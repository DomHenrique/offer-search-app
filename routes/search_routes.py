from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import time
import threading
from datetime import datetime
import sys
import os
import re
import pandas as pd

# Adiciona o diretório raiz ao path para importar módulos de scraping
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from utils.helpers import clean_search_term, safe_int
from scraping.run_scraper import buscar_e_salvar_ofertas
from utils.simple_cache import cache
from utils.bulk_processor import BulkProcessor

search_bp = Blueprint('search', __name__)
db_manager = DatabaseManager()

# Armazena status das buscas em andamento
search_status = {}

@search_bp.route('', strict_slashes=False)
@search_bp.route('/', strict_slashes=False)
def search_page():
    """Página principal de busca - Redirecionada para a central de Catálogos"""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))
    
    query_args = request.args.to_dict()
    return redirect(url_for('catalog.catalog_list', **query_args))

@search_bp.route('/execute', methods=['POST'])
def execute_search():
    """Executa busca de ofertas"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    data = request.get_json()
    termo_pesquisa = clean_search_term(data.get('termo_pesquisa', ''))
    paginas_ml = safe_int(data.get('paginas_ml', 1), 1)
    
    if not termo_pesquisa:
        return jsonify({'error': 'Termo de pesquisa é obrigatório'}), 400
    
    if len(termo_pesquisa) < 2:
        return jsonify({'error': 'Termo de pesquisa deve ter pelo menos 2 caracteres'}), 400
    
    user_id = session['user_id']
    user_email = session.get('user_email') or 'usuario@sistema'
    search_id = f"{user_id}_{int(time.time())}"

    # Verifica cache antes de iniciar nova busca (apenas se tiver resultados)
    cache_key = f"search:{user_id}:{termo_pesquisa}"
    cached = cache.get(cache_key)
    if cached and cached.get('results') and len(cached['results']) > 0:
        # Se houver cache válido com resultados, retorna o search_id e marca como concluído
        search_status[search_id] = {
            'status': 'concluida',
            'progress': 100,
            'message': 'Busca carregada do cache.',
            'results': cached['results'],
            'stats': cached['stats'],
            'error': None,
            'completed': True
        }
        return jsonify({'search_id': search_id})

    # Inicializa status da busca
    search_status[search_id] = {
        'status': 'iniciando',
        'progress': 0,
        'message': 'Preparando busca...',
        'results': [],
        'error': None,
        'completed': False
    }

    # Inicia busca em thread separada
    thread = threading.Thread(
        target=_execute_search_thread,
        args=(search_id, user_id, user_email, termo_pesquisa, paginas_ml)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'search_id': search_id})

def _execute_search_thread(search_id, user_id, user_email, termo_pesquisa, paginas_ml):
    """Executa busca em thread separada"""
    try:
        print(f"🚀 Iniciando thread de busca para search_id: {search_id}")
        
        # Atualiza status
        search_status[search_id].update({
            'status': 'buscando',
            'progress': 10,
            'message': 'Configurando ambiente...'
        })
        print(f"📊 Status atualizado para 'buscando': {search_status[search_id]}")
        
        # Busca configurações do usuário
        configs = db_manager.get_user_configs(user_id)
        config_dict = {config['chave']: config['valor'] for config in configs}
        print(f"⚙️ Configurações do usuário: {config_dict}")
        
        # Verifica configurações (SerpApi agora é opcional/fallback)
        if not config_dict.get('SERPAPI_KEY'):
            print("⚠️ SERPAPI_KEY não configurada (Fallback desativado para esta busca)")
        
        # Configura variáveis de ambiente temporariamente
        original_env = {}
        for key, value in config_dict.items():
            if value:
                original_env[key] = os.environ.get(key)
                os.environ[key] = value
        
        try:
            # Atualiza progresso
            search_status[search_id].update({
                'progress': 30,
                'message': 'Buscando produtos na Amazon...'
            })
            print(f"📊 Progresso atualizado para 30%: {search_status[search_id]}")
            
            # Executa busca
            start_time = time.time()
            results = buscar_e_salvar_ofertas(termo_pesquisa, paginas_ml, user_id=str(user_id))
            execution_time = int(time.time() - start_time)
            print(f"⏱️ Busca concluída em {execution_time} segundos, {len(results)} resultados")
            
            # Atualiza progresso
            search_status[search_id].update({
                'progress': 80,
                'message': 'Processando resultados...'
            })
            print(f"📊 Progresso atualizado para 80%: {search_status[search_id]}")
            
            # Verifica se foi utilizado termo relaxado
            relaxed_used = None
            if hasattr(results, 'columns') and 'RELAXED_QUERY_USED' in results.columns:
                non_empty = results['RELAXED_QUERY_USED'].dropna()
                if not non_empty.empty:
                    relaxed_used = str(non_empty.iloc[0])

            # Determina status do log e telemetria por marketplace
            log_status = 'SUCCESS'
            if len(results) == 0:
                log_status = 'EMPTY'
            elif relaxed_used:
                log_status = 'FALLBACK_RECOVERED'

            # Busca resultados do banco para exibir
            print(f"🔍 Buscando ofertas do banco para termo: {termo_pesquisa}")
            ofertas = []
            try:
                ofertas_response = db_manager.supabase.table("ofertas").select("*").eq("termo_pesquisa", termo_pesquisa).order("score_produto", desc=True).limit(50).execute()
                ofertas = ofertas_response.data or []
                if not ofertas and relaxed_used:
                    ofertas_resp_relaxed = db_manager.supabase.table("ofertas").select("*").eq("termo_pesquisa", relaxed_used).order("score_produto", desc=True).limit(50).execute()
                    ofertas = ofertas_resp_relaxed.data or []
            except Exception as e_fetch:
                print(f"Aviso ao consultar ofertas salvas: {e_fetch}")

            # Se o banco ainda não retornou mas o scraper coletou dados, usa os dados do scraper diretamente
            if not ofertas and results:
                print("ℹ️ Usando resultados diretos do scraper para exibição imediata")
                ofertas = results if isinstance(results, list) else results.to_dict('records')

            # Calcula estatísticas e telemetria
            amazon_count = int(len([r for r in ofertas if (r.get('marketplace') or '').lower() == 'amazon']) or 0)
            ml_count = int(len([r for r in ofertas if (r.get('marketplace') or '').lower() in ('mercadolivre', 'mercado livre', 'mercado_livre')]) or 0)
            total_count = int(len(ofertas) or 0)

            ml_status = 'SUCCESS' if ml_count > 0 else ('EMPTY' if total_count == 0 else 'FAILED')
            amazon_status = 'SUCCESS' if amazon_count > 0 else ('EMPTY' if total_count == 0 else 'FAILED')
            
            telemetry = {
                'amazon': {'status': amazon_status, 'count': amazon_count},
                'mercadolivre': {'status': ml_status, 'count': ml_count}
            }

            # Grava log estruturado no banco
            error_msg = None
            if ml_count == 0 and amazon_count > 0:
                error_msg = "Mercado Livre retornou 0 ofertas (possível bloqueio/timeout). Amazon retornou com sucesso."
            elif amazon_count == 0 and ml_count > 0:
                error_msg = "Amazon retornou 0 ofertas. Mercado Livre retornou com sucesso."

            db_manager.save_search_log({
                'user_id': user_id,
                'user_email': user_email,
                'termo_original': termo_pesquisa,
                'termo_utilizado': relaxed_used or termo_pesquisa,
                'status': log_status,
                'total_ofertas': total_count,
                'ml_ofertas': ml_count,
                'amazon_ofertas': amazon_count,
                'tempo_execucao_segundos': round(execution_time, 2),
                'error_message': error_msg
            })

            stats = {
                'total_produtos': total_count,
                'amazon_produtos': amazon_count,
                'ml_produtos': ml_count,
                'preco_medio': float(sum(r.get('preco_numerico', 0) or 0 for r in ofertas) / total_count) if total_count > 0 else 0.0,
                'preco_minimo': float(min((r.get('preco_numerico', 0) or 0) for r in ofertas)) if total_count > 0 else 0.0,
                'preco_maximo': float(max((r.get('preco_numerico', 0) or 0) for r in ofertas)) if total_count > 0 else 0.0,
                'tempo_execucao': int(execution_time or 0),
                'relaxed_query_used': relaxed_used,
                'telemetry': telemetry
            }
            print(f"📈 Estatísticas: {stats}")
            
            # Salva no histórico
            history_id = db_manager.save_search_history(user_id, termo_pesquisa, stats)
            print(f"💾 ID do histórico salvo: {history_id}")
            print(f"✅ Encontradas {len(ofertas)} ofertas para exibição")
            
            # Finaliza busca
            search_status[search_id].update({
                'status': 'concluida',
                'progress': 100,
                'message': f'Busca concluída! {len(ofertas)} produtos encontrados.' + (f' (Termo otimizado: "{relaxed_used}")' if relaxed_used else ''),
                'results': ofertas,
                'stats': stats,
                'telemetry': telemetry,
                'relaxed_query_used': relaxed_used,
                'completed': True
            })
            # Salva no cache apenas se houver ofertas reais
            if ofertas:
                cache_key = f"search:{user_id}:{termo_pesquisa}"
                cache.set(cache_key, {'results': ofertas, 'stats': stats, 'telemetry': telemetry})
            print(f"🎉 Busca concluída com sucesso: {search_status[search_id]}")
            
        finally:
            # Restaura variáveis de ambiente
            for key, original_value in original_env.items():
                if original_value is not None:
                    os.environ[key] = original_value
                elif key in os.environ:
                    del os.environ[key]
    
    except Exception as e:
        print(f"❌ Erro na thread de busca: {e}")
        import traceback
        traceback.print_exc()

        # Grava log de erro no banco
        try:
            db_manager.save_search_log({
                'user_id': user_id,
                'user_email': user_email,
                'termo_original': termo_pesquisa,
                'termo_utilizado': termo_pesquisa,
                'status': 'ERROR',
                'total_ofertas': 0,
                'ml_ofertas': 0,
                'amazon_ofertas': 0,
                'tempo_execucao_segundos': 0.0,
                'error_message': str(e)
            })
        except Exception:
            pass

        search_status[search_id].update({
            'status': 'erro',
            'error': str(e),
            'completed': True
        })

@search_bp.route('/status/<search_id>')
def search_status_endpoint(search_id):
    """Retorna status da busca"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    status = search_status.get(search_id, {
        'status': 'nao_encontrada',
        'error': 'Busca não encontrada',
        'completed': True
    })
    
    return jsonify(status)

