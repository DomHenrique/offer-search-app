
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database.db_manager import DatabaseManager
from utils.helpers import safe_int
from utils.simple_cache import cache

approval_bp = Blueprint('approval', __name__)
db_manager = DatabaseManager()

@approval_bp.route('/')
def approved_products():
    """Página com produtos aprovados"""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    page = safe_int(request.args.get('page', 1), 1)
    per_page = 12
    
    # Busca produtos aprovados
    approved_products = db_manager.get_approved_products(user_id, limit=per_page * page)
    
    # Calcula estatísticas
    stats = calculate_approval_stats(approved_products)
    
    return render_template('approval/approved.html', 
                         products=approved_products,
                         stats=stats,
                         page=page)

@approval_bp.route('/remove', methods=['POST'])
def remove_approved_product():
    """Remove produto da lista de aprovados"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    data = request.get_json()
    product_id = safe_int(data.get('product_id'))
    
    if not product_id:
        return jsonify({'error': 'ID do produto é obrigatório'}), 400
    
    user_id = session['user_id']
    success = db_manager.remove_approved_product(user_id, product_id)
    # Invalida todos os caches de busca do usuário
    _invalidate_user_search_cache(user_id)
    if success:
        return jsonify({
            'success': True,
            'message': 'Produto removido da lista de aprovados!'
        })
    else:
        return jsonify({'error': 'Erro ao remover produto'}), 500

# Função utilitária para invalidar todos os caches de busca do usuário
def _invalidate_user_search_cache(user_id):
    # Percorre todas as chaves do cache e remove as que pertencem ao usuário
    prefix = f"search:{user_id}:"
    keys_to_invalidate = []
    with cache._lock:
        for key in list(cache._cache.keys()):
            if key.startswith(prefix):
                keys_to_invalidate.append(key)
        for key in keys_to_invalidate:
            cache.invalidate(key)

@approval_bp.route('/add-note', methods=['POST'])
def add_product_note():
    """Adiciona observação a um produto aprovado"""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    data = request.get_json()
    product_id = safe_int(data.get('product_id'))
    note = data.get('note', '').strip()
    
    if not product_id:
        return jsonify({'error': 'ID do produto é obrigatório'}), 400
    
    user_id = session['user_id']
    
    try:
        # Atualiza observação do produto
        response = db_manager.supabase.table("produtos_aprovados").update({
            "observacoes": note
        }).eq("user_id", user_id).eq("id", product_id).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Observação salva com sucesso!'
            })
        else:
            return jsonify({'error': 'Produto não encontrado'}), 404
    
    except Exception as e:
        return jsonify({'error': f'Erro ao salvar observação: {str(e)}'}), 500

@approval_bp.route('/export')
def export_approved():
    """Exporta lista de produtos aprovados"""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    format_type = request.args.get('format', 'csv')
    
    # Busca todos os produtos aprovados
    approved_products = db_manager.get_approved_products(user_id, limit=1000)
    
    if format_type == 'csv':
        return export_to_csv(approved_products)
    elif format_type == 'json':
        return export_to_json(approved_products)
    else:
        flash('Formato de exportação inválido.', 'error')
        return redirect(url_for('approval.approved_products'))

def calculate_approval_stats(products):
    """Calcula estatísticas dos produtos aprovados"""
    if not products:
        return {
            'total': 0,
            'amazon': 0,
            'mercado_livre': 0,
            'preco_total': 0,
            'preco_medio': 0,
            'com_desconto': 0,
            'prime': 0
        }
    
    stats = {
        'total': len(products),
        'amazon': len([p for p in products if p.get('marketplace') == 'Amazon']),
        'mercado_livre': len([p for p in products if p.get('marketplace') == 'MercadoLivre']),
        'preco_total': sum(p.get('preco_numerico', 0) for p in products),
        'com_desconto': len([p for p in products if p.get('desconto_percent', 0) > 0]),
        'prime': len([p for p in products if p.get('prime', False)])
    }
    
    stats['preco_medio'] = stats['preco_total'] / stats['total'] if stats['total'] > 0 else 0
    
    return stats

def export_to_csv(products):
    """Exporta produtos para CSV"""
    import csv
    import io
    from flask import make_response
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Cabeçalho
    writer.writerow([
        'Título', 'Preço', 'Marketplace', 'Avaliação', 'Número de Avaliações',
        'URL', 'Observações', 'Data de Aprovação'
    ])
    
    # Dados
    for product in products:
        writer.writerow([
            product.get('titulo', ''),
            product.get('preco', ''),
            product.get('marketplace', ''),
            product.get('avaliacao', ''),
            product.get('avaliacoes', ''),
            product.get('url_produto', ''),
            product.get('observacoes', ''),
            product.get('aprovado_em', '')
        ])
    
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment; filename=produtos_aprovados.csv'
    
    return response

def export_to_json(products):
    """Exporta produtos para JSON"""
    from flask import jsonify, make_response
    import json
    
    response = make_response(json.dumps(products, indent=2, ensure_ascii=False))
    response.headers['Content-Type'] = 'application/json'
    response.headers['Content-Disposition'] = 'attachment; filename=produtos_aprovados.json'
    
    return response
