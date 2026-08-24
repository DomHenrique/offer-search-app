from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import threading
import time
from datetime import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from services.meli.catalog import MeliCatalogService
from scraping.web_scrap_catalog_ml import get_catalog_list, get_catalog_sellers
from scraping.web_scrap_amazon_catalog import get_amazon_catalog_sellers

catalog_bp = Blueprint('catalog', __name__)
db_manager = DatabaseManager()
meli_catalog = MeliCatalogService()

# Armazena status das buscas em andamento (em memória)
catalog_search_status = {}
catalog_sellers_status = {}


# ─── Páginas ──────────────────────────────────────────────────────────────────

@catalog_bp.route('/')
def catalog_list():
    """Página principal de catálogos — listagem, busca e comparação com inventário."""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']

    # 1. Catálogos salvos do usuário
    saved_catalogs = db_manager.get_user_catalogs(user_id, limit=200)

    # 2. Inventário consolidado do usuário para cruzamento de SKUs
    inventory = db_manager.get_consolidated_inventory(user_id)
    sku_dict = {str(item.get('sku') or '').strip().upper(): item for item in inventory}

    # 3. Mapeamento de SKUs vinculados
    sku_links = db_manager.get_sku_catalogs(user_id)
    catalog_to_sku = {}
    for link in sku_links:
        c_id = str(link.get('catalog_id') or '').strip().upper()
        s_code = str(link.get('sku') or '').strip().upper()
        if c_id and s_code:
            catalog_to_sku[c_id] = s_code

    # 4. Busca os menores preços coletados para todos os catálogos
    catalog_ids = [str(cat.get('catalog_id') or '').strip().upper() for cat in saved_catalogs if cat.get('catalog_id')]
    prices_map = db_manager.get_catalog_prices_map(catalog_ids)

    # 5. Agrupa os catálogos identificando a origem (SKU vinculado vs Busca Avulsa) e calculando métricas
    from collections import OrderedDict
    grouped_catalogs = OrderedDict()

    for cat in saved_catalogs:
        c_id = str(cat.get('catalog_id') or '').strip().upper()
        raw_term = (cat.get('termo_pesquisa') or '').strip()
        
        # Preço de concorrência coletado
        price_data = prices_map.get(c_id, {})
        competitor_price = float(price_data.get('min_price') or cat.get('buybox_min_price') or 0.0)
        buybox_winner = price_data.get('buybox_winner') or cat.get('buybox_winner') or 'Vendedor Oficial'
        cat['competitor_price'] = competitor_price
        cat['buybox_winner'] = buybox_winner
        cat['frete_full'] = price_data.get('frete_full', False)
        
        # Identifica se este catálogo está vinculado a um SKU diretamente ou pelo termo
        linked_sku = catalog_to_sku.get(c_id)
        if not linked_sku:
            for s_code, s_item in sku_dict.items():
                if raw_term.upper() == s_code or raw_term.lower() == s_item.get('descricao', '').lower():
                    linked_sku = s_code
                    break

        group_key = linked_sku if linked_sku else (raw_term if raw_term else 'Outros / Sem termo associado')

        if group_key not in grouped_catalogs:
            sku_info = sku_dict.get(linked_sku) if linked_sku else None
            grouped_catalogs[group_key] = {
                'key': group_key,
                'term': raw_term or group_key,
                'sku_code': linked_sku,
                'sku_info': sku_info,
                'is_orphan': bool(linked_sku is None),
                'catalogs': []
            }
        
        # Anexa métricas do SKU e comparativo de preços
        sku_info = grouped_catalogs[group_key]['sku_info']
        if sku_info:
            my_revenda = float(sku_info.get('preco_revenda') or 0.0)
            my_pix = float(sku_info.get('preco_site_pix') or 0.0)
            my_custo = float(sku_info.get('preco_custo') or 0.0)
        else:
            my_revenda = 0.0
            my_pix = 0.0
            my_custo = 0.0

        cat['my_revenda'] = my_revenda
        cat['my_pix'] = my_pix
        cat['my_custo'] = my_custo

        # Cálculo de status de competitividade e margem
        if not sku_info:
            status = 'sem_sku'
            diff_price = 0.0
            diff_pct = 0.0
            margin_pct = 0.0
        elif competitor_price <= 0 or my_revenda <= 0:
            status = 'sem_preco'
            diff_price = 0.0
            diff_pct = 0.0
            margin_pct = ((my_revenda - my_custo) / my_revenda * 100) if my_revenda > 0 and my_custo > 0 else 0.0
        else:
            diff_price = my_revenda - competitor_price
            diff_pct = ((my_revenda - competitor_price) / competitor_price * 100)
            margin_pct = ((my_revenda - my_custo) / my_revenda * 100) if my_revenda > 0 and my_custo > 0 else 0.0
            if my_revenda < competitor_price:
                status = 'vencendo'
            elif my_revenda > competitor_price:
                status = 'perdendo'
            else:
                status = 'empatado'

        cat['status_competitivo'] = status
        cat['diff_price'] = diff_price
        cat['diff_pct'] = diff_pct
        cat['margin_pct'] = margin_pct

        grouped_catalogs[group_key]['catalogs'].append(cat)

    return render_template('catalog/catalog_list.html',
                           saved_catalogs=saved_catalogs,
                           grouped_catalogs=grouped_catalogs,
                           inventory=inventory)


