from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from database.db_manager import DatabaseManager
from utils.decorators import login_required

alert_bp = Blueprint('alert', __name__)
db = DatabaseManager()

@alert_bp.route('/')
@login_required
def alert_page():
    """Página de alertas"""
    user_id = session['user_id']
    alerts = db.get_user_alerts(user_id)
    return render_template('alerts/alerts.html', alerts=alerts)

@alert_bp.route('/create', methods=['POST'])
@login_required
def create_alert():
    """Criar novo alerta"""
    try:
        data = request.get_json()
        user_id = session['user_id']
        
        produto_nome = data.get('produto_nome', '').strip()
        preco_alvo = data.get('preco_alvo')
        tipo_alerta = data.get('tipo_alerta')
        telefone = data.get('telefone')
        ativo = data.get('ativo', True)
        
        if not produto_nome or not preco_alvo or not tipo_alerta:
            return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios'})
        
        alert_id = db.create_price_alert(user_id, produto_nome, preco_alvo, tipo_alerta, ativo, telefone)
        
        if alert_id:
            return jsonify({'success': True, 'message': 'Alerta criado com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao criar alerta'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@alert_bp.route('/update/<int:alert_id>', methods=['POST'])
@login_required
def update_alert(alert_id):
    """Atualizar alerta existente"""
    try:
        data = request.get_json()
        user_id = session['user_id']
        
        alert = db.get_alert_by_id(alert_id, user_id)
        if not alert:
            return jsonify({'success': False, 'message': 'Alerta não encontrado'})
        
        produto_nome = data.get('produto_nome', '').strip()
        preco_alvo = data.get('preco_alvo')
        tipo_alerta = data.get('tipo_alerta')
        telefone = data.get('telefone')
        ativo = data.get('ativo', True)
        
        if not produto_nome or not preco_alvo or not tipo_alerta:
            return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios'})
        
        success = db.update_price_alert(alert_id, produto_nome, preco_alvo, tipo_alerta, ativo, telefone)
        
        if success:
            return jsonify({'success': True, 'message': 'Alerta atualizado com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao atualizar alerta'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@alert_bp.route('/delete/<int:alert_id>', methods=['DELETE'])
@login_required
def delete_alert(alert_id):
    """Excluir alerta"""
    try:
        user_id = session['user_id']
        
        alert = db.get_alert_by_id(alert_id, user_id)
        if not alert:
            return jsonify({'success': False, 'message': 'Alerta não encontrado'})
        
        success = db.delete_price_alert(alert_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Alerta excluído com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao excluir alerta'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})