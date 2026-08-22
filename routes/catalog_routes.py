from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import threading
import time
from datetime import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from scraping.web_scrap_catalog_ml import get_catalog_list, get_catalog_sellers
from scraping.web_scrap_amazon_catalog import get_amazon_catalog_sellers

catalog_bp = Blueprint('catalog', __name__)
db_manager = DatabaseManager()

# Armazena status das buscas em andamento (em memória)
catalog_search_status = {}
catalog_sellers_status = {}


# ─── Páginas ──────────────────────────────────────────────────────────────────

@catalog_bp.route('/')
def catalog_list():
    """Página principal de catálogos — listagem e busca."""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']

    # Catálogos já salvos do usuário (agrupados por termo de pesquisa)
    saved_catalogs = db_manager.get_user_catalogs(user_id, limit=200)

    # Agrupa os catálogos pelo termo que os originou
    from collections import OrderedDict
    grouped_catalogs = OrderedDict()
    for cat in saved_catalogs:
        raw_term = (cat.get('termo_pesquisa') or '').strip()
        term = raw_term if raw_term else 'Outros / Sem termo associado'
        if term not in grouped_catalogs:
            grouped_catalogs[term] = []
        grouped_catalogs[term].append(cat)

    return render_template('catalog/catalog_list.html',
                           saved_catalogs=saved_catalogs,
                           grouped_catalogs=grouped_catalogs)


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
    """Extrai catálogos do Mercado Livre e Amazon a partir das ofertas salvas no banco de dados"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    try:
        user_id = session['user_id']
        catalogs = db_manager.extract_and_save_catalogs_from_offers(user_id=user_id)
        return jsonify({
            'success': True,
            'count': len(catalogs),
            'catalogs': catalogs,
            'message': f"{len(catalogs)} catálogo(s) sincronizado(s) com sucesso a partir do histórico de ofertas!"
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── API — Busca de catálogos (assíncrona) ───────────────────────────────────

@catalog_bp.route('/search', methods=['POST'])
def search_catalogs():
    """Inicia busca de catálogos por termo em thread de background."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json()
    search_term = (data.get('termo_pesquisa') or '').strip()
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
        args=(search_id, user_id, search_term, n_pages),
        daemon=True
    )
    thread.start()

    return jsonify({'search_id': search_id})


def _search_catalogs_thread(search_id: str, user_id: str, search_term: str, n_pages: int):
    """Thread de busca de catálogos."""
    try:
        catalog_search_status[search_id].update({
            'status': 'buscando',
            'progress': 20,
            'message': f'Buscando catálogos para "{search_term}" no Mercado Livre...'
        })

        result = get_catalog_list(search_term, n_pages)

        if not result['success']:
            catalog_search_status[search_id].update({
                'status': 'erro',
                'error': result.get('error', 'Erro desconhecido'),
                'completed': True,
            })
            return

        catalogs = result['catalogs']

        catalog_search_status[search_id].update({
            'progress': 70,
            'message': f'Salvando {len(catalogs)} catálogos...'
        })

        # Persiste catálogos no Supabase
        for cat in catalogs:
            db_manager.save_catalog({
                'catalog_id': cat['catalog_id'],
                'nome': cat['nome'],
                'imagem': cat['imagem'],
                'termo_pesquisa': search_term,
                'user_id': user_id,
            })

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
            result = get_catalog_sellers(catalog_id, user_id=user_id)
            if not result['success']:
                catalog_sellers_status[scrape_id].update({
                    'status': 'erro',
                    'error': result.get('error', 'Erro desconhecido'),
                    'login_required': result.get('login_required', False),
                    'completed': True,
                })
                return
            sellers = result['sellers']
            # Persiste sellers no Supabase
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

