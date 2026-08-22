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

@search_bp.route('/')
def search_page():
    """Página principal de busca"""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))
    
    return render_template('search/search.html')

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
    search_id = f"{user_id}_{int(time.time())}"

    # Verifica cache antes de iniciar nova busca
    cache_key = f"search:{user_id}:{termo_pesquisa}"
    cached = cache.get(cache_key)
    if cached:
        # Se houver cache válido, retorna o search_id e marca como concluído
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
        args=(search_id, user_id, termo_pesquisa, paginas_ml)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'search_id': search_id})

def _execute_search_thread(search_id, user_id, termo_pesquisa, paginas_ml):
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
            results = buscar_e_salvar_ofertas(termo_pesquisa, paginas_ml)
            execution_time = int(time.time() - start_time)
            print(f"⏱️ Busca concluída em {execution_time} segundos, {len(results)} resultados")
            
            # Atualiza progresso
            search_status[search_id].update({
                'progress': 80,
                'message': 'Processando resultados...'
            })
            print(f"📊 Progresso atualizado para 80%: {search_status[search_id]}")
            
            # Calcula estatísticas
            stats = {
                'total_produtos': int(len(results) or 0),
                'amazon_produtos': int(len([r for r in results if r.get('marketplace') == 'Amazon']) or 0),
                'ml_produtos': int(len([r for r in results if r.get('marketplace') == 'MercadoLivre']) or 0),
                'preco_medio': float(sum(r.get('preco_numerico', 0) or 0 for r in results) / len(results)) if results else 0.0,
                'preco_minimo': float(min((r.get('preco_numerico', 0) or 0) for r in results)) if results else 0.0,
                'preco_maximo': float(max((r.get('preco_numerico', 0) or 0) for r in results)) if results else 0.0,
                'tempo_execucao': int(execution_time or 0)
            }
            print(f"📈 Estatísticas: {stats}")
            
            # Salva no histórico
            history_id = db_manager.save_search_history(user_id, termo_pesquisa, stats)
            print(f"💾 ID do histórico salvo: {history_id}")
            
            # Busca resultados do banco para exibir
            print(f"🔍 Buscando ofertas do banco para termo: {termo_pesquisa}")
            ofertas_response = db_manager.supabase.table("ofertas").select("*").eq("termo_pesquisa", termo_pesquisa).order("score_produto", desc=True).limit(50).execute()
            
            ofertas = ofertas_response.data or []
            print(f"✅ Encontradas {len(ofertas)} ofertas no banco de dados")
            
            # Finaliza busca
            search_status[search_id].update({
                'status': 'concluida',
                'progress': 100,
                'message': f'Busca concluída! {len(ofertas)} produtos encontrados.',
                'results': ofertas,
                'stats': stats,
                'completed': True
            })
            # Salva no cache
            cache_key = f"search:{user_id}:{termo_pesquisa}"
            cache.set(cache_key, {'results': ofertas, 'stats': stats})
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
    
    # 1. Classificação Precisa de Catálogo com Concorrência de Sellers vs Anúncio de Vendedor Único
    # No Mercado Livre, um item é considerado catálogo se pertencer ao catálogo oficial (/p/MLB...)
    # com opções de compra / múltiplos vendedores disputando a BuyBox.
    is_user_post = '/up/' in url or 'MLBU' in url
    
    # Extrai o Catalog ID se houver
    cat_match = re.search(r'/p/(MLB\d+)', url)
    raw_cat_id = cat_match.group(1) if cat_match else (p.get('catalog_id') or '')
    
    # Flags vindas do scraper, banco ou metadados
    raw_is_cat = p.get('is_catalog')
    if raw_is_cat is None:
        raw_is_cat = p.get('IS_CATALOG')
    if raw_is_cat is None:
        raw_is_cat = p.get('is_catalogo')
    
    has_buybox_sellers = int(p.get('sellers_count') or 0) > 1
    has_options_link = bool(re.search(r'/p/MLB\d+/s', url)) or ('type=product' in url and bool(p.get('opcoes_compra')))
    is_explicit_cat = p.get('origem') == 'catalogo' and bool(p.get('tem_concorrentes'))
    has_scraper_cat_flag = bool(raw_is_cat) or (bool(raw_cat_id) and not is_user_post)
    
    # Para ser considerado catálogo ativo no card:
    is_cat = (has_scraper_cat_flag or has_buybox_sellers or has_options_link or is_explicit_cat) and not is_user_post
    p['is_catalog'] = bool(is_cat)
    
    p['catalog_id'] = raw_cat_id if (raw_cat_id and is_cat) else ''
    
    wid_match = re.search(r'wid=(MLB\d+)', url)
    p['winner_item_id'] = wid_match.group(1) if wid_match else ''
    
    # 2. Vendedor e Medalha
    store = p.get('loja_oficial') or p.get('store_name') or ''
    if not store:
        store = "Vendedor Mercado Livre" if 'mercadolivre' in url.lower() else "Amazon Brasil"
    p['store_name'] = store
    
    if p.get('prime') or p.get('patrocinado') or reviews >= 400:
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
    if is_cat:
        p['sellers_count'] = max(int(p.get('sellers_count') or (reviews / 15)), 2)
    else:
        p['sellers_count'] = 1
        
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

    return {
        'catalog_count': catalog_count,
        'individual_count': individual_count,
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
        # Enriquece os produtos com inteligência de mercado
        enriched_results = [enrich_product_intel(p) for p in raw_results]
        sidebar_metrics = compute_sidebar_metrics(enriched_results)
        
        return render_template('search/results.html',
                               results=enriched_results,
                               stats=stats,
                               sidebar_metrics=sidebar_metrics,
                               search_id=search_id,
                               busca_id=busca_id,
                               termo_pesquisa=termo)
    
    flash('Busca não encontrada ou expirada. Realize uma nova busca.', 'info')
    return redirect(url_for('search.search_page'))

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