def enrich_product_intel(produto: dict) -> dict:
    """Enriquece o produto com métricas financeiras e de concorrência inspiradas no Avant Pro"""
    import re
    p = dict(produto)
    url = p.get('url_produto') or p.get('link') or ''
    title = p.get('titulo') or ''
    price = float(p.get('preco_numerico') or 0)
    reviews = int(p.get('avaliacoes') or p.get('num_avaliacoes') or 0)
    
    # Normaliza o campo marketplace (scraper entrega MARKETPLACE uppercase)
    raw_mp = p.get('marketplace') or p.get('MARKETPLACE') or ''
    raw_mp_lower = raw_mp.lower().strip()
    if 'amazon' in raw_mp_lower or 'amazon.com' in url.lower():
        p['marketplace'] = 'Amazon'
    else:
        p['marketplace'] = 'MercadoLivre'
    
    # 1. Classificação Precisa de Catálogo com Concorrência de Sellers vs Anúncio de Vendedor Único
    # Mercado Livre: catálogo oficial (/p/MLB...)
    # Amazon: produto com ASIN (/dp/ASIN) e múltiplas opções de compra
    is_user_post = '/up/' in url or 'MLBU' in url
    
    # Extrai o Catalog ID se houver (Mercado Livre ou Amazon ASIN)
    # Prioridade: URL /p/MLB > campo CATALOG_ID do scraper > catalog_id do banco > ASIN
    cat_match = re.search(r'/p/(MLB\d+)', url)
    asin_match = re.search(r'/dp/([A-Z0-9]{10})', url) or re.search(r'([A-Z0-9]{10})', str(p.get('codigo_produto') or p.get('ASIN') or ''))
    
    is_amazon = (p.get('marketplace') or p.get('MARKETPLACE') or '').lower() == 'amazon' or 'amazon.com' in url.lower()
    
    # catalog_id do scraper (campo novo CATALOG_ID ou catalog_id)
    scraper_catalog_id = str(p.get('CATALOG_ID') or p.get('catalog_id') or '').strip()
    
    if cat_match:
        raw_cat_id = cat_match.group(1)
    elif scraper_catalog_id and scraper_catalog_id.startswith('MLB'):
        raw_cat_id = scraper_catalog_id
    elif is_amazon and asin_match:
        raw_cat_id = asin_match.group(1)
    else:
        raw_cat_id = ''
    
    # Flags vindas do scraper, banco ou metadados
    # O sinal do scraper tem PRIORIDADE — se o scraper detectou catálogo, acreditamos nele
    raw_is_cat = p.get('is_catalog')
    if raw_is_cat is None:
        raw_is_cat = p.get('IS_CATALOG')
    if raw_is_cat is None:
        raw_is_cat = p.get('is_catalogo')
    
    sellers_count = int(p.get('sellers_count') or p.get('SELLERS_COUNT') or 1)
    
    # Detecção de múltiplas ofertas em textos de metadados
    offers_text = str(p.get('offers') or p.get('OFFERS') or p.get('ofertas_especiais') or p.get('etiquetas') or '')
    offers_match = re.search(r'(\d+)\s*(?:outras?\s*ofertas?|opções\s*de\s*compra|vendedores|ofertas?\s*a\s*partir|novas?\s*ofertas?)', offers_text, re.IGNORECASE)
    if offers_match:
        sellers_count = max(sellers_count, int(offers_match.group(1)) + 1)

    has_buybox_sellers = sellers_count > 1

    if is_amazon:
        # Na Amazon: sinal do scraper é suficiente (is_catalog=True já indica buybox compartilhado)
        # Também considera múltiplos vendedores, texto explícito de ofertas, ou link offer-listing
        has_amazon_offers_link = 'offer-listing' in url or 'aod' in url
        is_cat = bool(raw_is_cat) or sellers_count > 1 or bool(offers_match) or has_amazon_offers_link
        if is_cat and sellers_count == 1:
            sellers_count = 2
    else:
        # No Mercado Livre, o scraper melhorado já detecta /p/MLB e wid= corretamente
        # raw_is_cat tem prioridade — não sobrescrever com heurística negativa
        ml_is_cat_url = bool(cat_match) and not is_user_post
        has_options_link = bool(re.search(r'/p/MLB\d+/s', url)) or ('type=product' in url and bool(p.get('opcoes_compra')))
        is_explicit_cat = p.get('origem') == 'catalogo' and bool(p.get('tem_concorrentes'))
        # raw_is_cat agora é sinal de primeira classe — se o scraper detectou catálogo, mantém
        is_cat = (bool(raw_is_cat) or ml_is_cat_url or has_buybox_sellers or has_options_link or is_explicit_cat or bool(scraper_catalog_id)) and not is_user_post
        # Garante sellers_count mínimo para produtos de catálogo confirmados
        if is_cat and sellers_count == 1:
            sellers_count = 2

    p['is_catalog'] = bool(is_cat)
    p['sellers_count'] = sellers_count
    
    p['catalog_id'] = raw_cat_id if (raw_cat_id and is_cat) else ''
    
    wid_match = re.search(r'wid=(MLB\d+)', url)
    p['winner_item_id'] = wid_match.group(1) if wid_match else (raw_cat_id if (is_amazon and is_cat) else '')
    
    # 2. Vendedor da BuyBox e Medalha
    raw_store = p.get('store_name') or p.get('loja_oficial') or p.get('LOJA_OFICIAL') or p.get('loja') or ''
    
    # Se raw_store for uma URL ou contiver /loja/, extrai o nome formatado
    if '/loja/' in str(raw_store):
        loja_m = re.search(r'/loja/([^/?&#]+)', str(raw_store))
        if loja_m:
            raw_store = loja_m.group(1).replace('-', ' ').title()
    elif not raw_store and '/loja/' in url:
        loja_m = re.search(r'/loja/([^/?&#]+)', url)
        if loja_m:
            raw_store = loja_m.group(1).replace('-', ' ').title()

    clean_store = re.sub(r'^(vendido\s+por\s+|por\s+|loja\s+oficial\s+)', '', str(raw_store), flags=re.IGNORECASE).strip()
    
    # Sanitização: NUNCA usar ASIN ou código de produto como nome de vendedor
    if re.match(r'^(B0[A-Z0-9]{8}|[A-Z0-9]{10}|MLB\d+)$', clean_store, re.IGNORECASE):
        clean_store = ""

    if not clean_store or clean_store.lower() in ('loja não identificada', 'loja', 'none', 'null'):
        # Tenta extrair a marca do produto ou título
        brand_val = str(p.get('marca') or p.get('brand') or '').strip()
        if brand_val and not re.match(r'^(B0[A-Z0-9]{8}|[A-Z0-9]{10}|MLB\d+)$', brand_val, re.IGNORECASE):
            clean_store = brand_val
        elif title.upper().startswith("EF ECOFLOW"):
            clean_store = "EF ECOFLOW"
        elif title.upper().startswith("ECOFLOW"):
            clean_store = "Ecoflow"
        elif title.upper().startswith("ZOUPW"):
            clean_store = "ZOUPW"
        else:
            # Fallback tenta extrair da URL se for loja oficial
            loja_url_match = re.search(r'/loja/([^/?&#]+)', url)
            if loja_url_match:
                clean_store = loja_url_match.group(1).replace('-', ' ').title()
            else:
                clean_store = "Vendedor Oficial" if is_cat else ("Vendedor Mercado Livre" if 'mercadolivre' in url.lower() else "Amazon Brasil")
            
    p['store_name'] = clean_store
    p['winner_seller_name'] = clean_store
    
    # Medalha e Reputação do Vendedor
    raw_medal = str(p.get('seller_medal') or p.get('reputacao') or '').lower()
    if 'platinum' in raw_medal:
        p['seller_medal'] = 'Platinum'
    elif 'gold' in raw_medal:
        p['seller_medal'] = 'Gold'
    elif 'líder' in raw_medal or 'lider' in raw_medal or 'silver' in raw_medal:
        p['seller_medal'] = 'Líder'
    elif p.get('prime') or p.get('patrocinado') or reviews >= 400:
        p['seller_medal'] = 'Platinum'
    elif reviews >= 120:
        p['seller_medal'] = 'Gold'
    elif reviews >= 25:
        p['seller_medal'] = 'Líder'
    else:
        p['seller_medal'] = 'Sem medalha'
        
    p['seller_location'] = p.get('seller_location') or 'São Paulo/SP'
    
    # 3. Envio / Frete
    if p.get('prime') or 'full' in str(p.get('etiquetas', '')).lower() or reviews > 50:
        p['shipping_type'] = 'FULL'
    elif p.get('frete_gratis', True):
        p['shipping_type'] = 'Frete Grátis'
    else:
        p['shipping_type'] = 'Flex'
        
    # 4. Vendas Estimadas & Faturamento
    multiplier = 15 if is_cat else 8
    estimated_sales = max(reviews * multiplier, 60 if is_cat else 20)
    p['estimated_sales'] = estimated_sales
    p['estimated_revenue'] = float(estimated_sales * price)
    
    # 5. Comissão ML Estimada
    if p.get('marketplace') == 'Amazon':
        p['platform_commission'] = float(price * 0.15)
    else:
        p['platform_commission'] = float((price * 0.13) + (6.0 if price < 79.0 else 0.0))
        
    # 6. Concorrentes no catálogo (BuyBox)
    raw_sellers = p.get('sellers_count') or p.get('SELLERS_COUNT') or p.get('buybox_offers_count')
    if raw_sellers and int(raw_sellers) > 0:
        p['sellers_count'] = int(raw_sellers)
    elif is_cat:
        p['sellers_count'] = max(int(reviews / 15), 2)
    else:
        p['sellers_count'] = 1
        
    p['buybox_offers_count'] = p['sellers_count']
    p['buybox_min_price'] = float(p.get('buybox_min_price') or p.get('BUYBOX_MIN_PRICE') or 0.0)
        
    # 7. Idade estimada (dias)
    p['age_days'] = min(max(reviews * 3, 60), 730)
    
    # 8. Marca
    words = title.split()
    p['brand'] = words[0] if words else 'Geral'
    
    # 9. Parcelamento
    if price > 0:
        p['installment_val'] = float(price / 12)
        
    return p


