import io
import re
import csv
from typing import List, Dict
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
from database.db_manager import DatabaseManager
from utils.decorators import login_required
from services.reference_listings_extractor import extract_reference_listing
from services.ai_matcher.dossier_builder import build_and_save_sku_dossier
from services.inventory_matcher import InventoryMatcher
from services.listing_auditor import ListingAuditor

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')
db = DatabaseManager()


@inventory_bp.route('/')
@login_required
def inventory_list():
    """Página principal de Estoque Consolidado e Pedidos de Compra"""
    user_id = session['user_id']
    inventory = db.get_consolidated_inventory(user_id)
    orders = db.get_purchase_orders(user_id)

    total_skus = len(inventory)
    total_pecas = sum(item.get('quantidade_total', 0) for item in inventory)
    total_pedidos = len(orders)

    return render_template(
        'inventory/inventory_list.html',
        inventory=inventory,
        orders=orders,
        total_skus=total_skus,
        total_pecas=total_pecas,
        total_pedidos=total_pedidos
    )


@inventory_bp.route('/orders/<pedido_id>')
@login_required
def order_detail(pedido_id):
    """Página de detalhes de um Pedido de Compra"""
    user_id = session['user_id']
    order = db.get_purchase_order_by_id(pedido_id, user_id)
    if not order:
        flash('Pedido não encontrado.', 'error')
        return redirect(url_for('inventory.inventory_list'))
    
    return render_template('inventory/order_detail.html', order=order)


@inventory_bp.route('/orders/create', methods=['POST'])
@login_required
def create_order():
    """Criação manual de pedido de compra"""
    try:
        user_id = session['user_id']
        data = request.get_json() if request.is_json else request.form

        numero_pedido = data.get('numero_pedido') or f"PED-{pd.Timestamp.now().strftime('%Y%m%d-%H%M')}"
        fornecedor = data.get('fornecedor', '')
        observacoes = data.get('observacoes', '')
        
        # Pode vir lista de itens via JSON
        itens = data.get('itens', [])
        if isinstance(itens, str):
            import json
            try:
                itens = json.loads(itens)
            except Exception:
                itens = []

        # Se veio via form com campos individuais (criação rápida de 1 item)
        if not itens and data.get('sku'):
            itens = [{
                'sku': data.get('sku'),
                'descricao': data.get('descricao') or data.get('sku'),
                'ncm': data.get('ncm', ''),
                'quantidade': int(data.get('quantidade', 1) or 1),
                'preco_revenda': float(data.get('preco_revenda') or 0) if data.get('preco_revenda') else None,
                'preco_site_pix': float(data.get('preco_site_pix') or 0) if data.get('preco_site_pix') else None,
                'link_produto': data.get('link_produto', '')
            }]

        if not itens:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Informe ao menos um item com SKU.'}), 400
            flash('Informe ao menos um item com SKU.', 'warning')
            return redirect(url_for('inventory.inventory_list'))

        order = db.create_purchase_order(
            user_id=user_id,
            numero_pedido=numero_pedido,
            fornecedor=fornecedor,
            observacoes=observacoes,
            itens=itens
        )

        if order:
            if request.is_json:
                return jsonify({'success': True, 'order': order, 'message': 'Pedido cadastrado com sucesso!'})
            flash('Pedido cadastrado com sucesso!', 'success')
            return redirect(url_for('inventory.inventory_list'))
        else:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Erro ao cadastrar pedido no banco de dados.'}), 500
            flash('Erro ao cadastrar pedido.', 'error')
            return redirect(url_for('inventory.inventory_list'))

    except Exception as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Erro ao processar pedido: {e}', 'error')
        return redirect(url_for('inventory.inventory_list'))


@inventory_bp.route('/orders/delete/<pedido_id>', methods=['POST'])
@login_required
def delete_order(pedido_id):
    """Exclusão de pedido de compra"""
    try:
        user_id = session['user_id']
        deleted = db.delete_purchase_order(pedido_id, user_id)
        if deleted:
            if request.is_json:
                return jsonify({'success': True, 'message': 'Pedido excluído com sucesso!'})
            flash('Pedido excluído com sucesso!', 'success')
        else:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Pedido não encontrado.'}), 404
            flash('Pedido não encontrado.', 'warning')
        return redirect(url_for('inventory.inventory_list'))
    except Exception as e:
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Erro ao excluir pedido: {e}', 'error')
        return redirect(url_for('inventory.inventory_list'))


