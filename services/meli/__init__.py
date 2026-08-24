"""
Pacote de serviços oficiais do Mercado Livre.
Fornece clientes HTTP, gerenciador OAuth 2.0, catálogo e busca de ofertas.
"""

from services.meli.auth import MeliAuthManager
from services.meli.client import MeliClient
from services.meli.catalog import MeliCatalogService
from services.meli.search import MeliSearchService

__all__ = [
    "MeliAuthManager",
    "MeliClient",
    "MeliCatalogService",
    "MeliSearchService"
]
