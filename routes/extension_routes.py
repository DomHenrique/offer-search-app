"""
Rotas e Endpoints de API dedicados à Extensão Chrome (Offer Search Assistant / In-Page Intel).
Fornece inteligência de catálogo, saldo em estoque, comparativo de margens e vinculação de SKUs.
"""

from flask import Blueprint, request, jsonify, session, current_app
from database.db_manager import DatabaseManager
from services.inventory_matcher import InventoryMatcher
from typing import Dict, List, Optional
import re

extension_bp = Blueprint('extension', __name__)
db_manager = DatabaseManager()
matcher = InventoryMatcher(db_manager=db_manager)


def _get_current_user_id() -> str:
    """Obtém user_id da sessão ativa ou de cabeçalhos/parâmetros com fallback inteligente"""
    user_id = session.get('user_id')
    if not user_id:
        user_id = request.headers.get('X-User-Id') or request.args.get('user_id')
    if not user_id:
        try:
            u_res = db_manager.supabase.table("users").select("id").eq("ativo", True).limit(1).execute()
            if u_res.data:
                user_id = str(u_res.data[0]["id"])
        except Exception:
            pass
    return str(user_id or "1")


def _calculate_margin_metrics(cost: float, sell_price: float, fee_pct: float = 0.16, fixed_fee: float = 0.0) -> Dict:
    """Calcula margem líquida, lucro bruto e status competitivo"""
    cost = float(cost or 0.0)
    sell_price = float(sell_price or 0.0)
    fee_pct = float(fee_pct or 0.16)
    fixed_fee = float(fixed_fee or 0.0)
    
    # Se preço de venda for abaixo de R$ 79 e não houver fixed_fee especificado, aplica taxa fixa do ML
    if 0 < sell_price < 79.0 and fixed_fee == 0.0:
        fixed_fee = 6.0
    
    if sell_price <= 0:
        return {
            'net_profit': 0.0,
            'margin_pct': 0.0,
            'marketplace_fee': 0.0,
            'fixed_fee': fixed_fee,
            'fee_pct': fee_pct,
            'status': 'NO_PRICE',
            'status_label': 'Sem Preço de Venda',
            'status_color': '#94a3b8'
        }
        
    marketplace_fee = round((sell_price * fee_pct) + fixed_fee, 2)
    net_profit = round(sell_price - marketplace_fee - cost, 2)
    margin_pct = round((net_profit / sell_price) * 100, 1) if sell_price > 0 else 0.0
    
    if cost <= 0:
        status = 'NO_COST'
        status_label = 'Custo Não Cadastrado'
        status_color = '#64748b'
    elif net_profit > 0 and margin_pct >= 15.0:
        status = 'EXCELLENT_MARGIN'
        status_label = '🔥 Alta Margem de Lucro'
        status_color = '#10b981'
    elif net_profit > 0:
        status = 'PROFITABLE'
        status_label = '🟢 Lucrativo'
        status_color = '#22c55e'
    elif net_profit == 0:
        status = 'BREAK_EVEN'
        status_label = '⚪ Ponto de Equilíbrio'
        status_color = '#f59e0b'
    else:
        status = 'NEGATIVE_MARGIN'
        status_label = '🔴 Abaixo do Custo / Prejuízo'
        status_color = '#ef4444'
        
    return {
        'net_profit': net_profit,
        'margin_pct': margin_pct,
        'marketplace_fee': marketplace_fee,
        'status': status,
        'status_label': status_label,
        'status_color': status_color
    }


def build_meli_sell_similar_url(catalog_id: str = None, item_id: str = None) -> str:
    """
    Constrói a URL oficial do fluxo 'Vender um igual' (SYI) do Mercado Livre.
    Padrão oficial: https://www.mercadolivre.com.br/syi/core/list/equals?itemId=MLB...&productId=MLB...
    """
    params = []
    if item_id:
        clean_item = str(item_id).replace("-", "").strip()
        params.append(f"itemId={clean_item}")
    if catalog_id:
        clean_cat = str(catalog_id).strip()
        params.append(f"productId={clean_cat}")

    if not params:
        return ""

    query = "&".join(params)
    return f"https://www.mercadolivre.com.br/syi/core/list/equals?{query}"


