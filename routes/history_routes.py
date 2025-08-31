from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from database.db_manager import DatabaseManager
from datetime import datetime, timedelta
import math

history_bp = Blueprint('history', __name__)
db = DatabaseManager()

@history_bp.route('/')
def history_page():
    """Página de histórico de buscas"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
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
def delete_search(busca_id):
    """Excluir busca específica do histórico"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'})
    
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

@history_bp.route('/clear', methods=['POST'])
def clear_history():
    """Limpar todo o histórico do usuário"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'})
    
    try:
        user_id = session['user_id']
        
        # Esta funcionalidade precisa ser implementada no db_manager
        # Por enquanto, vamos retornar um erro amigável
        # success = db.clear_all_history(user_id)
        
        return jsonify({'success': False, 'message': 'Funcionalidade ainda não implementada.'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})
