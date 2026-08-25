import io
import re
import csv
from typing import List, Dict
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
import pandas as pd
from database.db_manager import DatabaseManager
from utils.decorators import login_required

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

@inventory_bp.route('/product/<sku>')
@login_required
def product_detail(sku):
    """Página dedicada de detalhes completos do SKU e catálogos conectados"""
    user_id = session['user_id']
    product = db.get_sku_details(user_id=user_id, sku=sku)
    if not product:
        flash(f'Produto com SKU "{sku}" não encontrado no inventário.', 'error')
        return redirect(url_for('inventory.inventory_list'))

    return render_template('inventory/product_detail.html', product=product, sku=sku)


@inventory_bp.route('/api/product/<sku>')
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