def compute_sidebar_metrics(results: list) -> dict:
    """Calcula estatísticas agregadas para os filtros da Sidebar Avant Pro"""
    medals = {'no_medal': 0, 'lider': 0, 'gold': 0, 'platinum': 0}
    shipping = {'full': 0, 'free': 0, 'flex': 0}
    sellers_range = {'range_1_5': 0, 'range_6_10': 0, 'range_11_30': 0, 'range_30_plus': 0}
    creation_age = {'up_to_180': 0, 'up_to_365': 0, 'more_365': 0}
    types = {'classico': 0, 'premium': 0, 'oficiais': 0}

    total_revenue = 0.0
    total_sales = 0

    catalog_count = 0
    individual_count = 0

    for r in results:
        # Catálogo vs Individual
        if r.get('is_catalog'):
            catalog_count += 1
        else:
            individual_count += 1

        # Medalhas
        m = r.get('seller_medal', 'Sem medalha')
        if m == 'Platinum': medals['platinum'] += 1
        elif m == 'Gold': medals['gold'] += 1
        elif m == 'Líder': medals['lider'] += 1
        else: medals['no_medal'] += 1

        # Envio
        s = r.get('shipping_type', 'Frete Grátis')
        if s == 'FULL': shipping['full'] += 1
        elif s == 'Flex': shipping['flex'] += 1
        else: shipping['free'] += 1

        # Sellers
        sc = r.get('sellers_count', 1)
        if sc <= 5: sellers_range['range_1_5'] += 1
        elif sc <= 10: sellers_range['range_6_10'] += 1
        elif sc <= 30: sellers_range['range_11_30'] += 1
        else: sellers_range['range_30_plus'] += 1

        # Idade
        age = r.get('age_days', 90)
        if age <= 180: creation_age['up_to_180'] += 1
        elif age <= 365: creation_age['up_to_365'] += 1
        else: creation_age['more_365'] += 1

        # Tipos
        if r.get('patrocinado') or r.get('is_catalog'):
            types['premium'] += 1
        elif r.get('loja_oficial'):
            types['oficiais'] += 1
        else:
            types['classico'] += 1

        total_revenue += float(r.get('estimated_revenue', 0))
        total_sales += int(r.get('estimated_sales', 0))

    new_offers_count = sum(1 for r in results if r.get('is_new'))

    return {
        'catalog_count': catalog_count,
        'individual_count': individual_count,
        'new_offers_count': new_offers_count,
        'medals': medals,
        'shipping': shipping,
        'sellers_range': sellers_range,
        'creation_age': creation_age,
        'types': types,
        'total_revenue': total_revenue,
        'total_sales': total_sales
    }


