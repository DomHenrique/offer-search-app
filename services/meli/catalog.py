"""
services/meli/catalog.py
Serviço de Catálogos e Inteligência de Buy Box da API Oficial do Mercado Livre.
"""

from typing import Optional, List, Dict, Any
from services.meli.client import MeliClient


class MeliCatalogService:
    """
    Interage com os endpoints oficiais de produtos e catálogos do Mercado Livre:
    - /products/search (Busca por termo ou GTIN/EAN)
    - /products/{product_id} (Detalhe do catálogo)
    - /products/{product_id}/items (Concorrentes e disputa de Buy Box)
    """

    def __init__(self, client: Optional[MeliClient] = None):
        self.client = client or MeliClient()
        self._users_cache: Dict[str, Dict[str, Any]] = {}

    def get_user_info(self, seller_id: Any, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtém informações e reputação do vendedor via GET /users/{seller_id} com cache em memória.
        """
        if not seller_id:
            return {"seller_id": None, "nickname": "Vendedor", "reputation_level": "none", "power_seller_status": None}

        clean_seller_id = str(seller_id).strip()
        if clean_seller_id in self._users_cache:
            return self._users_cache[clean_seller_id]

        try:
            response = self.client.get(f"users/{clean_seller_id}", user_id=user_id)
            if response.status_code == 200:
                data = response.json()
                seller_reputation = data.get("seller_reputation", {})
                transactions = seller_reputation.get("transactions", {})
                
                user_info = {
                    "seller_id": clean_seller_id,
                    "nickname": data.get("nickname") or f"Vendedor #{clean_seller_id}",
                    "reputation_level": seller_reputation.get("level_id", "none"),
                    "power_seller_status": seller_reputation.get("power_seller_status"),
                    "transactions_completed": transactions.get("completed", 0),
                    "city": data.get("address", {}).get("city", ""),
                    "state": data.get("address", {}).get("state", ""),
                    "country_id": data.get("country_id", "BR")
                }
                if len(self._users_cache) > 500:
                    self._users_cache.clear()
                self._users_cache[clean_seller_id] = user_info
                return user_info
        except Exception as e:
            print(f"⚠️ [MeliCatalogService] Erro ao consultar dados do usuário {clean_seller_id}: {e}")

        default_info = {
            "seller_id": clean_seller_id,
            "nickname": f"Vendedor #{clean_seller_id}",
            "reputation_level": "none",
            "power_seller_status": None
        }
        return default_info

    def search_catalog_products(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        site_id: str = "MLB",
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Busca produtos de catálogo no Mercado Livre via GET /products/search.
        """
        params = {
            "status": "active",
            "site_id": site_id,
            "q": query.strip(),
            "limit": min(limit, 50),
            "offset": offset
        }

        try:
            response = self.client.get("products/search", params=params, user_id=user_id)
            if response.status_code != 200:
                print(f"⚠️ [MeliCatalogService] /products/search retornou {response.status_code}: {response.text}")
                return {"success": False, "results": [], "total": 0, "status_code": response.status_code}

            data = response.json()
            raw_results = data.get("results", [])
            paging = data.get("paging", {})

            parsed_products = []
            for item in raw_results:
                parsed = self._parse_catalog_item(item)
                if parsed:
                    parsed_products.append(parsed)

            return {
                "success": True,
                "results": parsed_products,
                "total": paging.get("total", len(parsed_products)),
                "offset": paging.get("offset", offset),
                "limit": paging.get("limit", limit)
            }

        except Exception as e:
            print(f"❌ [MeliCatalogService] Erro ao buscar produtos de catálogo: {e}")
            return {"success": False, "results": [], "total": 0, "error": str(e)}

    def search_by_identifier(
        self,
        identifier: str,
        site_id: str = "MLB",
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Busca catálogo exato por EAN, GTIN, ISBN, UPC ou Part Number.
        """
        clean_identifier = identifier.strip().replace(" ", "").replace("-", "")
        params = {
            "status": "active",
            "site_id": site_id,
            "product_identifier": clean_identifier
        }

        try:
            response = self.client.get("products/search", params=params, user_id=user_id)
            if response.status_code != 200:
                return {"success": False, "results": [], "total": 0}

            data = response.json()
            raw_results = data.get("results", [])
            parsed_products = [self._parse_catalog_item(item) for item in raw_results if item]

            return {
                "success": True,
                "results": [p for p in parsed_products if p],
                "total": len(parsed_products)
            }
        except Exception as e:
            print(f"❌ [MeliCatalogService] Erro ao buscar por identificador {clean_identifier}: {e}")
            return {"success": False, "results": [], "error": str(e)}

    def get_product_detail(self, product_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Obtém os detalhes completos de uma ficha de produto de catálogo via GET /products/{product_id}.
        """
        clean_id = product_id.strip()
        if not clean_id.startswith("MLB") and not clean_id.startswith("MLA"):
            clean_id = f"MLB{clean_id}"

        try:
            response = self.client.get(f"products/{clean_id}", user_id=user_id)
            if response.status_code != 200:
                return None
            return self._parse_catalog_item(response.json())
        except Exception as e:
            print(f"❌ [MeliCatalogService] Erro ao obter produto {clean_id}: {e}")
            return None

    def get_catalog_competition(
        self,
        product_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtém os vendedores concorrentes e a disputa de Buy Box de um produto de catálogo.
        Consulta /products/{product_id}/items e /products/{product_id}.
        """
        clean_id = product_id.strip()
        if not clean_id.startswith("MLB") and not clean_id.startswith("MLA"):
            clean_id = f"MLB{clean_id}"

        # 1. Busca dados do produto principal (Buy Box)
        product_detail = self.get_product_detail(clean_id, user_id=user_id)
        buy_box_winner = product_detail.get("buy_box_winner") if product_detail else None

        # Enriquece buy_box_winner se disponível
        if buy_box_winner and buy_box_winner.get("seller_id"):
            u_info = self.get_user_info(buy_box_winner.get("seller_id"), user_id=user_id)
            buy_box_winner["seller_name"] = u_info.get("nickname") or buy_box_winner.get("seller_name", "Vendedor Oficial")
            buy_box_winner["reputation_level"] = u_info.get("reputation_level", "none")
            buy_box_winner["power_seller_status"] = u_info.get("power_seller_status")

        # 2. Busca lista de concorrentes em /products/{product_id}/items
        competitors = []
        try:
            response = self.client.get(f"products/{clean_id}/items", user_id=user_id)
            if response.status_code == 200:
                items_data = response.json()
                raw_items = items_data.get("results", []) if isinstance(items_data, dict) else items_data
                for it in raw_items:
                    competitor = self._parse_competitor_item(it, buy_box_winner, user_id=user_id)
                    if competitor:
                        competitors.append(competitor)
        except Exception as e:
            print(f"⚠️ [MeliCatalogService] Erro ao buscar /products/{clean_id}/items: {e}")

        # Se não retornou items via endpoint de items mas temos o buy box winner
        if not competitors and buy_box_winner:
            competitors.append({
                "item_id": buy_box_winner.get("item_id"),
                "seller_id": buy_box_winner.get("seller_id"),
                "seller_name": buy_box_winner.get("seller_name", "Vendedor Oficial"),
                "reputation_level": buy_box_winner.get("reputation_level", "none"),
                "power_seller_status": buy_box_winner.get("power_seller_status"),
                "price": buy_box_winner.get("price", 0.0),
                "original_price": buy_box_winner.get("original_price"),
                "currency_id": buy_box_winner.get("currency_id", "BRL"),
                "is_buy_box_winner": True,
                "logistic_type": buy_box_winner.get("logistic_type", "fulfillment"),
                "permalink": product_detail.get("permalink", f"https://www.mercadolivre.com.br/p/{clean_id}"),
                "condition": "new"
            })

        return {
            "success": True,
            "catalog_id": clean_id,
            "product": product_detail,
            "buy_box_winner": buy_box_winner,
            "competitors": competitors,
            "total_competitors": len(competitors)
        }

    def _parse_catalog_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normaliza os dados brutos de um produto de catálogo retornado pela API.
        """
        if not item or not isinstance(item, dict):
            return None

        product_id = item.get("id")
        if not product_id:
            return None

        name = item.get("name") or item.get("title", "")
        buy_box_winner = item.get("buy_box_winner") or {}
        
        # Preço da Buy Box ou preço direto
        price = buy_box_winner.get("price") or item.get("price") or 0.0
        currency_id = buy_box_winner.get("currency_id") or item.get("currency_id", "BRL")

        # Imagens
        pictures = item.get("pictures", [])
        image_url = ""
        if pictures and isinstance(pictures, list):
            image_url = pictures[0].get("url", "")

        # Permalink
        permalink = item.get("permalink") or f"https://www.mercadolivre.com.br/p/{product_id}"

        # Atributos (Marca, Modelo, GTIN)
        raw_attributes = item.get("attributes", [])
        attributes = {}
        for attr in raw_attributes:
            attr_id = attr.get("id", "")
            val = attr.get("value_name") or attr.get("value_id")
            if attr_id and val:
                attributes[attr_id] = val

        return {
            "catalog_id": product_id,
            "title": name,
            "name": name,
            "price": float(price) if price else 0.0,
            "currency_id": currency_id,
            "image_url": image_url,
            "permalink": permalink,
            "domain_id": item.get("domain_id", ""),
            "status": item.get("status", "active"),
            "rating_average": item.get("rating_average", 0.0),
            "reviews_total": item.get("reviews_total", 0),
            "brand": attributes.get("BRAND", attributes.get("MARCA", "")),
            "model": attributes.get("MODEL", attributes.get("MODELO", "")),
            "gtin": attributes.get("GTIN", attributes.get("EAN", "")),
            "buy_box_winner": buy_box_winner,
            "attributes": attributes,
            "is_catalog": True
        }

    def _parse_competitor_item(
        self,
        item: Dict[str, Any],
        buy_box_winner: Optional[Dict[str, Any]],
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Normaliza um concorrente de catálogo e enriquece com dados do lojista.
        """
        if not item or not isinstance(item, dict):
            return None

        item_id = item.get("id") or item.get("item_id")
        price = item.get("price", 0.0)
        seller = item.get("seller", {})
        seller_id = (seller.get("id") if isinstance(seller, dict) else None) or item.get("seller_id") or (seller if isinstance(seller, (str, int)) else None)
        
        user_info = self.get_user_info(seller_id, user_id=user_id) if seller_id else {}
        seller_name = (seller.get("nickname") if isinstance(seller, dict) else None) or (
            user_info.get("nickname") or item.get("seller_name") or f"Vendedor #{seller_id}"
        )

        winner_item_id = buy_box_winner.get("item_id") if buy_box_winner else None
        is_winner = (item_id == winner_item_id) if winner_item_id else False

        shipping = item.get("shipping", {})
        logistic_type = shipping.get("logistic_type") if isinstance(shipping, dict) else item.get("logistic_type", "standard")

        return {
            "item_id": item_id,
            "seller_id": seller_id,
            "seller_name": seller_name,
            "reputation_level": user_info.get("reputation_level", "none"),
            "power_seller_status": user_info.get("power_seller_status"),
            "city": user_info.get("city", ""),
            "state": user_info.get("state", ""),
            "price": float(price) if price else 0.0,
            "original_price": item.get("original_price"),
            "currency_id": item.get("currency_id", "BRL"),
            "is_buy_box_winner": is_winner,
            "logistic_type": logistic_type,
            "permalink": item.get("permalink", ""),
            "condition": item.get("condition", "new"),
            "available_quantity": item.get("available_quantity", 1)
        }