@extension_bp.after_request
def add_cors_headers(response):
    """Permite requisições da extensão Chrome e páginas de marketplace"""
    origin = request.headers.get('Origin')
    if origin:
        response.headers['Access-Control-Allow-Origin'] = origin
    else:
        response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-User-Id'
    return response


@extension_bp.route('/api/extension/product-intel', methods=['GET', 'OPTIONS'])
def get_product_intel():
    """
    Retorna a inteligência do produto/catálogo acessado no Mercado Livre ou Amazon:
    - Status de vinculação com SKU do estoque
    - Matching inteligente de SKU com InventoryMatcher (EAN, Marca/Modelo, Título)
    - Quantidade em estoque, custo de aquisição e preço de venda
    - Comparativo e simulação de margem frente ao preço da BuyBox
    """
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200

    catalog_id = (request.args.get('catalog_id') or '').strip().upper()
    item_id = (request.args.get('item_id') or '').strip().upper()
    url = (request.args.get('url') or '').strip()
    title = (request.args.get('title') or '').strip()
    brand = (request.args.get('brand') or '').strip()
    model = (request.args.get('model') or '').strip()
    gtin = (request.args.get('gtin') or '').strip()
    marketplace = (request.args.get('marketplace') or 'mercadolivre').strip().lower()
    fee_pct = float(request.args.get('fee_pct') or 0.16)
    current_price_param = request.args.get('current_price')

    user_id = _get_current_user_id()
    
    # 1. Busca vínculo existente em sku_catalogs
    all_links = db_manager.get_sku_catalogs(user_id=user_id)
    matched_link = None
    
    if catalog_id:
        matched_link = next((item for item in all_links if item.get('catalog_id', '').upper() == catalog_id), None)
    
    if not matched_link and item_id:
        matched_link = next((item for item in all_links if item.get('catalog_id', '').upper() == item_id or item_id in (item.get('catalog_url') or '')), None)

    # 2. Busca inventário do usuário
    inventory = db_manager.get_consolidated_inventory(user_id=user_id)
    normalize_sku = lambda s: re.sub(r'[^A-Za-z0-9]', '', str(s or '')).upper()
    inventory_by_norm_sku = {normalize_sku(inv.get('sku')): inv for inv in inventory}

    # Preço do concorrente / BuyBox na página
    current_price = 0.0
    if current_price_param:
        try:
            current_price = float(str(current_price_param).replace('R$', '').replace('.', '').replace(',', '.').strip())
        except (ValueError, TypeError):
            pass

    # Executa o InventoryMatcher com os dados extraídos da página
    extracted_data = {
        'listing_id': catalog_id or item_id,
        'title': title,
        'brand': brand,
        'model': model,
        'gtin': gtin
    }
    raw_matches = matcher.find_matches_for_listing(user_id=user_id, extracted_data=extracted_data, limit=6)
    
    ranked_suggestions = []
    for cand in raw_matches:
        cand_cost = float(cand.get('preco_custo') or 0.0)
        cand_resale = float(cand.get('preco_revenda') or 0.0)
        cand_margin = _calculate_margin_metrics(cost=cand_cost, sell_price=current_price, fee_pct=fee_pct)
        ranked_suggestions.append({
            'sku': cand.get('sku'),
            'descricao': cand.get('descricao'),
            'termo_busca': cand.get('termo_busca'),
            'estoque_total': int(cand.get('quantidade_total') or 0),
            'preco_custo': cand_cost,
            'preco_venda': cand_resale,
            'image_url': cand.get('image_url') or '',
            'match_score': cand.get('match_score', 0),
            'match_tier': cand.get('match_tier', 'NONE'),
            'match_badge': cand.get('match_badge', ''),
            'reasons': cand.get('reasons', []),
            'margin': cand_margin
        })

    # Se não houver matches com score, preenche com os primeiros itens do inventário
    if not ranked_suggestions and inventory:
        for item in inventory[:6]:
            i_cost = float(item.get('preco_custo') or 0.0)
            i_resale = float(item.get('preco_site_pix') or item.get('preco_revenda') or 0.0)
            ranked_suggestions.append({
                'sku': item.get('sku'),
                'descricao': item.get('descricao'),
                'termo_busca': item.get('termo_busca') or '',
                'estoque_total': int(item.get('quantidade_total') or item.get('estoque_total') or 0),
                'preco_custo': i_cost,
                'preco_venda': i_resale,
                'image_url': '',
                'match_score': 0,
                'match_tier': 'NONE',
                'match_badge': '',
                'reasons': [],
                'margin': _calculate_margin_metrics(cost=i_cost, sell_price=current_price, fee_pct=fee_pct)
            })

    best_match = ranked_suggestions[0] if (ranked_suggestions and ranked_suggestions[0].get('match_score', 0) >= 50) else None

    # URL oficial para "Vender um Igual" no Mercado Livre (Fluxo SYI)
    sell_similar_url = build_meli_sell_similar_url(catalog_id=catalog_id, item_id=item_id)

    if matched_link:
        sku = str(matched_link.get('sku', '')).strip().upper()
        norm_sku = normalize_sku(sku)
        inv_item = inventory_by_norm_sku.get(norm_sku, {})
        
        cost_price = float(inv_item.get('preco_custo') or 0.0)
        resale_price = float(inv_item.get('preco_site_pix') or inv_item.get('preco_revenda') or 0.0)
        stock_qty = int(inv_item.get('quantidade_total') or inv_item.get('estoque_total') or 0)
        
        buybox_price = current_price if current_price > 0 else float(matched_link.get('buybox_min_price') or 0.0)
        margin_analysis = _calculate_margin_metrics(cost=cost_price, sell_price=buybox_price, fee_pct=fee_pct)
        
        return jsonify({
            'is_linked': True,
            'catalog_id': catalog_id or matched_link.get('catalog_id'),
            'sku': sku,
            'descricao': inv_item.get('descricao') or matched_link.get('catalog_title') or 'Produto Cadastrado',
            'termo_comercial': inv_item.get('termo_busca') or inv_item.get('termo_comercial') or '',
            'estoque_total': stock_qty,
            'preco_custo': cost_price,
            'preco_venda': resale_price,
            'buybox_min_price': buybox_price,
            'buybox_winner': matched_link.get('buybox_winner') or 'Vencedor Atual',
            'sellers_count': matched_link.get('sellers_count') or 1,
            'margin': margin_analysis,
            'app_catalog_url': f"/catalog?sku={sku}",
            'sell_similar_url': sell_similar_url,
            'suggestions': ranked_suggestions
        }), 200

    # Se não está vinculado, retorna status desvinculado e sugestões ordenadas pelo matcher
    return jsonify({
        'is_linked': False,
        'catalog_id': catalog_id or item_id,
        'current_price': current_price,
        'best_match': best_match,
        'suggestions': ranked_suggestions,
        'sell_similar_url': sell_similar_url
    }), 200


