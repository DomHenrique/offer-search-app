from datetime import datetime, timedelta
import re
from typing import Any, Optional

def format_currency(value: Any) -> str:
    """Formata valor como moeda brasileira"""
    try:
        if isinstance(value, str):
            # Remove caracteres não numéricos exceto vírgula e ponto
            clean_value = re.sub(r'[^\d,.]', '', value)
            if ',' in clean_value and '.' in clean_value:
                # Formato brasileiro: 1.234,56
                if clean_value.rfind(',') > clean_value.rfind('.'):
                    clean_value = clean_value.replace('.', '').replace(',', '.')
                else:
                    # Formato americano: 1,234.56
                    clean_value = clean_value.replace(',', '')
            elif ',' in clean_value:
                # Só vírgula - pode ser decimal
                parts = clean_value.split(',')
                if len(parts) == 2 and len(parts[1]) <= 2:
                    clean_value = clean_value.replace(',', '.')
                else:
                    clean_value = clean_value.replace(',', '')
            
            value = float(clean_value)
        
        if isinstance(value, (int, float)):
            return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
        return str(value)
    
    except (ValueError, TypeError):
        return str(value)

def time_ago(dt: Any) -> str:
    """Retorna tempo relativo (ex: '2 horas atrás')"""
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        
        if not isinstance(dt, datetime):
            return str(dt)
        
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        
        if diff.days > 0:
            if diff.days == 1:
                return "1 dia atrás"
            elif diff.days < 7:
                return f"{diff.days} dias atrás"
            elif diff.days < 30:
                weeks = diff.days // 7
                return f"{weeks} semana{'s' if weeks > 1 else ''} atrás"
            else:
                months = diff.days // 30
                return f"{months} mês{'es' if months > 1 else ''} atrás"
        
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours} hora{'s' if hours > 1 else ''} atrás"
        
        minutes = diff.seconds // 60
        if minutes > 0:
            return f"{minutes} minuto{'s' if minutes > 1 else ''} atrás"
        
        return "Agora mesmo"
    
    except Exception:
        return str(dt)

def clean_search_term(term: str) -> str:
    """Limpa termo de busca removendo caracteres especiais"""
    if not term:
        return ""
    
    # Remove caracteres especiais e múltiplos espaços
    cleaned = re.sub(r'[^\w\s-]', '', term.strip())
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    return cleaned.lower()

def validate_email(email: str) -> bool:
    """Valida formato de email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_password(password: str) -> tuple[bool, str]:
    """Valida senha e retorna (válida, mensagem)"""
    if len(password) < 6:
        return False, "Senha deve ter pelo menos 6 caracteres"
    
    if not re.search(r'[A-Za-z]', password):
        return False, "Senha deve conter pelo menos uma letra"
    
    if not re.search(r'\d', password):
        return False, "Senha deve conter pelo menos um número"
    
    return True, "Senha válida"

def safe_int(value: Any, default: int = 0) -> int:
    """Converte valor para int de forma segura"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_float(value: Any, default: float = 0.0) -> float:
    """Converte valor para float de forma segura"""
    try:
        if isinstance(value, str):
            # Limpa string antes de converter
            clean_value = re.sub(r'[^\d,.-]', '', value)
            if ',' in clean_value:
                clean_value = clean_value.replace(',', '.')
            return float(clean_value)
        return float(value)
    except (ValueError, TypeError):
        return default

def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """Trunca texto se exceder tamanho máximo"""
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def get_marketplace_icon(marketplace: str) -> str:
    """Retorna ícone CSS para marketplace"""
    icons = {
        'Amazon': 'fab fa-amazon',
        'MercadoLivre': 'fas fa-shopping-cart',
        'Mercado Livre': 'fas fa-shopping-cart'
    }
    return icons.get(marketplace, 'fas fa-store')

def get_rating_stars(rating: float) -> str:
    """Retorna HTML com estrelas para avaliação"""
    if not rating or rating <= 0:
        return '<span class="text-muted">Sem avaliação</span>'
    
    full_stars = int(rating)
    half_star = 1 if (rating - full_stars) >= 0.5 else 0
    empty_stars = 5 - full_stars - half_star
    
    html = ""
    for _ in range(full_stars):
        html += '<i class="fas fa-star text-warning"></i>'
    
    if half_star:
        html += '<i class="fas fa-star-half-alt text-warning"></i>'
    
    for _ in range(empty_stars):
        html += '<i class="far fa-star text-muted"></i>'
    
    html += f' <small class="text-muted">({rating:.1f})</small>'
    
    return html