@catalog_bp.route('/<catalog_id>')
def catalog_detail(catalog_id):
    """Página de detalhe de um catálogo — sellers e comparativo (Mercado Livre e Amazon)."""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))

    catalog_id = str(catalog_id).strip().upper()

    # Valida o formato do catalog_id (MLB... ou ASIN de 10 dígitos)
    import re
    is_valid = bool(re.match(r'^MLB\d+$', catalog_id)) or bool(re.match(r'^[A-Z0-9]{10}$', catalog_id))
    if not is_valid:
        flash('ID de catálogo inválido.', 'error')
        return redirect(url_for('catalog.catalog_list'))

    # Busca dados do catálogo no banco
    catalog = db_manager.get_catalog_by_id(catalog_id)

    # Busca sellers já coletados (última coleta)
    sellers = db_manager.get_catalog_sellers(catalog_id)

    # Se não tiver catálogo no banco nem sellers, cria registro inicial básico
    if not catalog:
        mp = "MercadoLivre" if catalog_id.startswith('MLB') else "Amazon"
        catalog = {
            "catalog_id": catalog_id,
            "titulo": f"Catálogo {mp} {catalog_id}",
            "nome": f"Catálogo {mp} {catalog_id}",
            "url_produto": f"https://www.mercadolivre.com.br/p/{catalog_id}" if mp == "MercadoLivre" else f"https://www.amazon.com.br/dp/{catalog_id}",
            "marketplace": mp,
            "buybox_winner": "Vendedor Oficial",
            "buybox_min_price": 0.0,
            "sellers_count": len(sellers) if sellers else 1
        }

    return render_template('catalog/catalog_detail.html',
                           catalog_id=catalog_id,
                           catalog=catalog,
                           sellers=sellers)