@extension_bp.route('/api/extension/simulate-margin', methods=['GET', 'POST', 'OPTIONS'])
def simulate_margin():
    """
    Simula dinamicamente a margem de lucro dado um preço de venda e um custo de SKU.
    """
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200

    data = request.get_json(silent=True) if request.method == 'POST' else {}
    if not data:
        data = request.args

    cost = float(data.get('cost') or data.get('preco_custo') or 0.0)
    sell_price = float(data.get('sell_price') or data.get('preco_venda') or 0.0)
    fee_pct = float(data.get('fee_pct') or 0.16)
    fixed_fee = float(data.get('fixed_fee') or 0.0)

    margin = _calculate_margin_metrics(cost=cost, sell_price=sell_price, fee_pct=fee_pct, fixed_fee=fixed_fee)
    return jsonify({
        'success': True,
        'margin': margin
    }), 200


@extension_bp.route('/api/extension/inventory-list', methods=['GET', 'OPTIONS'])
def get_extension_inventory_list():
    """
    Retorna a lista de SKUs ativos no estoque para autocompletação e busca no widget in-page.
    """
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200

    q = (request.args.get('q') or '').strip().lower()
    user_id = _get_current_user_id()
    
    inventory = db_manager.get_consolidated_inventory(user_id=user_id)
    
    if q:
        inventory = [
            item for item in inventory
            if q in str(item.get('sku', '')).lower() or q in str(item.get('descricao', '')).lower() or q in str(item.get('termo_busca', '')).lower()
        ]

    formatted_list = [
        {
            'sku': item.get('sku'),
            'descricao': item.get('descricao'),
            'termo_comercial': item.get('termo_busca') or item.get('termo_comercial') or '',
            'estoque_total': int(item.get('quantidade_total') or item.get('estoque_total') or 0),
            'preco_custo': float(item.get('preco_custo') or 0.0),
            'preco_venda': float(item.get('preco_site_pix') or item.get('preco_revenda') or 0.0)
        }
        for item in inventory[:40]
    ]

    return jsonify({
        'total': len(formatted_list),
        'items': formatted_list
    }), 200