@search_bp.route('/results')
def results_page():
    """Página de resultados da busca (persistente e em tempo real) com Inteligência Avant Pro"""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    search_id = request.args.get('search_id')
    busca_id = request.args.get('busca_id', type=int)
    termo = request.args.get('termo')
    
    raw_results = []
    stats = {}
    
    # 1. Tenta pegar da memória RAM
    if search_id and search_id in search_status:
        status = search_status[search_id]
        if status.get('status') == 'concluida':
            raw_results = status.get('results', [])
            stats = status.get('stats', {})
        elif status.get('status') == 'erro':
            flash(f"Erro na busca: {status.get('error')}", 'error')
            return redirect(url_for('search.search_page'))
        else:
            flash('Busca ainda não foi concluída.', 'warning')
            return redirect(url_for('search.search_page'))
            
    # 2. Se veio busca_id ou termo, busca do Supabase
    elif busca_id or termo:
        data = db_manager.get_offers_by_search(busca_id=busca_id, termo=termo)
        if data.get('results'):
            raw_results = data['results']
            stats = data.get('stats', {})
            termo = data.get('termo_pesquisa')
    
    if raw_results:
        # Recupera histórico anterior para detectar itens novos
        previous_known_ids = db_manager.get_previous_search_identifiers(user_id, termo or '')
        has_history = len(previous_known_ids) > 0
        
        # Enriquece os produtos com inteligência de mercado e flag de novidades
        enriched_results = []
        for p in raw_results:
            enriched = enrich_product_intel(p)
            p_url = (enriched.get('url_produto') or enriched.get('link') or '').strip()
            p_cat = (enriched.get('catalog_id') or '').strip().upper()
            
            is_new = False
            if has_history:
                if p_url and (p_url not in previous_known_ids) and (not p_cat or p_cat not in previous_known_ids):
                    is_new = True
            enriched['is_new'] = is_new
            enriched_results.append(enriched)

        sidebar_metrics = compute_sidebar_metrics(enriched_results)
        sidebar_metrics['has_previous_history'] = has_history
        
        telemetry = stats.get('telemetry') or {
            'amazon': {'status': 'SUCCESS' if stats.get('amazon_produtos', 0) > 0 else 'EMPTY', 'count': stats.get('amazon_produtos', 0)},
            'mercadolivre': {'status': 'SUCCESS' if stats.get('ml_produtos', 0) > 0 else ('FAILED' if stats.get('amazon_produtos', 0) > 0 and stats.get('ml_produtos', 0) == 0 else 'EMPTY'), 'count': stats.get('ml_produtos', 0)}
        }

        return render_template('search/results.html',
                               results=enriched_results,
                               stats=stats,
                               telemetry=telemetry,
                               sidebar_metrics=sidebar_metrics,
                               search_id=search_id,
                               busca_id=busca_id,
                               termo_pesquisa=termo)
    
    flash('Busca não encontrada ou expirada. Realize uma nova busca.', 'info')
    return redirect(url_for('search.search_page'))


