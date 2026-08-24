"""
services/meli/auth.py
Gerenciador de Autenticação OAuth 2.0 e Ciclo de Vida de Tokens do Mercado Livre.
"""

import os
import time
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from database.db_manager import DatabaseManager


class MeliAuthManager:
    """
    Gerencia credenciais, URLs de autorização, troca de código OAuth
    e renovação contínua de tokens de acesso (Auto-refresh) do Mercado Livre.
    """
    
    DEFAULT_APP_ID = "4953283902208442"
    DEFAULT_CLIENT_SECRET = "PJjqeilipeEQ5XWQeaBzV7obxW1ndBJ5"
    
    AUTH_BASE_URL = "https://auth.mercadolivre.com.br/authorization"
    TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
    
    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.app_id = os.environ.get("MELI_APP_ID", self.DEFAULT_APP_ID)
        self.client_secret = os.environ.get("MELI_CLIENT_SECRET", self.DEFAULT_CLIENT_SECRET)

    def get_authorization_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Gera a URL de consentimento OAuth do Mercado Livre.
        """
        from urllib.parse import urlencode
        params = {
            "response_type": "code",
            "client_id": self.app_id,
            "redirect_uri": redirect_uri
        }
        if state:
            params["state"] = state
        return f"{self.AUTH_BASE_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str, redirect_uri: str, user_id: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Troca o authorization_code retornado pelo Mercado Livre por access_token e refresh_token.
        """
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.app_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        try:
            response = requests.post(self.TOKEN_URL, data=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                expires_in = data.get("expires_in", 21600)  # Padrão: 6 horas (21600s)
                expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
                
                token_data = {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": expires_in,
                    "expires_at": expires_at,
                    "user_id": data.get("user_id"),
                    "token_type": data.get("token_type", "Bearer"),
                    "scope": data.get("scope", "")
                }
                
                # Salvar no Supabase
                self.db.save_meli_oauth_tokens(token_data, user_id=user_id)
                return True, token_data
            else:
                error_msg = f"Erro na troca do código OAuth: {response.status_code} - {response.text}"
                print(f"❌ {error_msg}")
                return False, {"error": error_msg, "status_code": response.status_code}
        except Exception as e:
            error_msg = f"Exceção ao comunicar com endpoint OAuth Meli: {str(e)}"
            print(f"❌ {error_msg}")
            return False, {"error": error_msg}

    def refresh_access_token(self, user_id: Optional[str] = None, current_refresh_token: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Usa o refresh_token para obter um novo access_token (e novo refresh_token).
        """
        if not current_refresh_token:
            saved = self.db.get_meli_oauth_tokens(user_id=user_id)
            if saved:
                current_refresh_token = saved.get("refresh_token")
        
        if not current_refresh_token:
            current_refresh_token = os.environ.get("MELI_REFRESH_TOKEN")
            
        if not current_refresh_token:
            return False, {"error": "Nenhum refresh_token disponível para renovação."}

        payload = {
            "grant_type": "refresh_token",
            "client_id": self.app_id,
            "client_secret": self.client_secret,
            "refresh_token": current_refresh_token
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        try:
            response = requests.post(self.TOKEN_URL, data=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                expires_in = data.get("expires_in", 21600)
                expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
                
                token_data = {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": expires_in,
                    "expires_at": expires_at,
                    "user_id": data.get("user_id"),
                    "token_type": data.get("token_type", "Bearer"),
                    "scope": data.get("scope", "")
                }
                
                self.db.save_meli_oauth_tokens(token_data, user_id=user_id)
                return True, token_data
            else:
                error_msg = f"Falha ao renovar access_token: {response.status_code} - {response.text}"
                print(f"❌ {error_msg}")
                return False, {"error": error_msg, "status_code": response.status_code}
        except Exception as e:
            error_msg = f"Exceção ao renovar access_token Meli: {str(e)}"
            print(f"❌ {error_msg}")
            return False, {"error": error_msg}

    def get_valid_access_token(self, user_id: Optional[str] = None) -> Optional[str]:
        """
        Retorna um access_token válido.
        Se estiver ausente, tenta recuperar do .env.
        Se estiver expirado ou a menos de 10 minutos de expirar, executa auto-refresh.
        """
        saved = self.db.get_meli_oauth_tokens(user_id=user_id)
        if not saved:
            # Fallback para .env
            env_token = os.environ.get("MELI_ACCESS_TOKEN")
            if env_token:
                return env_token
            return None

        access_token = saved.get("access_token")
        expires_at_str = saved.get("expires_at")
        
        # Se não há data de expiração, retorna o token atual
        if not expires_at_str or not access_token:
            return access_token

        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            # Se expira em menos de 10 minutos (600s), renova antecipadamente
            if datetime.now() + timedelta(seconds=600) >= expires_at:
                success, refreshed = self.refresh_access_token(user_id=user_id, current_refresh_token=saved.get("refresh_token"))
                if success:
                    return refreshed.get("access_token")
                return access_token  # Tenta usar o que tem mesmo se refresh falhar
            return access_token
        except Exception:
            return access_token

    def get_status(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna o status completo da integração com a conta Mercado Livre.
        """
        saved = self.db.get_meli_oauth_tokens(user_id=user_id)
        if not saved or not saved.get("access_token"):
            env_token = os.environ.get("MELI_ACCESS_TOKEN")
            if env_token:
                return {
                    "connected": True,
                    "source": "env",
                    "user_id": os.environ.get("MELI_USER_ID", "Configurado no .env"),
                    "expires_at": None,
                    "has_refresh_token": bool(os.environ.get("MELI_REFRESH_TOKEN"))
                }
            return {
                "connected": False,
                "source": "none",
                "user_id": None,
                "expires_at": None,
                "has_refresh_token": False
            }

        expires_at_str = saved.get("expires_at")
        is_expired = False
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                is_expired = datetime.now() >= expires_at
            except Exception:
                pass

        return {
            "connected": True,
            "source": "database",
            "user_id": saved.get("meli_user_id") or saved.get("user_id"),
            "expires_at": expires_at_str,
            "is_expired": is_expired,
            "has_refresh_token": bool(saved.get("refresh_token")),
            "updated_at": saved.get("updated_at")
        }

    def disconnect(self, user_id: Optional[str] = None) -> bool:
        """
        Desconecta a conta removendo os tokens salvos.
        """
        return self.db.delete_meli_oauth_tokens(user_id=user_id)