@inventory_bp.route('/import-bulk', methods=['POST'])
@login_required
def import_bulk():
    """
    Importação em massa de produtos e pedidos:
    - Via upload de arquivo (XLSX / CSV)
    - Via texto copiado e colado do Google Sheets / Excel (Paste Grid)
    """
    try:
        user_id = session['user_id']
        parsed_items: List[Dict] = []
        numero_pedido = ""
        fornecedor = ""
        observacoes = ""

        # ─── 1. Importação via Upload de Arquivo (Multipart/form-data) ───
        if 'file' in request.files and request.files['file'].filename:
            file = request.files['file']
            filename = file.filename.lower()
            numero_pedido = request.form.get('numero_pedido') or f"LOTE-{filename.split('.')[0].upper()[:20]}"
            fornecedor = request.form.get('fornecedor', 'Importação em Massa')
            observacoes = request.form.get('observacoes', f"Arquivo: {file.filename}")

            if filename.endswith('.csv'):
                content = file.read().decode('utf-8', errors='ignore')
                df = pd.read_csv(io.StringIO(content), sep=None, engine='python')
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
            else:
                return jsonify({'success': False, 'error': 'Formato inválido. Envie um arquivo .xlsx ou .csv.'}), 400

            parsed_items = _parse_dataframe_to_items(df)

        # ─── 2. Importação via JSON / Colagem de Planilha (Ctrl+V) ───
        elif request.is_json:
            data = request.get_json()
            numero_pedido = data.get('numero_pedido') or f"LOTE-{pd.Timestamp.now().strftime('%Y%m%d-%H%M')}"
            fornecedor = data.get('fornecedor', 'Planilha Copiada')
            observacoes = data.get('observacoes', 'Importação via Copiar/Colar')
            pasted_text = data.get('pasted_text', '').strip()

            if pasted_text:
                parsed_items = _parse_pasted_text(pasted_text)
            elif data.get('itens'):
                parsed_items = data.get('itens')

        else:
            return jsonify({'success': False, 'error': 'Nenhum dado ou arquivo enviado para importação.'}), 400

        if not parsed_items:
            return jsonify({'success': False, 'error': 'Nenhum item válido com SKU foi identificado no conteúdo importado.'}), 400

        # Cria o pedido com os itens identificados
        created_order = db.create_purchase_order(
            user_id=user_id,
            numero_pedido=numero_pedido,
            fornecedor=fornecedor,
            observacoes=observacoes,
            itens=parsed_items
        )

        if created_order:
            return jsonify({
                'success': True,
                'message': f'Sucesso! {len(parsed_items)} itens importados no pedido "{numero_pedido}".',
                'order_id': created_order['id'],
                'total_items': len(parsed_items)
            })
        else:
            return jsonify({'success': False, 'error': 'Erro ao salvar pedido importado no banco.'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro no processamento da importação: {str(e)}'}), 500


def _parse_pasted_text(raw_text: str) -> List[Dict]:
    """Faz parse de texto copiado e colado de planilhas (TSV / CSV) com detecção posicional e semântica"""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return []

    # Detecta delimitador principal (Tab, Ponto-e-vírgula ou Vírgula)
    first_line = lines[0]
    if '\t' in first_line:
        delimiter = '\t'
    elif ';' in first_line:
        delimiter = ';'
    else:
        delimiter = ','

    reader = csv.reader(lines, delimiter=delimiter)
    rows = [r for r in reader if r and any(cell.strip() for cell in r)]
    if not rows:
        return []

    # Identifica se a primeira linha é cabeçalho
    first_row_str = ' '.join(rows[0]).lower()
    has_header = any(k in first_row_str for k in ['código', 'codigo', 'sku', 'descrição', 'descricao', 'ncm', 'quantidade', 'preco', 'preço'])
    start_idx = 1 if has_header else 0

    items: List[Dict] = []
    for row in rows[start_idx:]:
        cells = [c.strip() for c in row if c is not None]
        if not cells:
            continue

        # Se a primeira coluna for apenas número sequencial (ex: 1, 2, 3, #), ignora ela
        if len(cells) > 1 and (cells[0].isdigit() or cells[0] in ['#', 'item']):
            cells = cells[1:]

        if not cells:
            continue

        # SKU é a primeira coluna útil
        sku = cells[0].upper()
        descricao = cells[1] if len(cells) > 1 else sku
        ncm = ""
        qtd = 1
        preco_revenda = None
        preco_site_pix = None
        link_produto = ""

        # Itera sobre as colunas restantes analisando os tipos
        remaining = cells[2:]
        prices_found = []

        for cell in remaining:
            c_clean = cell.strip()
            if not c_clean:
                continue

            # 1. NCM (formato 0000.00.00 ou 8 dígitos com ponto)
            if re.match(r'^\d{4}\.\d{2}\.\d{2}$', c_clean) or (c_clean.replace('.', '').isdigit() and len(c_clean.replace('.', '')) == 8 and '.' in c_clean):
                ncm = c_clean
            
            # 2. Quantidade explícita com 'UN' ou 'unidades' ou 'un'
            elif re.search(r'^\d+\s*(un|unidades|pc|pcs)?$', c_clean, re.IGNORECASE):
                nums = re.findall(r'\d+', c_clean)
                if nums and (int(nums[0]) <= 10000) and 'r$' not in c_clean.lower() and ',' not in c_clean:
                    # Se tiver 'un' explícito ou for inteiro simples pequeno, é qtd
                    if 'un' in c_clean.lower() or qtd == 1:
                        qtd = int(nums[0])
                    else:
                        p_val = _parse_price(c_clean)
                        if p_val > 0:
                            prices_found.append(p_val)
            
            # 3. Link HTTP
            elif c_clean.startswith(('http://', 'https://', 'www.')):
                link_produto = c_clean
            
            # 4. Preço (contém R$, vírgula decimal ou valor formatado)
            elif 'r$' in c_clean.lower() or ',' in c_clean or ('.' in c_clean and len(c_clean.split('.')[1]) == 2):
                p_val = _parse_price(c_clean)
                if p_val > 0:
                    prices_found.append(p_val)
            
            # 5. Outros valores numéricos
            else:
                p_val = _parse_price(c_clean)
                if p_val > 0:
                    prices_found.append(p_val)

        if len(prices_found) >= 1:
            preco_revenda = prices_found[0]
        if len(prices_found) >= 2:
            preco_site_pix = prices_found[1]

        if sku:
            items.append({
                'sku': sku,
                'descricao': descricao or sku,
                'ncm': ncm,
                'quantidade': qtd,
                'preco_revenda': preco_revenda,
                'preco_site_pix': preco_site_pix,
                'link_produto': link_produto
            })

    return items


def _parse_dataframe_to_items(df: pd.DataFrame) -> List[Dict]:
    """Mapeia DataFrame de XLSX ou CSV para lista de itens estruturados"""
    items: List[Dict] = []
    
    # Normaliza nomes de colunas
    col_map = {}
    for col in df.columns:
        c_lower = str(col).strip().lower()
        if any(k in c_lower for k in ['código', 'codigo', 'sku', 'cod']):
            col_map['sku'] = col
        elif any(k in c_lower for k in ['descrição', 'descricao', 'nome', 'produto', 'título', 'titulo']):
            col_map['descricao'] = col
        elif 'ncm' in c_lower:
            col_map['ncm'] = col
        elif any(k in c_lower for k in ['quantidade', 'qtd', 'estoque', 'quant']):
            col_map['quantidade'] = col
        elif any(k in c_lower for k in ['revenda', 'preço', 'preco', 'marketplace']):
            col_map['preco_revenda'] = col
        elif any(k in c_lower for k in ['pix', 'site']):
            col_map['preco_site_pix'] = col
        elif any(k in c_lower for k in ['link', 'url', 'ecoflow']):
            col_map['link_produto'] = col

    for _, row in df.iterrows():
        sku_val = str(row[col_map['sku']]).strip() if 'sku' in col_map and pd.notna(row[col_map['sku']]) else ""
        if not sku_val or sku_val.lower() == 'nan':
            continue

        desc_val = str(row[col_map['descricao']]).strip() if 'descricao' in col_map and pd.notna(row[col_map['descricao']]) else sku_val
        ncm_val = str(row[col_map['ncm']]).strip() if 'ncm' in col_map and pd.notna(row[col_map['ncm']]) else ""
        
        qtd_raw = str(row[col_map['quantidade']]) if 'quantidade' in col_map and pd.notna(row[col_map['quantidade']]) else "1"
        qtd_nums = re.findall(r'\d+', qtd_raw)
        qtd = int(qtd_nums[0]) if qtd_nums else 1

        p_revenda = _parse_price(str(row[col_map['preco_revenda']])) if 'preco_revenda' in col_map and pd.notna(row[col_map['preco_revenda']]) else None
        p_pix = _parse_price(str(row[col_map['preco_site_pix']])) if 'preco_site_pix' in col_map and pd.notna(row[col_map['preco_site_pix']]) else None
        link_val = str(row[col_map['link_produto']]).strip() if 'link_produto' in col_map and pd.notna(row[col_map['link_produto']]) else ""

        items.append({
            'sku': sku_val.upper(),
            'descricao': desc_val,
            'ncm': ncm_val,
            'quantidade': qtd,
            'preco_revenda': p_revenda,
            'preco_site_pix': p_pix,
            'link_produto': link_val
        })

    return items


def _parse_price(price_str: str) -> float:
    """Converte strings de preço (ex: 'R$ 3.179,00' ou '3179.00') para float"""
    if not price_str or price_str.lower() == 'nan':
        return 0.0
    try:
        clean = re.sub(r'[^\d,\.]', '', str(price_str))
        if ',' in clean and '.' in clean:
            clean = clean.replace('.', '').replace(',', '.')
        elif ',' in clean:
            clean = clean.replace(',', '.')
        return float(clean)
    except Exception:
        return 0.0


# ─── API de Vinculação de Catálogos a SKUs (1-para-N) ──────────────────────────

@inventory_bp.route('/api/skus', methods=['GET'])
@login_required
def get_user_skus_api():
    """Retorna lista rápida de SKUs do estoque do usuário para o modal de vinculação"""
    try:
        user_id = session['user_id']
        inventory = db.get_consolidated_inventory(user_id)
        skus_data = []
        for item in inventory:
            skus_data.append({
                'sku': item.get('sku'),
                'descricao': item.get('descricao'),
                'quantidade_total': item.get('quantidade_total', 0),
                'preco_revenda': item.get('preco_revenda'),
                'catalogs_count': len(item.get('catalogs', []))
            })
        return jsonify({'success': True, 'skus': skus_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/link-catalog', methods=['POST'])
@login_required
def link_catalog_api():
    """Vincula um catálogo a um SKU do inventário mediante aprovação do usuário"""
    try:
        user_id = session['user_id']
        data = request.get_json() or {}

        sku = data.get('sku')
        catalog_id = data.get('catalog_id')
        catalog_title = data.get('catalog_title', '')
        catalog_url = data.get('catalog_url', '')
        catalog_image = data.get('catalog_image', '')
        buybox_winner = data.get('buybox_winner', 'Vendedor Oficial')
        buybox_min_price = float(data.get('buybox_min_price') or 0.0)
        sellers_count = int(data.get('sellers_count') or 1)

        if not sku or not catalog_id:
            return jsonify({'success': False, 'error': 'SKU e Catalog ID são obrigatórios.'}), 400

        result = db.link_catalog_to_sku(
            user_id=user_id,
            sku=sku,
            catalog_id=catalog_id,
            catalog_title=catalog_title,
            catalog_url=catalog_url,
            catalog_image=catalog_image,
            buybox_winner=buybox_winner,
            buybox_min_price=buybox_min_price,
            sellers_count=sellers_count
        )

        return jsonify({
            'success': True,
            'message': f"Catálogo {catalog_id} vinculado com sucesso ao SKU {sku}!",
            'data': result
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/unlink-catalog', methods=['POST'])
@login_required
def unlink_catalog_api():
    """Desvincula um catálogo de um SKU do inventário"""
    try:
        user_id = session['user_id']
        data = request.get_json() or {}

        sku = data.get('sku')
        catalog_id = data.get('catalog_id')

        if not sku or not catalog_id:
            return jsonify({'success': False, 'error': 'SKU e Catalog ID são obrigatórios.'}), 400

        success = db.unlink_catalog_from_sku(user_id=user_id, sku=sku, catalog_id=catalog_id)
        if success:
            return jsonify({'success': True, 'message': f"Catálogo {catalog_id} desvinculado do SKU {sku}."})
        return jsonify({'success': False, 'error': 'Falha ao desvincular catálogo.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── Detalhes do Produto / SKU (Página Dedicada e API JSON para Drawer) ──────────

@inventory_bp.route('/product/<path:sku>')
@login_required
def product_detail(sku):
    """Página dedicada de detalhes completos do SKU e catálogos conectados"""
    user_id = session['user_id']
    product = db.get_sku_details(user_id=user_id, sku=sku)
    if not product:
        flash(f'Produto com SKU "{sku}" não encontrado no inventário.', 'error')
        return redirect(url_for('inventory.inventory_list'))

    return render_template('inventory/product_detail.html', product=product, sku=sku)


@inventory_bp.route('/api/product/<path:sku>')
@login_required
def product_detail_api(sku):
    """Retorna dados completos do SKU e seus catálogos conectados para o Drawer lateral"""
    user_id = session['user_id']
    product = db.get_sku_details(user_id=user_id, sku=sku)
    if not product:
        return jsonify({'success': False, 'error': f'Produto {sku} não encontrado.'}), 404

    return jsonify({
        'success': True,
        'product': product
    })


# ─── Gestão de Conhecimento do SKU e Anúncios de Referência ───────────────────

@inventory_bp.route('/api/sku/<path:sku>/knowledge', methods=['GET'])
@login_required
def get_sku_knowledge_api(sku):
    """Retorna o Dossiê Canônico e a lista de anúncios de referência de um SKU"""
    user_id = session['user_id']
    knowledge = db.get_sku_knowledge(user_id, sku)
    references = db.get_sku_reference_listings(user_id, sku)
    return jsonify({
        'success': True,
        'sku': sku,
        'knowledge': knowledge,
        'reference_listings': references
    })


@inventory_bp.route('/api/sku/<path:sku>/reference-listing', methods=['POST'])
@login_required
def add_sku_reference_listing_api(sku):
    """Adiciona um anúncio ativo de referência ao SKU e atualiza o Dossiê Canônico"""
    user_id = session['user_id']
    try:
        data = request.get_json(force=True, silent=True) or {}
        url_or_id = (data.get('url_or_id') or '').strip()
        is_own_store = bool(data.get('is_own_store', True))

        if not url_or_id:
            return jsonify({'success': False, 'error': 'Informe a URL ou ID do anúncio.'}), 400

        # Extrai metadados do marketplace (ML, Amazon, Loja Própria)
        listing_data = extract_reference_listing(url_or_id, user_id=user_id)
        listing_data['is_own_store'] = is_own_store

        saved_ref = db.add_sku_reference_listing(user_id, sku, listing_data)

        # Dispara o grafo de síntese do Dossiê Canônico com o novo anúncio integrado
        updated_dossier = build_and_save_sku_dossier(user_id, sku, db)

        return jsonify({
            'success': True,
            'message': 'Anúncio de referência adicionado e Dossiê Canônico atualizado!',
            'reference': saved_ref,
            'dossier': updated_dossier
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao adicionar anúncio: {str(e)}'}), 500


@inventory_bp.route('/api/sku/<path:sku>/reference-listing/<listing_id>', methods=['DELETE', 'POST'])
@login_required
def delete_sku_reference_listing_api(sku, listing_id):
    """Remove um anúncio de referência do SKU"""
    user_id = session['user_id']
    try:
        success = db.delete_sku_reference_listing(user_id, sku, listing_id)
        if success:
            return jsonify({'success': True, 'message': 'Anúncio de referência removido com sucesso.'})
        return jsonify({'success': False, 'error': 'Não foi possível remover o anúncio.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/api/sku/<path:sku>/resynthesize-dossier', methods=['POST'])
@login_required
def resynthesize_sku_dossier_api(sku):
    """Reexecuta o grafo de síntese do Dossiê Canônico para o SKU"""
    user_id = session['user_id']
    try:
        dossier = build_and_save_sku_dossier(user_id, sku, db)
        return jsonify({
            'success': True,
            'message': 'Dossiê Canônico reanalisado com sucesso pelo agente de IA!',
            'dossier': dossier
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao reanalisar dossiê: {str(e)}'}), 500


# ==============================================================================
# ENDPOINTS DO SCANNER INTELIGENTE DE PRODUTOS E MATCHING COM INVENTÁRIO
# ==============================================================================

@inventory_bp.route('/api/scanner/extract-and-match', methods=['POST'])
@login_required
def scanner_extract_and_match_api():
    """Extrai metadados do link (ML, Amazon, Fornecedor), audita ou cruza com o estoque"""
    user_id = session['user_id']
    try:
        data = request.get_json(force=True, silent=True) or {}
        url_or_id = (data.get('url_or_id') or '').strip()
        role = (data.get('role') or 'supplier').strip().lower()
        sku_hint = (data.get('sku_hint') or '').strip().upper()

        if not url_or_id:
            return jsonify({'success': False, 'error': 'Por favor, informe a URL ou ID do anúncio.'}), 400

        # 1. Extração estruturada de atributos
        extracted = extract_reference_listing(url_or_id, user_id=user_id, role=role)

        # 2. Busca e ranking de candidatos no inventário
        matcher = InventoryMatcher(db)
        candidates = matcher.find_matches_for_listing(user_id, extracted, limit=5)

        # Identifica candidato principal (ou usa o sku_hint se informado)
        top_candidate = None
        if sku_hint:
            for c in candidates:
                if c.get('sku') == sku_hint:
                    top_candidate = c
                    break
            if not top_candidate:
                inv_details = db.get_sku_details(user_id, sku_hint)
                if inv_details:
                    top_candidate = {
                        "sku": sku_hint,
                        "descricao": inv_details.get("descricao") or sku_hint,
                        "quantidade_total": inv_details.get("quantidade_total", 0),
                        "preco_custo": float(inv_details.get("preco_custo") or 0.0),
                        "preco_revenda": float(inv_details.get("preco_revenda") or 0.0),
                        "match_score": 100,
                        "match_tier": "USER_SPECIFIED",
                        "match_badge": "🎯 SKU Selecionado Diretamente",
                        "reasons": ["Selecionado diretamente pelo usuário"]
                    }
        elif candidates:
            top_candidate = candidates[0]

        # 3. Se for Loja Própria: roda auditoria de saúde do anúncio
        audit_data = None
        if role == 'own_store':
            auditor = ListingAuditor(db)
            audit_data = auditor.audit_own_store_listing(user_id, extracted, top_candidate)

        # 4. Se for Concorrente: calcula análise de margem contra o topo do inventário
        competitor_analysis = None
        if role == 'competitor' and top_candidate:
            cost = float(top_candidate.get('preco_custo') or 0.0)
            comp_price = float(extracted.get('price') or 0.0)
            fee = round(comp_price * 0.16, 2)
            net_profit = round(comp_price - fee - cost, 2)
            margin_pct = round((net_profit / comp_price) * 100, 1) if comp_price > 0 else 0.0

            competitor_analysis = {
                "competitor_price": comp_price,
                "inventory_cost": cost,
                "marketplace_fee": fee,
                "net_profit": net_profit,
                "margin_pct": margin_pct,
                "is_dangerous": (net_profit < 0 or margin_pct < 8.0)
            }

        return jsonify({
            'success': True,
            'extracted_data': extracted,
            'candidates': candidates,
            'top_candidate': top_candidate,
            'audit': audit_data,
            'competitor_analysis': competitor_analysis,
            'role': role
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao escanear produto: {str(e)}'}), 500


@inventory_bp.route('/api/scanner/confirm-link', methods=['POST'])
@login_required
def scanner_confirm_link_api():
    """Confirma e salva o vínculo do anúncio escaneado com o SKU do inventário"""
    user_id = session['user_id']
    try:
        data = request.get_json(force=True, silent=True) or {}
        sku = str(data.get('sku') or '').strip().upper()
        extracted_data = data.get('extracted_data') or {}
        role = str(data.get('role') or extracted_data.get('listing_role') or 'supplier').strip().lower()
        override_title = (data.get('override_title') or '').strip()
        override_price = data.get('override_price')

        if not sku:
            return jsonify({'success': False, 'error': 'SKU de destino não informado.'}), 400
        if not extracted_data:
            return jsonify({'success': False, 'error': 'Dados extraídos do produto não fornecidos.'}), 400

        if override_title:
            extracted_data['title'] = override_title
        if override_price is not None and str(override_price).strip() != '':
            try:
                extracted_data['price'] = float(override_price)
            except:
                pass

        extracted_data['listing_role'] = role
        extracted_data['is_own_store'] = (role == 'own_store')

        # Persiste na tabela de referências ativas do SKU
        saved_ref = db.add_sku_reference_listing(user_id, sku, extracted_data)

        # Se for anúncio do Mercado Livre ou catálogo MLB, também sincroniza em sku_catalogs
        listing_id = str(extracted_data.get('listing_id') or '').strip().upper()
        if listing_id.startswith('MLB'):
            try:
                db.link_catalog_to_sku(
                    user_id=user_id,
                    sku=sku,
                    catalog_id=listing_id,
                    catalog_title=extracted_data.get('title', ''),
                    catalog_url=extracted_data.get('listing_url', ''),
                    catalog_image=extracted_data.get('image_url', ''),
                    buybox_winner=extracted_data.get('seller', 'Vendedor'),
                    buybox_min_price=float(extracted_data.get('price') or 0.0),
                    sellers_count=1
                )
            except Exception as e_link:
                print(f"Aviso ao linkar sku_catalogs via scanner: {e_link}")

        # Atualiza Dossiê Canônico com o novo conhecimento anexado
        updated_dossier = build_and_save_sku_dossier(user_id, sku, db)

        return jsonify({
            'success': True,
            'message': f'Produto vinculado com sucesso ao SKU {sku}!',
            'sku': sku,
            'reference': saved_ref,
            'dossier': updated_dossier
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao confirmar vínculo: {str(e)}'}), 500


@inventory_bp.route('/api/scanner/quick-fill-attributes', methods=['POST'])
@login_required
def scanner_quick_fill_attributes_api():
    """Aplica atributos do fornecedor para enriquecer a base de conhecimento do SKU"""
    user_id = session['user_id']
    try:
        data = request.get_json(force=True, silent=True) or {}
        sku = str(data.get('sku') or '').strip().upper()
        fill_attrs = data.get('attributes') or {}

        if not sku or not fill_attrs:
            return jsonify({'success': False, 'error': 'SKU e atributos são obrigatórios.'}), 400

        # Atualiza o Dossiê Canônico com a nova fusão de atributos
        updated_dossier = build_and_save_sku_dossier(user_id, sku, db)

        return jsonify({
            'success': True,
            'message': 'Atributos sincronizados com sucesso a partir da base do fornecedor!',
            'dossier': updated_dossier
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao preencher atributos: {str(e)}'}), 500


@inventory_bp.route('/api/scanner/create-sku-from-listing', methods=['POST'])
@login_required
def scanner_create_sku_from_listing_api():
    """Cadastra um novo SKU no inventário a partir dos dados do produto escaneado"""
    user_id = session['user_id']
    try:
        data = request.get_json(force=True, silent=True) or {}
        sku = str(data.get('sku') or '').strip().upper()
        descricao = str(data.get('descricao') or '').strip()
        preco_custo = float(data.get('preco_custo') or 0.0)
        preco_revenda = float(data.get('preco_revenda') or 0.0)
        link_produto = str(data.get('link_produto') or '').strip()
        ncm = str(data.get('ncm') or '').strip()
        extracted_data = data.get('extracted_data') or {}
        role = str(data.get('role') or 'supplier').strip().lower()

        if not sku:
            return jsonify({'success': False, 'error': 'O código do novo SKU é obrigatório.'}), 400
        if not descricao:
            descricao = extracted_data.get('title') or sku

        # 1. Cria o item no inventário
        success = db.create_inventory_item(
            user_id=user_id,
            sku=sku,
            descricao=descricao,
            preco_custo=preco_custo,
            preco_revenda=preco_revenda,
            link_produto=link_produto or extracted_data.get('listing_url', ''),
            ncm=ncm
        )
        if not success:
            return jsonify({'success': False, 'error': 'Não foi possível cadastrar o item no estoque.'}), 400

        # 2. Salva a referência se dados extraídos foram fornecidos
        if extracted_data:
            extracted_data['listing_role'] = role
            extracted_data['is_own_store'] = (role == 'own_store')
            db.add_sku_reference_listing(user_id, sku, extracted_data)

        # 3. Gera dossiê canônico inicial para o novo SKU
        dossier = build_and_save_sku_dossier(user_id, sku, db)

        return jsonify({
            'success': True,
            'message': f'Novo SKU {sku} cadastrado no estoque com sucesso!',
            'sku': sku,
            'dossier': dossier
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao criar SKU a partir do anúncio: {str(e)}'}), 500