@search_bp.route('/api/search/retry-ml', methods=['POST'])
def retry_mercadolivre_search():
    """Re-executa exclusivamente a busca no Mercado Livre para um termo específico e salva no Supabase"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    data = request.get_json() or {}
    termo = data.get('termo', '').strip()
    if not termo:
        return jsonify({'error': 'Termo de pesquisa obrigatório'}), 400
        
    user_id = session['user_id']
    try:
        from scraping.unificar_dados import _fetch_ml_worker, padronizar_colunas_ml
        from database.supabase_client import SupabaseDB
        
        df_ml, tel_ml = _fetch_ml_worker(termo, paginas_ml=1, user_id=str(user_id))
        if df_ml is not None and not df_ml.empty:
            df_ml_pad = padronizar_colunas_ml(df_ml)
            df_ml_pad['termo_pesquisa'] = termo
            db = SupabaseDB()
            db.salvar_ofertas(df_ml_pad)
            
            # Invalida cache de busca do usuário
            _invalidate_user_search_cache(user_id)
            
            records = df_ml_pad.to_dict('records')
            enriched = [enrich_product_intel(r) for r in records]
            return jsonify({
                'success': True,
                'count': len(enriched),
                'results': enriched,
                'message': f'{len(enriched)} ofertas coletadas do Mercado Livre com sucesso!'
            })
        else:
            return jsonify({
                'success': False,
                'count': 0,
                'message': 'Mercado Livre não retornou produtos para este termo.'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'Erro ao re-tentar Mercado Livre: {e}'
        }), 500

@search_bp.route('/recent')
def recent_searches():
    """Página com buscas recentes"""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    termo_pesquisa = request.args.get('termo', '')
    
    # Busca ofertas recentes
    query = db_manager.supabase.table("ofertas").select("*").order("criado_em", desc=True)
    
    if termo_pesquisa:
        query = query.eq("termo_pesquisa", termo_pesquisa)
    
    ofertas_response = query.limit(100).execute()
    ofertas = ofertas_response.data or []
    
    # Agrupa por termo de pesquisa
    termos_unicos = list(set(oferta['termo_pesquisa'] for oferta in ofertas))
    
    return render_template('search/recent.html', 
                         ofertas=ofertas, 
                         termos_unicos=termos_unicos,
                         termo_selecionado=termo_pesquisa)

@search_bp.route('/approve-products', methods=['POST'])
def approve_products():
    """Aprova produtos selecionados"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    data = request.get_json()
    product_ids = data.get('product_ids', [])
    
    if not product_ids:
        return jsonify({'error': 'Nenhum produto selecionado'}), 400
    
    user_id = session['user_id']
    approved_count = db_manager.approve_products(user_id, product_ids)
    # Invalida todos os caches de busca do usuário
    _invalidate_user_search_cache(user_id)
    return jsonify({
        'success': True,
        'approved_count': approved_count,
        'message': f'{approved_count} produto(s) aprovado(s) com sucesso!'
    })