@catalog_bp.route('/extract-from-history', methods=['POST'])
def extract_from_history():
    """Extrai catálogos confirmados do histórico e limpa produtos sem concorrência"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    try:
        user_id = session['user_id']
        # Limpa catálogos da Amazon que foram catalogados com apenas 1 vendedor
        db_manager.cleanup_single_seller_catalogs()
        catalogs = db_manager.extract_and_save_catalogs_from_offers(user_id=user_id)
        return jsonify({
            'success': True,
            'count': len(catalogs),
            'catalogs': catalogs,
            'message': f"{len(catalogs)} catálogo(s) sincronizado(s) com sucesso a partir do histórico de ofertas!"
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@catalog_bp.route('/cleanup-empty', methods=['POST'])
def cleanup_empty():
    """Remove da listagem de catálogos produtos que possuem apenas 1 vendedor (sem concorrência)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    try:
        removed = db_manager.cleanup_single_seller_catalogs()
        return jsonify({
            'success': True,
            'removed': removed,
            'message': f"{removed} produto(s) de vendedor único removido(s) da lista de catálogos."
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── API — Busca de catálogos (assíncrona) ───────────────────────────────────

@catalog_bp.route('/search', methods=['POST'])
def search_catalogs():
    """Inicia busca de catálogos por termo em thread de background com suporte a origin_sku."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json() or {}
    search_term = (data.get('termo_pesquisa') or '').strip()
    origin_sku = (data.get('origin_sku') or '').strip().upper()
    n_pages = max(1, min(int(data.get('n_pages', 1) or 1), 3))

    if not search_term or len(search_term) < 2:
        return jsonify({'error': 'Termo de pesquisa deve ter pelo menos 2 caracteres'}), 400

    user_id = session['user_id']
    search_id = f"cat_{user_id}_{int(time.time())}"

    catalog_search_status[search_id] = {
        'status': 'iniciando',
        'progress': 0,
        'message': 'Preparando busca de catálogos...',
        'results': [],
        'error': None,
        'completed': False,
    }

    thread = threading.Thread(
        target=_search_catalogs_thread,
        args=(search_id, user_id, search_term, n_pages, origin_sku),
        daemon=True
    )
    thread.start()

    return jsonify({'search_id': search_id})


def _search_catalogs_thread(search_id: str, user_id: str, search_term: str, n_pages: int, origin_sku: str = ''):
    """Thread de busca de catálogos com API Oficial do Mercado Livre e vinculação automática de SKU."""
    try:
        clean_search = search_term
        if origin_sku and origin_sku.upper().startswith('ECO') and 'ecoflow' not in clean_search.lower():
            clean_search = f"EcoFlow {clean_search}"

        catalog_search_status[search_id].update({
            'status': 'buscando',
            'progress': 20,
            'message': f'Buscando catálogos para "{clean_search}" no Mercado Livre (API Oficial)...'
        })

        catalogs = []
        
        # 1. Tenta buscar via API Oficial do Mercado Livre (/products/search)
        try:
            api_res = meli_catalog.search_catalog_products(clean_search, limit=50, user_id=user_id, only_active=True)
            if api_res.get('success') and api_res.get('results'):
                for p in api_res['results']:
                    p_price = float(p.get('price') or p.get('buybox_min_price') or p.get('preco') or 0.0)
                    sellers = int(p.get('sellers_count') or 0)
                    if p_price > 0 and (sellers > 0 or p.get('buy_box_winner')):
                        catalogs.append({
                            'catalog_id': p['catalog_id'],
                            'nome': p.get('name') or p.get('title'),
                            'imagem': p.get('image_url', ''),
                            'preco': p_price,
                            'buybox_min_price': p_price,
                            'competitor_price': p_price,
                            'sellers_count': max(1, sellers),
                            'url': p.get('permalink', ''),
                            'buy_box_winner': p.get('buy_box_winner')
                        })
                print(f"✅ [Catalog] {len(catalogs)} catálogos ativos encontrados via API Oficial Meli.")
        except Exception as e_api:
            print(f"⚠️ [Catalog] Falha na API Oficial Meli, acionando fallback de scraping: {e_api}")

        # 2. Se a API não retornou catálogos, executa fallback transparente para scraping
        if not catalogs:
            catalog_search_status[search_id].update({
                'progress': 40,
                'message': f'Consultando catálogos via motor de busca secundário...'
            })
            result = get_catalog_list(clean_search, n_pages)
            if not result['success']:
                catalog_search_status[search_id].update({
                    'status': 'erro',
                    'error': result.get('error', 'Nenhum catálogo encontrado'),
                    'completed': True,
                })
                return
            raw_cats = result.get('catalogs', [])
            for rc in raw_cats:
                rc_price = float(rc.get('buybox_min_price') or rc.get('preco') or rc.get('price') or 0.0)
                if rc_price > 0:
                    rc['preco'] = rc_price
                    rc['buybox_min_price'] = rc_price
                    rc['competitor_price'] = rc_price
                    rc['sellers_count'] = int(rc.get('sellers_count') or 1)
                    catalogs.append(rc)

        # Filtro estrito final de garantia
        catalogs = [c for c in catalogs if float(c.get('preco') or 0.0) > 0]

        catalog_search_status[search_id].update({
            'progress': 70,
            'message': f'Salvando {len(catalogs)} catálogos...'
        })

        # Obtém vínculos existentes do usuário e inventário para comparação
        existing_links = {item['catalog_id']: item['sku'] for item in db_manager.get_sku_catalogs(user_id=user_id)}
        inventory = db_manager.get_consolidated_inventory(user_id)
        sku_dict = {str(item.get('sku') or '').strip().upper(): item for item in inventory}

        # Persiste catálogos no Supabase
        for cat in catalogs:
            cid = str(cat['catalog_id']).strip().upper()
            db_manager.save_catalog({
                'catalog_id': cid,
                'nome': cat.get('nome') or cat.get('title', ''),
                'imagem': cat.get('imagem') or cat.get('image_url', ''),
                'termo_pesquisa': search_term,
                'user_id': user_id,
            })

            # Se houver SKU de origem, realiza o vínculo automático em sku_catalogs
            if origin_sku:
                try:
                    db_manager.link_catalog_to_sku(
                        user_id=user_id,
                        sku=origin_sku,
                        catalog_id=cid,
                        catalog_title=cat.get('nome', ''),
                        catalog_image=cat.get('imagem', '')
                    )
                    existing_links[cid] = origin_sku
                except Exception as e_link:
                    print(f"Aviso ao auto-vincular catálogo {cid} ao SKU {origin_sku}: {e_link}")

            linked_sku = existing_links.get(cid) or origin_sku
            cat['linked_sku'] = linked_sku
            cat['is_linked'] = bool(linked_sku)

            # Anexa métricas do SKU vinculado se houver
            comp_price = float(cat.get('competitor_price') or cat.get('preco') or cat.get('buybox_min_price') or 0.0)
            cat['competitor_price'] = comp_price
            cat['preco'] = comp_price
            cat['buybox_min_price'] = comp_price

            if linked_sku and linked_sku.upper() in sku_dict:
                sku_info = sku_dict[linked_sku.upper()]
                my_revenda = float(sku_info.get('preco_revenda') or 0.0)
                my_pix = float(sku_info.get('preco_site_pix') or 0.0)
                my_custo = float(sku_info.get('preco_custo') or 0.0)
                cat['my_revenda'] = my_revenda
                cat['my_pix'] = my_pix
                cat['my_custo'] = my_custo

                if comp_price > 0 and my_revenda > 0:
                    diff = my_revenda - comp_price
                    cat['diff_price'] = diff
                    if diff < -0.01:
                        cat['status_competitivo'] = 'vencendo'
                    elif diff > 0.01:
                        cat['status_competitivo'] = 'perdendo'
                    else:
                        cat['status_competitivo'] = 'empatado'
                else:
                    cat['status_competitivo'] = 'sem_concorrencia' if comp_price == 0 else 'sem_sku'
            else:
                cat['status_competitivo'] = 'sem_sku'

        catalog_search_status[search_id].update({
            'status': 'concluida',
            'progress': 100,
            'message': f'{len(catalogs)} catálogo(s) encontrado(s).',
            'results': catalogs,
            'completed': True,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        catalog_search_status[search_id].update({
            'status': 'erro',
            'error': str(e),
            'completed': True,
        })


@catalog_bp.route('/link-sku', methods=['POST'])
def link_sku():
    """Vincula manualmente um catálogo a um SKU do inventário."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    data = request.get_json() or {}
    sku = (data.get('sku') or '').strip().upper()
    catalog_id = (data.get('catalog_id') or '').strip().upper()
    user_id = session['user_id']
    
    if not sku or not catalog_id:
        return jsonify({'error': 'SKU e Catalog ID são obrigatórios'}), 400
    
    try:
        res = db_manager.link_catalog_to_sku(user_id=user_id, sku=sku, catalog_id=catalog_id)
        return jsonify({'success': True, 'data': res, 'message': f'Catálogo {catalog_id} vinculado ao SKU {sku} com sucesso!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@catalog_bp.route('/unlink-sku', methods=['POST'])
def unlink_sku():
    """Desvincula um catálogo de um SKU do inventário."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    data = request.get_json() or {}
    sku = (data.get('sku') or '').strip().upper()
    catalog_id = (data.get('catalog_id') or '').strip().upper()
    user_id = session['user_id']
    
    if not sku or not catalog_id:
        return jsonify({'error': 'SKU e Catalog ID são obrigatórios'}), 400
    
    try:
        db_manager.unlink_catalog_from_sku(user_id=user_id, sku=sku, catalog_id=catalog_id)
        return jsonify({'success': True, 'message': f'Catálogo {catalog_id} desvinculado do SKU {sku}!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@catalog_bp.route('/delete-batch', methods=['POST'])
def delete_batch():
    """Exclui múltiplos catálogos do banco e da visualização."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json() or {}
    catalog_ids = data.get('catalog_ids', [])
    if isinstance(catalog_ids, str):
        catalog_ids = [catalog_ids]
    
    if not catalog_ids:
        return jsonify({'error': 'Nenhum catálogo informado para exclusão'}), 400

    user_id = session['user_id']
    try:
        deleted = db_manager.delete_catalogs(user_id=user_id, catalog_ids=catalog_ids)
        return jsonify({
            'success': True,
            'deleted_count': deleted,
            'message': f'{deleted} catálogo(s) excluído(s) com sucesso.'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@catalog_bp.route('/link-sku-batch', methods=['POST'])
def link_sku_batch():
    """Vincula múltiplos catálogos a um SKU do inventário."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json() or {}
    sku = (data.get('sku') or '').strip().upper()
    catalog_items = data.get('catalog_items', [])
    user_id = session['user_id']

    if not sku:
        return jsonify({'error': 'SKU é obrigatório'}), 400
    if not catalog_items:
        return jsonify({'error': 'Nenhum catálogo informado para vinculação'}), 400

    linked_count = 0
    try:
        for item in catalog_items:
            if isinstance(item, str):
                cid = item.strip().upper()
                ctitle, curl, cimg = f'Catálogo {cid}', f'https://www.mercadolivre.com.br/p/{cid}', ''
            else:
                cid = str(item.get('catalog_id') or '').strip().upper()
                ctitle = item.get('title') or item.get('nome') or f'Catálogo {cid}'
                curl = item.get('url') or item.get('url_produto') or f'https://www.mercadolivre.com.br/p/{cid}'
                cimg = item.get('image') or item.get('imagem') or ''
            
            if cid:
                db_manager.link_catalog_to_sku(
                    user_id=user_id,
                    sku=sku,
                    catalog_id=cid,
                    catalog_title=ctitle,
                    catalog_url=curl,
                    catalog_image=cimg
                )
                linked_count += 1

        return jsonify({
            'success': True,
            'linked_count': linked_count,
            'sku': sku,
            'message': f'{linked_count} catálogo(s) vinculado(s) ao SKU {sku} com sucesso!'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@catalog_bp.route('/status/<search_id>')
def search_status(search_id):
    """Endpoint de polling — status da busca de catálogos."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    status = catalog_search_status.get(search_id, {
        'status': 'nao_encontrada',
        'error': 'Busca não encontrada',
        'completed': True,
    })
    return jsonify(status)


# ─── API — Scraping de sellers (assíncrona para ML e Amazon) ───────────────────

@catalog_bp.route('/<catalog_id>/scrape-sellers', methods=['POST'])
def scrape_sellers(catalog_id):
    """Inicia scraping de sellers de um catálogo específico (Mercado Livre ou Amazon)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    catalog_id = str(catalog_id).strip().upper()
    import re
    is_valid = bool(re.match(r'^MLB\d+$', catalog_id)) or bool(re.match(r'^[A-Z0-9]{10}$', catalog_id))
    if not is_valid:
        return jsonify({'error': 'ID de catálogo inválido'}), 400

    user_id = session['user_id']
    scrape_id = f"sellers_{catalog_id}_{int(time.time())}"
    is_amazon = not catalog_id.startswith('MLB')
    mp_name = "Amazon" if is_amazon else "Mercado Livre"

    catalog_sellers_status[scrape_id] = {
        'status': 'iniciando',
        'progress': 0,
        'message': f'Iniciando scraping de sellers do catálogo {catalog_id} ({mp_name})...',
        'sellers': [],
        'error': None,
        'login_required': False,
        'completed': False,
    }

    thread = threading.Thread(
        target=_scrape_sellers_thread,
        args=(scrape_id, user_id, catalog_id),
        daemon=True
    )
    thread.start()

    return jsonify({'scrape_id': scrape_id})


def _scrape_sellers_thread(scrape_id: str, user_id: str, catalog_id: str):
    """Thread de scraping de sellers suportando Mercado Livre e Amazon."""
    try:
        is_amazon = not catalog_id.startswith('MLB')
        mp_name = "Amazon" if is_amazon else "Mercado Livre"

        catalog_sellers_status[scrape_id].update({
            'status': 'buscando',
            'progress': 25,
            'message': f'Acessando página de concorrentes de {catalog_id} no {mp_name}...'
        })

        if is_amazon:
            res_amazon = get_amazon_catalog_sellers(catalog_id, user_id=user_id)
            sellers = res_amazon.get('sellers', [])
            if not sellers and res_amazon.get('error'):
                catalog_sellers_status[scrape_id].update({
                    'status': 'erro',
                    'error': res_amazon.get('error'),
                    'completed': True,
                })
                return
        else:
            sellers = []
            # 1. Tenta obter concorrentes via API Oficial do Mercado Livre (/products/{id}/items)
            try:
                comp_data = meli_catalog.get_catalog_competition(catalog_id, user_id=user_id)
                if comp_data.get('success') and comp_data.get('competitors'):
                    for idx, c in enumerate(comp_data['competitors']):
                        sellers.append({
                            'seller_name': c.get('seller_name') or f'Vendedor #{c.get("seller_id", idx+1)}',
                            'preco': float(c.get('price', 0.0)),
                            'posicao': 1 if c.get('is_buy_box_winner') else idx + 1,
                            'is_best_offer': bool(c.get('is_buy_box_winner')),
                            'frete_full': c.get('logistic_type') == 'fulfillment',
                            'condicao': c.get('condition', 'new'),
                            'reputation_level': c.get('reputation_level', 'none'),
                            'power_seller_status': c.get('power_seller_status'),
                            'city': c.get('city', ''),
                            'state': c.get('state', ''),
                            'url_vendedor': c.get('permalink', ''),
                            'catalog_id': catalog_id,
                            'coletado_em': datetime.now().isoformat()
                        })
                    # Ordena: Vencedor da Buy Box primeiro, seguido por menor preço
                    sellers.sort(key=lambda s: (not s.get('is_best_offer', False), s.get('preco', 999999)))
                    for idx, s in enumerate(sellers):
                        s['posicao'] = idx + 1
                    print(f"✅ [Catalog] {len(sellers)} vendedores enriquecidos via API Oficial Meli para {catalog_id}.")
            except Exception as e_api:
                print(f"⚠️ [Catalog] Falha ao obter concorrentes via API Meli: {e_api}")

            # 2. Se a API não retornou vendedores, executa fallback de scraping
            if not sellers:
                catalog_sellers_status[scrape_id].update({
                    'progress': 50,
                    'message': f'Consultando concorrentes via motor de busca secundário...'
                })
                result = get_catalog_sellers(catalog_id, user_id=user_id)
                if not result['success']:
                    catalog_sellers_status[scrape_id].update({
                        'status': 'erro',
                        'error': result.get('error', 'Nenhum concorrente encontrado'),
                        'login_required': result.get('login_required', False),
                        'completed': True,
                    })
                    return
                sellers = result.get('sellers', [])

            # Persiste sellers no Supabase
            if sellers:
                db_manager.save_catalog_sellers(catalog_id, sellers)

        catalog_sellers_status[scrape_id].update({
            'status': 'concluida',
            'progress': 100,
            'message': f'{len(sellers)} vendedor(es) encontrado(s) no {mp_name}.',
            'sellers': sellers,
            'completed': True,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        catalog_sellers_status[scrape_id].update({
            'status': 'erro',
            'error': str(e),
            'completed': True,
        })


@catalog_bp.route('/sellers-status/<scrape_id>')
@catalog_bp.route('/sellers/status/<scrape_id>')
def sellers_scrape_status(scrape_id):
    """Endpoint de polling — status do scraping de sellers."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    status = catalog_sellers_status.get(scrape_id, {
        'status': 'nao_encontrada',
        'error': 'Scraping não encontrado',
        'completed': True,
    })
    return jsonify(status)


@catalog_bp.route('/api/<catalog_id>/sellers')
def api_catalog_sellers(catalog_id):
    """Retorna lista de concorrentes/sellers cacheados no Supabase em formato JSON (MLB ou ASIN)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    catalog_id = str(catalog_id).strip().upper()
    import re
    is_valid = bool(re.match(r'^MLB\d+$', catalog_id)) or bool(re.match(r'^[A-Z0-9]{10}$', catalog_id))
    if not is_valid:
        return jsonify({'error': 'ID de catálogo inválido'}), 400

    catalog_data = db_manager.get_catalog_by_id(catalog_id)
    sellers = db_manager.get_catalog_sellers(catalog_id)

    min_price = 0.0
    winner_name = None
    if sellers:
        min_price = min((s.get('preco', 0) for s in sellers if s.get('preco', 0) > 0), default=0.0)
        best = next((s for s in sellers if s.get('is_best_offer') or s.get('posicao') == 1), sellers[0])
        winner_name = best.get('seller_name')

    return jsonify({
        'success': True,
        'catalog_id': catalog_id,
        'catalog': catalog_data,
        'sellers': sellers or [],
        'total_sellers': len(sellers or []),
        'min_price': min_price,
        'winner_name': winner_name
    })

