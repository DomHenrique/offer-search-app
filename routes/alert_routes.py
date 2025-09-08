from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from database.db_manager import DatabaseManager
from utils.decorators import login_required
import os

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

@alert_bp.route('/api/check-alerts', methods=['POST'])
def check_alerts_api():
    """API endpoint para verificar alertas - chamado pelo Supabase"""
    try:
        # Verificar autenticação via header
        auth_header = request.headers.get('Authorization')
        expected_token = os.environ.get('SUPABASE_ALERT_TOKEN', 'default_token')
        
        if not auth_header or auth_header != f'Bearer {expected_token}':
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        user_id = data.get('user_id')
        products = data.get('products', [])
        
        if not user_id or not products:
            return jsonify({'error': 'user_id and products are required'}), 400
        
        # Buscar alertas do usuário
        alerts = db.get_user_alerts(user_id)
        triggered_alerts = []
        
        for alert in alerts:
            if not alert['ativo']:
                continue
                
            for product in products:
                # Verificar se o produto corresponde ao alerta
                if alert['produto_nome'].lower() in product.get('titulo', '').lower():
                    preco_numerico = product.get('preco_numerico', 0)
                    
                    # Verificar condição do alerta
                    should_trigger = False
                    if alert['tipo_alerta'] == 'menor_ou_igual' and preco_numerico <= alert['preco_alvo']:
                        should_trigger = True
                    elif alert['tipo_alerta'] == 'maior_ou_igual' and preco_numerico >= alert['preco_alvo']:
                        should_trigger = True
                    
                    if should_trigger:
                        triggered_alerts.append({
                            'alert_id': alert['id'],
                            'product': product,
                            'alert': alert
                        })
        
        return jsonify({
            'success': True,
            'triggered_alerts': triggered_alerts,
            'total_checked': len(alerts),
            'total_products': len(products)
        })
        
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@alert_bp.route('/api/trigger-alert', methods=['POST'])
def trigger_alert_api():
    """API endpoint para disparar alerta específico"""
    try:
        # Verificar autenticação via header
        auth_header = request.headers.get('Authorization')
        expected_token = os.environ.get('SUPABASE_ALERT_TOKEN', 'default_token')
        
        if not auth_header or auth_header != f'Bearer {expected_token}':
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        alert_id = data.get('alert_id')
        product = data.get('product')
        
        if not alert_id or not product:
            return jsonify({'error': 'alert_id and product are required'}), 400
        
        # Buscar alerta
        alert = db.get_alert_by_id(alert_id, data.get('user_id'))
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        # Atualizar contador de disparos
        db.supabase.table("alertas").update({
            "total_disparos": alert.get('total_disparos', 0) + 1,
            "ultimo_disparo": "NOW()"
        }).eq("id", alert_id).execute()
        
        # Preparar dados para notificação
        message_data = {
            'alert_id': alert_id,
            'product_title': product.get('titulo'),
            'product_price': product.get('preco'),
            'product_url': product.get('url_produto'),
            'target_price': alert['preco_alvo'],
            'alert_type': alert['tipo_alerta'],
            'phone': alert.get('telefone')
        }
        
        return jsonify({
            'success': True,
            'message': 'Alert triggered successfully',
            'data': message_data
        })
        
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500