# Função utilitária para invalidar todos os caches de busca do usuário
def _invalidate_user_search_cache(user_id):
    from utils.simple_cache import cache
    prefix = f"search:{user_id}:"
    keys_to_invalidate = []
    with cache._lock:
        for key in list(cache._cache.keys()):
            if key.startswith(prefix):
                keys_to_invalidate.append(key)
        for key in keys_to_invalidate:
            cache.invalidate(key)

@search_bp.route('/create-purchase-order', methods=['POST'])
def create_purchase_order_from_search():
    """Cria um pedido de compra no inventário diretamente a partir de uma oferta encontrada"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
        
    try:
        user_id = session['user_id']
        data = request.get_json() or {}
        
        produto_titulo = data.get('produto_titulo') or 'Produto sem título'
        fornecedor = data.get('fornecedor') or 'Fornecedor Marketplace'
        marketplace = data.get('marketplace') or 'MercadoLivre'
        preco_unitario = float(data.get('preco_unitario') or 0)
        quantidade = int(data.get('quantidade') or 1)
        url_produto = data.get('url_produto') or ''
        
        # Gera SKU automático ou simplificado
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', produto_titulo[:10]).upper()
        sku = f"{clean_name}-{int(time.time()) % 10000}"
        numero_pedido = f"PED-SRCH-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        itens = [{
            'sku': sku,
            'descricao': produto_titulo,
            'ncm': '',
            'quantidade': quantidade,
            'preco_revenda': preco_unitario,
            'preco_site_pix': preco_unitario * 0.95,
            'link_produto': url_produto
        }]
        
        observacoes = f"Gerado automaticamente a partir da busca no marketplace {marketplace}. Vendedor: {fornecedor}"
        
        order = db_manager.create_purchase_order(
            user_id=user_id,
            numero_pedido=numero_pedido,
            fornecedor=fornecedor,
            observacoes=observacoes,
            itens=itens
        )
        
        if order:
            return jsonify({
                'success': True,
                'pedido_id': order.get('id'),
                'numero_pedido': numero_pedido,
                'message': 'Pedido de Compra gerado com sucesso no inventário!'
            })
        else:
            return jsonify({'success': False, 'error': 'Não foi possível salvar o pedido no banco de dados.'}), 500
            
    except Exception as e:
        print(f"❌ Erro ao criar pedido de compra da busca: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@search_bp.route('/batch/preview', methods=['POST'])
def batch_preview():
    """Lê arquivo ou texto e retorna lista estruturada para conferência prévia do lote"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
        
    try:
        itens = []
        
        # Processa arquivo CSV, XLSX ou TXT
        if 'arquivo_csv' in request.files and request.files['arquivo_csv'].filename:
            file = request.files['arquivo_csv']
            filename = file.filename.lower()
            
            if filename.endswith('.xlsx') or filename.endswith('.xls'):
                import io
                df_file = pd.read_excel(io.BytesIO(file.read()))
                # Tenta localizar a coluna de produto/termo
                col_name = None
                for col in df_file.columns:
                    c_low = str(col).lower()
                    if any(k in c_low for k in ['termo', 'produto', 'nome', 'descricao', 'title', 'item']):
                        col_name = col
                        break
                if col_name is None:
                    col_name = df_file.columns[0]
                    
                for idx, row in df_file.iterrows():
                    val = str(row[col_name]).strip()
                    if val and val != 'nan':
                        sku_val = str(row.get('sku', '')).strip() if 'sku' in [str(c).lower() for c in df_file.columns] else ''
                        itens.append({
                            'id': len(itens) + 1,
                            'termo': val,
                            'sku': sku_val,
                            'selected': True
                        })
            else:
                content = file.read().decode('utf-8', errors='ignore').splitlines()
                for line in content:
                    line_str = line.strip()
                    if line_str:
                        parts = line_str.split(',')
                        term = parts[0].strip().strip('"').strip("'")
                        sku_val = parts[1].strip() if len(parts) > 1 else ''
                        if term and term.lower() not in ['termo', 'produto', 'nome']:
                            itens.append({
                                'id': len(itens) + 1,
                                'termo': term,
                                'sku': sku_val,
                                'selected': True
                            })
                            
        # Processa texto colado
        elif 'termos_texto' in request.form and request.form['termos_texto'].strip():
            lines = request.form['termos_texto'].split('\n')
            for line in lines:
                val = line.strip()
                if val:
                    itens.append({
                        'id': len(itens) + 1,
                        'termo': val,
                        'sku': '',
                        'selected': True
                    })
                    
        # Remove termos duplicados mantendo a ordem
        vistos = set()
        itens_unicos = []
        for it in itens:
            if it['termo'].lower() not in vistos:
                vistos.add(it['termo'].lower())
                itens_unicos.append(it)
                
        return jsonify({
            'success': True,
            'total': len(itens_unicos),
            'itens': itens_unicos
        })
        
    except Exception as e:
        print(f"❌ Erro ao gerar preview do lote: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@search_bp.route('/bulk', methods=['POST'])
def execute_bulk_search():
    """Inicia busca em lote a partir dos termos confirmados"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    user_id = session['user_id']
    termos = []
    
    # Se veio lista confirmada em JSON
    if request.is_json:
        data = request.get_json() or {}
        termos = data.get('termos', [])
    else:
        # Processa textarea ou form tradicional
        if 'termos_texto' in request.form and request.form['termos_texto'].strip():
            termos_brutos = request.form['termos_texto'].split('\n')
            termos.extend([t.strip() for t in termos_brutos if t.strip()])
        
        if 'arquivo_csv' in request.files:
            file = request.files['arquivo_csv']
            if file.filename:
                content = file.read().decode('utf-8', errors='ignore').splitlines()
                for line in content:
                    term = line.split(',')[0].strip()
                    if term and term.lower() not in ['termo', 'produto', 'nome']:
                        termos.append(term)
                        
    # Remove duplicatas
    termos = list(dict.fromkeys([t for t in termos if t and str(t).strip()]))
    
    if not termos:
        return jsonify({'error': 'Nenhum termo de busca selecionado'}), 400
        
    try:
        # Cria lote
        lote_response = db_manager.supabase.table("lotes_busca").insert({
            "user_id": user_id,
            "status": "pendente",
            "total_itens": len(termos)
        }).execute()
        
        lote_id = lote_response.data[0]['id']
        
        # Cria itens do lote
        itens_data = [{"lote_id": lote_id, "termo": t} for t in termos]
        db_manager.supabase.table("lote_itens").insert(itens_data).execute()
        
        # Inicia processador com gravação de histórico individual
        processor = BulkProcessor(db_manager)
        processor.start_bulk_search(lote_id, user_id)
        
        return jsonify({
            'success': True,
            'lote_id': lote_id,
            'total_itens': len(termos)
        })
        
    except Exception as e:
        print(f"Erro ao iniciar busca em lote: {e}")
        return jsonify({'error': str(e)}), 500

@search_bp.route('/bulk/<lote_id>/status', methods=['GET'])
def bulk_status(lote_id):
    """Retorna o status de um lote de busca"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
        
    try:
        response = db_manager.supabase.table("lotes_busca").select("*").eq("id", lote_id).execute()
        if not response.data:
            return jsonify({'error': 'Lote não encontrado'}), 404
            
        lote = response.data[0]
        # Garante que itens_processados não seja None
        processados = lote.get('itens_processados') or 0
        total = lote.get('total_itens') or 1
        
        progress = int((processados / total) * 100) if total > 0 else 0
        
        return jsonify({
            'status': lote['status'],
            'total_itens': total,
            'itens_processados': processados,
            'progress': progress,
            'arquivo_resultado_url': lote.get('arquivo_resultado_url'),
            'erro_mensagem': lote.get('erro_mensagem')
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── AÇÕES DE TRIAGEM EM LOTE NA TELA DE RESULTADOS ──────────────────────────

@search_bp.route('/delete-offers', methods=['POST'])
def delete_offers():
    """Exclui uma ou mais ofertas do banco de dados a partir da triagem na tela de resultados"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    try:
        data = request.get_json() or {}
        offer_ids = data.get('offer_ids', [])
        offer_urls = data.get('offer_urls', [])

        deleted_by_id = 0
        deleted_by_url = 0

        if offer_ids:
            deleted_by_id = db_manager.delete_offers_by_ids(offer_ids)
        if offer_urls:
            deleted_by_url = db_manager.delete_offers_by_urls(offer_urls)

        total_deleted = max(deleted_by_id, deleted_by_url, len(offer_ids), len(offer_urls))

        return jsonify({
            'success': True,
            'deleted_count': total_deleted,
            'message': f"{total_deleted} oferta(s) removida(s) do histórico com sucesso."
        })
    except Exception as e:
        print(f"❌ Erro ao excluir ofertas em lote: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@search_bp.route('/batch-add-catalogs', methods=['POST'])
def batch_add_catalogs():
    """Adiciona múltiplos produtos de catálogo selecionados à tabela de catálogos monitorados"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    try:
        user_id = session['user_id']
        data = request.get_json() or {}
        catalogs = data.get('catalogs', [])

        if not catalogs:
            return jsonify({'success': False, 'error': 'Nenhum catálogo fornecido'}), 400

        added_count = 0
        skipped_count = 0

        for item in catalogs:
            cid = str(item.get('catalog_id') or '').strip()
            if not cid:
                skipped_count += 1
                continue

            mp = item.get('marketplace') or ('MercadoLivre' if cid.startswith('MLB') else 'Amazon')
            title = item.get('title') or item.get('nome') or f"Catálogo {cid}"
            image = item.get('image') or item.get('imagem') or ""
            url = item.get('url') or item.get('url_produto') or ""
            search_term = item.get('search_term') or item.get('termo_pesquisa') or ""

            cat_payload = {
                "catalog_id": cid,
                "nome": title,
                "titulo": title,
                "imagem": image,
                "imagem_url": image,
                "url_produto": url,
                "marketplace": mp,
                "termo_pesquisa": search_term,
                "user_id": user_id
            }

            saved = db_manager.save_catalog(cat_payload)
            if saved:
                added_count += 1
            else:
                skipped_count += 1

        return jsonify({
            'success': True,
            'added_count': added_count,
            'skipped_count': skipped_count,
            'message': f"{added_count} catálogo(s) adicionado(s) com sucesso aos Catálogos Monitorados!"
        })
    except Exception as e:
        print(f"❌ Erro ao adicionar catálogos em lote: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

