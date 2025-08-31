from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import time
import threading
from datetime import datetime
import sys
import os

# Adiciona o diretório raiz ao path para importar módulos de scraping
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from utils.helpers import clean_search_term, safe_int
from scraping.run_scraper import buscar_e_salvar_ofertas

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
        
        # Verifica configurações necessárias
        if not config_dict.get('SERPAPI_KEY'):
            print("❌ SERPAPI_KEY não configurada")
            search_status[search_id].update({
                'status': 'erro',
                'error': 'SERPAPI_KEY não configurada. Acesse Configurações para definir.',
                'completed': True
            })
            return
        
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
                'total_produtos': len(results),
                'amazon_produtos': len([r for r in results if r.get('marketplace') == 'Amazon']),
                'ml_produtos': len([r for r in results if r.get('marketplace') == 'MercadoLivre']),
                'preco_medio': sum(r.get('preco_numerico', 0) for r in results) / len(results) if results else 0,
                'preco_minimo': min(r.get('preco_numerico', 0) for r in results) if results else 0,
                'preco_maximo': max(r.get('preco_numerico', 0) for r in results) if results else 0,
                'tempo_execucao': execution_time
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

@search_bp.route('/results')
def results_page():
    """Página de resultados da busca"""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))
    
    search_id = request.args.get('search_id')
    print(f"🔍 Acessando página de resultados para search_id: {search_id}")
    
    if not search_id or search_id not in search_status:
        print("❌ Busca não encontrada ou search_id inválido")
        flash('Busca não encontrada.', 'error')
        return redirect(url_for('search.search_page'))
    
    status = search_status[search_id]
    print(f"📊 Status da busca: {status}")
    
    if status['status'] != 'concluida':
        print("⚠️ Busca ainda não foi concluída")
        flash('Busca ainda não foi concluída.', 'warning')
        return redirect(url_for('search.search_page'))
    
    print(f"✅ Exibindo {len(status['results'])} resultados")
    return render_template('search/results.html', 
                         results=status['results'], 
                         stats=status.get('stats', {}),
                         search_id=search_id)

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
    
    return jsonify({
        'success': True,
        'approved_count': approved_count,
        'message': f'{approved_count} produto(s) aprovado(s) com sucesso!'
    })
