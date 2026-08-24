"""
Rotas e Endpoints de API dedicados à Extensão Chrome (Offer Search Assistant / In-Page Intel).
Fornece inteligência de catálogo, saldo em estoque, comparativo de margens e vinculação de SKUs.
"""

from flask import Blueprint, request, jsonify, session, current_app
from database.db_manager import DatabaseManager
from typing import Dict, List, Optional
import re

extension_bp = Blueprint('extension', __name__)
db_manager = DatabaseManager()


def _get_current_user_id() -> str:
    """Obtém user_id da sessão ativa ou de cabeçalhos/parâmetros"""
    user_id = session.get('user_id')
    if not user_id:
        # Fallback para token ou header enviado pela extensão
        user_id = request.headers.get('X-User-Id') or request.args.get('user_id') or "1"
    return str(user_id)


def _calculate_margin_metrics(cost: float, sell_price: float, fee_pct: float = 0.16, fixed_fee: float = 0.0) -> Dict:
    """Calcula margem líquida, lucro bruto e status competitivo"""
    cost = float(cost or 0.0)
    sell_price = float(sell_price or 0.0)
    
    if sell_price <= 0:
        return {
            'net_profit': 0.0,
            'margin_pct': 0.0,
            'marketplace_fee': 0.0,
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


@extension_bp.after_request
def add_cors_headers(response):
    """Permite requisições da extensão Chrome e páginas de marketplace"""
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-User-Id'
    return response


@extension_bp.route('/api/extension/product-intel', methods=['GET', 'OPTIONS'])
def get_product_intel():
    """
    Retorna a inteligência do produto/catálogo acessado no Mercado Livre ou Amazon:
    - Status de vinculação com SKU do estoque
    - Quantidade em estoque, custo de aquisição e preço de venda
    - Comparativo de margem frente ao preço da BuyBox
    """
    if request.method == 'OPTIONS':
        return jsonify({'ok': True}), 200

    catalog_id = (request.args.get('catalog_id') or '').strip().upper()
    item_id = (request.args.get('item_id') or '').strip().upper()
    url = (request.args.get('url') or '').strip()
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
    inventory = db_manager.get_inventory(user_id=user_id)
    inventory_by_sku = {str(inv.get('sku', '')).upper(): inv for inv in inventory}

    # Preço do concorrente / BuyBox na página
    current_price = 0.0
    if current_price_param:
        try:
            current_price = float(str(current_price_param).replace('R$', '').replace('.', '').replace(',', '.').strip())
        except (ValueError, TypeError):
            pass

    if matched_link:
        sku = str(matched_link.get('sku', '')).upper()
        inv_item = inventory_by_sku.get(sku, {})
        
        cost_price = float(inv_item.get('preco_custo') or 0.0)
        resale_price = float(inv_item.get('preco_site_pix') or inv_item.get('preco_venda') or 0.0)
        stock_qty = int(inv_item.get('estoque_total') or inv_item.get('estoque_unidades') or 0)
        
        buybox_price = current_price if current_price > 0 else float(matched_link.get('buybox_min_price') or 0.0)
        
        margin_analysis = _calculate_margin_metrics(cost=cost_price, sell_price=buybox_price)
        
        return jsonify({
            'is_linked': True,
            'catalog_id': catalog_id or matched_link.get('catalog_id'),
            'sku': sku,
            'descricao': inv_item.get('descricao') or matched_link.get('catalog_title') or 'Produto Cadastrado',
            'termo_comercial': inv_item.get('termo_comercial') or '',
            'estoque_total': stock_qty,
            'preco_custo': cost_price,
            'preco_venda': resale_price,
            'buybox_min_price': buybox_price,
            'buybox_winner': matched_link.get('buybox_winner') or 'Vencedor Atual',
            'sellers_count': matched_link.get('sellers_count') or 1,
            'margin': margin_analysis,
            'app_catalog_url': f"/catalog?sku={sku}"
        }), 200

    # Se não está vinculado, retorna status desvinculado e sugestões de SKUs rápidos
    top_suggestions = [
        {
            'sku': item.get('sku'),
            'descricao': item.get('descricao'),
            'estoque_total': item.get('estoque_total') or item.get('estoque_unidades') or 0,
            'preco_custo': float(item.get('preco_custo') or 0.0),
            'preco_venda': float(item.get('preco_site_pix') or item.get('preco_venda') or 0.0)
        }
        for item in inventory[:15]
    ]

    return jsonify({
        'is_linked': False,
        'catalog_id': catalog_id or item_id,
        'current_price': current_price,
        'suggestions': top_suggestions
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
    
    inventory = db_manager.get_inventory(user_id=user_id)
    
    if q:
        inventory = [
            item for item in inventory
            if q in str(item.get('sku', '')).lower() or q in str(item.get('descricao', '')).lower() or q in str(item.get('termo_comercial', '')).lower()
        ]

    formatted_list = [
        {
            'sku': item.get('sku'),
            'descricao': item.get('descricao'),
            'termo_comercial': item.get('termo_comercial') or '',
            'estoque_total': int(item.get('estoque_total') or item.get('estoque_unidades') or 0),
            'preco_custo': float(item.get('preco_custo') or 0.0),
            'preco_venda': float(item.get('preco_site_pix') or item.get('preco_venda') or 0.0)
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
        inventory = db_manager.get_inventory(user_id=user_id)
        inv_item = next((item for item in inventory if str(item.get('sku', '')).upper() == sku), {})
        
        cost_price = float(inv_item.get('preco_custo') or 0.0)
        resale_price = float(inv_item.get('preco_site_pix') or inv_item.get('preco_venda') or 0.0)
        stock_qty = int(inv_item.get('estoque_total') or inv_item.get('estoque_unidades') or 0)
        
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
