"""
services/meli/client.py
Cliente HTTP centralizado e resiliente para a API oficial do Mercado Livre.
"""

import time
import requests
from typing import Optional, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from services.meli.auth import MeliAuthManager


class MeliClient:
    """
    Cliente HTTP para a API Oficial do Mercado Livre (api.mercadolibre.com).
    Fornece pooling de conexões, injeção de tokens, auto-refresh em 401 e retry com backoff.
    """
    
    BASE_URL = "https://api.mercadolibre.com"

    def __init__(self, auth_manager: Optional[MeliAuthManager] = None):
        self.auth_manager = auth_manager or MeliAuthManager()
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        requires_auth: bool = True,
        user_id: Optional[str] = None,
        timeout: int = 15,
        _is_retry: bool = False
    ) -> requests.Response:
        """
        Executa requisição HTTP para a API do Mercado Livre.
        """
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        else:
            url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"

        req_headers = {
            "Accept": "application/json",
            "User-Agent": "OfferSearchApp/2.0"
        }
        if headers:
            req_headers.update(headers)

        if requires_auth:
            token = self.auth_manager.get_valid_access_token(user_id=user_id)
            if token:
                req_headers["Authorization"] = f"Bearer {token}"

        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_data,
                headers=req_headers,
                timeout=timeout
            )

            # Interceptor para 401 Unauthorized (Token expirou durante uso)
            if response.status_code == 401 and requires_auth and not _is_retry:
                print("🔄 [MeliClient] 401 recebido. Tentando renovar access_token...")
                success, _ = self.auth_manager.refresh_access_token(user_id=user_id)
                if success:
                    return self.request(
                        method=method,
                        endpoint=endpoint,
                        params=params,
                        json_data=json_data,
                        headers=headers,
                        requires_auth=requires_auth,
                        user_id=user_id,
                        timeout=timeout,
                        _is_retry=True
                    )

            # Interceptor para 429 Too Many Requests (Rate Limit)
            if response.status_code == 429 and not _is_retry:
                retry_after = int(response.headers.get("Retry-After", 2))
                print(f"⏳ [MeliClient] Rate limit atingido (429). Aguardando {retry_after}s...")
                time.sleep(retry_after)
                return self.request(
                    method=method,
                    endpoint=endpoint,
                    params=params,
                    json_data=json_data,
                    headers=headers,
                    requires_auth=requires_auth,
                    user_id=user_id,
                    timeout=timeout,
                    _is_retry=True
                )

            return response

        except requests.exceptions.RequestException as e:
            print(f"❌ [MeliClient] Erro na requisição para {url}: {e}")
            raise

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        return self.request("GET", endpoint, params=params, **kwargs)

    def post(self, endpoint: str, json_data: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        return self.request("POST", endpoint, json_data=json_data, **kwargs)
