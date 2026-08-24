"""
services/meli/search.py
Serviço de Busca Geral de Ofertas e Itens na API Oficial do Mercado Livre.
"""

from typing import Optional, List, Dict, Any
from services.meli.client import MeliClient


class MeliSearchService:
    """
    Executa buscas de itens e anúncios no Mercado Livre via GET /sites/MLB/search.
    Extrai metadados completos de frete FULL, parcelamento, seller e identificação de catálogo.
    """

    def __init__(self, client: Optional[MeliClient] = None):
        self.client = client or MeliClient()

    def search_offers(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        sort: Optional[str] = None,
        site_id: str = "MLB",
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Busca geral de anúncios/ofertas no Mercado Livre.
        """
        params = {
            "q": query.strip(),
            "limit": min(limit, 50),
            "offset": offset
        }
        if sort:
            # Exemplos: price_asc, price_desc, relevance
            params["sort"] = sort

        try:
            response = self.client.get(f"sites/{site_id}/search", params=params, user_id=user_id)
            if response.status_code != 200:
                print(f"⚠️ [MeliSearchService] /sites/{site_id}/search retornou {response.status_code}: {response.text}")
                return {"success": False, "results": [], "total": 0, "status_code": response.status_code}

            data = response.json()
            raw_results = data.get("results", [])
            paging = data.get("paging", {})

            parsed_offers = []
            for item in raw_results:
                parsed = self._parse_search_item(item)
                if parsed:
                    parsed_offers.append(parsed)

            return {
                "success": True,
                "results": parsed_offers,
                "total": paging.get("total", len(parsed_offers)),
                "offset": paging.get("offset", offset),
                "limit": paging.get("limit", limit)
            }

        except Exception as e:
            print(f"❌ [MeliSearchService] Erro ao buscar ofertas para '{query}': {e}")
            return {"success": False, "results": [], "total": 0, "error": str(e)}

    def get_item_detail(self, item_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Obtém os dados detalhados de um anúncio específico via GET /items/{item_id}.
        """
        clean_id = item_id.strip()
        try:
            response = self.client.get(f"items/{clean_id}", user_id=user_id)
            if response.status_code != 200:
                return None
            return self._parse_search_item(response.json())
        except Exception as e:
            print(f"❌ [MeliSearchService] Erro ao obter item {clean_id}: {e}")
            return None

    def _parse_search_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normaliza os dados de um item retornado pela busca do Mercado Livre.
        """
        if not item or not isinstance(item, dict):
            return None

        item_id = item.get("id", "")
        title = item.get("title", "")
        price = item.get("price", 0.0)
        original_price = item.get("original_price")
        currency_id = item.get("currency_id", "BRL")

        # Tratamento de Imagem para melhor resolução
        thumbnail = item.get("thumbnail", "")
        if thumbnail:
            # Substitui -I.jpg por -O.jpg para alta resolução
            thumbnail = thumbnail.replace("-I.jpg", "-O.jpg").replace("-V.jpg", "-O.jpg")
            if thumbnail.startswith("http://"):
                thumbnail = thumbnail.replace("http://", "https://")

        # Catálogo
        catalog_listing = bool(item.get("catalog_listing"))
        catalog_product_id = item.get("catalog_product_id") or ""
        is_catalog = catalog_listing or bool(catalog_product_id)

        # Logística / Frete FULL
        shipping = item.get("shipping", {}) or {}
        free_shipping = bool(shipping.get("free_shipping"))
        logistic_type = shipping.get("logistic_type", "standard")
        is_full = logistic_type == "fulfillment"

        # Parcelamento
        installments_data = item.get("installments", {}) or {}
        installments_qty = installments_data.get("quantity", 1)
        installments_amount = installments_data.get("amount", price)
        installments_rate = installments_data.get("rate", 0)
        is_interest_free = (installments_rate == 0) and (installments_qty > 1)

        # Vendedor
        seller = item.get("seller", {}) or {}
        seller_id = seller.get("id")
        seller_name = seller.get("nickname") or f"Vendedor #{seller_id}"
        reputation = seller.get("seller_reputation", {}) or {}
        power_seller = reputation.get("power_seller_status", "")  # platinum, gold, silver
        level_id = reputation.get("level_id", "")  # 5_green

        # Permalink
        permalink = item.get("permalink") or f"https://produto.mercadolivre.com.br/{item_id}"

        return {
            "id": item_id,
            "title": title,
            "price": float(price) if price else 0.0,
            "original_price": float(original_price) if original_price else None,
            "currency_id": currency_id,
            "image_url": thumbnail,
            "url": permalink,
            "site": "Mercado Livre",
            "is_catalog": is_catalog,
            "catalog_id": catalog_product_id if catalog_product_id else (f"MLB{item_id}" if is_catalog else None),
            "catalog_product_id": catalog_product_id,
            "condition": item.get("condition", "new"),
            "sold_quantity": item.get("sold_quantity", 0),
            "free_shipping": free_shipping,
            "logistic_type": logistic_type,
            "is_full": is_full,
            "installments_quantity": installments_qty,
            "installments_amount": installments_amount,
            "is_interest_free": is_interest_free,
            "seller_id": seller_id,
            "seller_name": seller_name,
            "seller_reputation": power_seller or level_id,
            "available_quantity": item.get("available_quantity", 1)
        }
