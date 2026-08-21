from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from database.db_manager import DatabaseManager
from datetime import datetime, timedelta
import math
from utils.decorators import login_required

history_bp = Blueprint('history', __name__)
db = DatabaseManager()

@history_bp.route('/')
@login_required
def history_page():
    """Página de histórico de buscas"""
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 15  # Itens por página
    
    # Buscar histórico paginado
    historico_items = db.get_search_history_paginated(user_id, page, per_page)
    
    # Obter total de itens para calcular o total de páginas
    total_items = db.get_search_history_count(user_id)
    total_pages = math.ceil(total_items / per_page)
    
    return render_template(
        'history/history.html', 
        historico=historico_items,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_items=total_items
    )

@history_bp.route('/delete/<int:busca_id>', methods=['DELETE'])
@login_required
def delete_search(busca_id):
    """Excluir busca específica do histórico"""
    try:
        user_id = session['user_id']
        
        # A lógica para verificar se a busca pertence ao usuário deve estar no db_manager
        success = db.delete_search_history(user_id, busca_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Busca excluída com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao excluir busca ou busca não encontrada'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@history_bp.route('/api/recent')
@login_required
def api_recent_searches():
    """Retorna os termos de busca recentes do usuário em formato JSON"""
    try:
        user_id = session['user_id']
        terms = db.get_recent_search_terms(user_id, limit=10)
        return jsonify({'success': True, 'terms': terms})
    except Exception as e:
        return jsonify({'success': False, 'terms': [], 'error': str(e)}), 500

