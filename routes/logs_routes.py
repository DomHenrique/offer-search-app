# routes/logs_routes.py
# Blueprint de Logs de Busca e Auditoria do Sistema

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from database.db_manager import DatabaseManager
from datetime import datetime

logs_bp = Blueprint('logs', __name__, url_prefix='/logs')
db_manager = DatabaseManager()


@logs_bp.route('/')
def logs_page():
    """Página principal de logs e auditoria."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    status_filter = request.args.get('status', 'ALL')

    # Busca logs recentes e estatísticas
    logs = db_manager.get_search_logs(status_filter=status_filter, limit=50)
    stats = db_manager.get_search_logs_stats()

    return render_template(
        'logs/logs_list.html',
        logs=logs,
        stats=stats,
        current_status=status_filter
    )


@logs_bp.route('/api/list')
def api_logs_list():
    """Endpoint JSON paginado para consulta de logs com filtros."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    status_filter = request.args.get('status', 'ALL')
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    logs = db_manager.get_search_logs(status_filter=status_filter, limit=limit, offset=offset)
    stats = db_manager.get_search_logs_stats()

    return jsonify({
        'success': True,
        'logs': logs,
        'stats': stats,
        'total': len(logs)
    })


@logs_bp.route('/api/stats')
def api_logs_stats():
    """Endpoint JSON com estatísticas consolidadas."""
    if 'user_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401

    stats = db_manager.get_search_logs_stats()
    return jsonify({'success': True, 'stats': stats})