@extension_bp.route('/api/extension/link-sku', methods=['POST', 'OPTIONS'])
def link_sku_from_extension():
    """
    Persiste o vínculo entre o catálogo da página e o SKU selecionado pelo usuário.
    """
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200

    data = request.get_json(force=True, silent=True) or {}
    catalog_id = (data.get('catalog_id') or '').strip().upper()
    sku = (data.get('sku') or '').strip().upper()
    
    if not catalog_id or not sku:
        return jsonify({'success': False, 'error': 'Catalog ID e SKU são obrigatórios.'}), 400

    user_id = _get_current_user_id()
    
    catalog_title = data.get('catalog_title') or f"Catálogo {catalog_id}"
    catalog_url = data.get('catalog_url') or f"https://www.mercadolivre.com.br/p/{catalog_id}"
    catalog_image = data.get('catalog_image') or ''
    buybox_winner = data.get('buybox_winner') or ''
    buybox_min_price = float(data.get('buybox_min_price') or 0.0)
    sellers_count = int(data.get('sellers_count') or 1)

    try:
        saved = db_manager.link_catalog_to_sku(
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

        # Obtém dados do inventário para responder imediatamente com o intel completo
        inventory = db_manager.get_consolidated_inventory(user_id=user_id)
        normalize_sku = lambda s: re.sub(r'[^A-Za-z0-9]', '', str(s or '')).upper()
        norm_sku = normalize_sku(sku)
        inv_item = next((item for item in inventory if normalize_sku(item.get('sku')) == norm_sku), {})
        
        cost_price = float(inv_item.get('preco_custo') or 0.0)
        resale_price = float(inv_item.get('preco_site_pix') or inv_item.get('preco_revenda') or 0.0)
        stock_qty = int(inv_item.get('quantidade_total') or inv_item.get('estoque_total') or 0)
        
        margin_analysis = _calculate_margin_metrics(cost=cost_price, sell_price=buybox_min_price)

        return jsonify({
            'success': True,
            'message': f'Catálogo {catalog_id} vinculado ao SKU {sku} com sucesso!',
            'product_intel': {
                'is_linked': True,
                'catalog_id': catalog_id,
                'sku': sku,
                'descricao': inv_item.get('descricao') or catalog_title,
                'estoque_total': stock_qty,
                'preco_custo': cost_price,
                'preco_venda': resale_price,
                'buybox_min_price': buybox_min_price,
                'buybox_winner': buybox_winner,
                'sellers_count': sellers_count,
                'margin': margin_analysis
            }
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@extension_bp.route('/api/extension/scan-search-page', methods=['POST', 'OPTIONS'])
def scan_search_page():
    """
    Escaneia em lote múltiplos cartões de produtos da página de busca do Mercado Livre.
    Cruza com catálogos vinculados e executa InventoryMatcher para identificar itens do estoque próprio.
    """
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200

    data = request.get_json(force=True, silent=True) or {}
    items = data.get('items') or []
    if not items:
        return jsonify({'success': True, 'total_scanned': 0, 'results': {}}), 200

    user_id = _get_current_user_id()

    # Pre-carrega catálogos vinculados e inventário para processar a página em memória
    all_links = db_manager.get_sku_catalogs(user_id=user_id)
    linked_by_catalog = {
        str(l.get('catalog_id') or '').strip().upper(): l
        for l in all_links if l.get('catalog_id')
    }

    inventory = db_manager.get_consolidated_inventory(user_id=user_id)
    normalize_sku = lambda s: re.sub(r'[^A-Za-z0-9]', '', str(s or '')).upper()
    inventory_by_norm_sku = {normalize_sku(inv.get('sku')): inv for inv in inventory}

    results = {}
    total_catalogs = 0
    total_in_stock = 0

    for item in items:
        card_id = str(item.get('id') or item.get('client_id') or item.get('url') or '')
        catalog_id = str(item.get('catalog_id') or '').strip().upper()
        item_id = str(item.get('item_id') or '').strip().upper()
        title = str(item.get('title') or '').strip()
        price = float(item.get('price') or 0.0)
        is_catalog = bool(catalog_id)
        if is_catalog:
            total_catalogs += 1

        matched_link = linked_by_catalog.get(catalog_id) if catalog_id else None

        if matched_link:
            sku = str(matched_link.get('sku') or '').strip().upper()
            inv_item = inventory_by_norm_sku.get(normalize_sku(sku), {})
            cost = float(inv_item.get('preco_custo') or 0.0)
            stock_qty = int(inv_item.get('quantidade_total') or inv_item.get('estoque_total') or 0)
            margin = _calculate_margin_metrics(cost=cost, sell_price=price)
            if stock_qty > 0 or cost > 0:
                total_in_stock += 1

            results[card_id] = {
                'is_catalog': True,
                'catalog_id': catalog_id,
                'is_linked': True,
                'sku': sku,
                'descricao': inv_item.get('descricao') or matched_link.get('catalog_title') or title,
                'estoque_total': stock_qty,
                'preco_custo': cost,
                'margin': margin,
                'sell_similar_url': build_meli_sell_similar_url(catalog_id=catalog_id, item_id=item_id)
            }
        else:
            # Não vinculado: roda o matcher para tentar achar correspondência no estoque
            extracted_data = {
                'listing_id': catalog_id or item_id,
                'title': title
            }
            matches = matcher.find_matches_for_listing(user_id=user_id, extracted_data=extracted_data, limit=1)
            best_match = matches[0] if (matches and matches[0].get('match_score', 0) >= 50) else None

            match_info = None
            if best_match:
                cost = float(best_match.get('preco_custo') or 0.0)
                margin = _calculate_margin_metrics(cost=cost, sell_price=price)
                total_in_stock += 1
                match_info = {
                    'sku': best_match.get('sku'),
                    'descricao': best_match.get('descricao'),
                    'estoque_total': int(best_match.get('quantidade_total') or 0),
                    'preco_custo': cost,
                    'match_score': best_match.get('match_score'),
                    'match_badge': best_match.get('match_badge'),
                    'margin': margin
                }

            sell_similar_url = build_meli_sell_similar_url(catalog_id=catalog_id, item_id=item_id) if is_catalog else ""

            results[card_id] = {
                'is_catalog': is_catalog,
                'catalog_id': catalog_id,
                'is_linked': False,
                'has_stock_match': bool(best_match),
                'match': match_info,
                'sell_similar_url': sell_similar_url
            }

    return jsonify({
        'success': True,
        'total_scanned': len(items),
        'total_catalogs': total_catalogs,
        'total_in_stock': total_in_stock,
        'results': results
    }), 200
