"""
tests/test_meli_services.py
Testes unitários dos serviços oficiais do Mercado Livre.
"""

import unittest
from unittest.mock import MagicMock, patch
from services.meli.auth import MeliAuthManager
from services.meli.client import MeliClient
from services.meli.catalog import MeliCatalogService
from services.meli.search import MeliSearchService


class TestMeliServices(unittest.TestCase):

    def setUp(self):
        self.mock_db = MagicMock()
        self.auth_manager = MeliAuthManager(db=self.mock_db)
        self.client = MeliClient(auth_manager=self.auth_manager)
        self.catalog_service = MeliCatalogService(client=self.client)
        self.search_service = MeliSearchService(client=self.client)

    def test_auth_url_generation(self):
        """Testa a geração de URL OAuth do Mercado Livre"""
        url = self.auth_manager.get_authorization_url(redirect_uri="http://localhost:5000/settings/meli/callback")
        self.assertIn("https://auth.mercadolivre.com.br/authorization", url)
        self.assertIn("client_id=4953283902208442", url)
        self.assertIn("response_type=code", url)
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%3A5000%2Fsettings%2Fmeli%2Fcallback", url)

    def test_catalog_parser(self):
        """Testa o parsing de produtos de catálogo oficial"""
        raw_catalog_item = {
            "id": "MLB12345678",
            "name": "Smartphone Galaxy S23 5G 128GB",
            "domain_id": "MLB-CELLPHONES",
            "status": "active",
            "pictures": [{"url": "https://http2.mlstatic.com/D_123-O.jpg"}],
            "buy_box_winner": {
                "item_id": "MLB999888",
                "price": 2899.90,
                "currency_id": "BRL",
                "seller_id": 456789,
                "seller_name": "Loja Oficial Samsung"
            },
            "attributes": [
                {"id": "BRAND", "value_name": "Samsung"},
                {"id": "MODEL", "value_name": "Galaxy S23"},
                {"id": "GTIN", "value_name": "7891234567890"}
            ]
        }
        parsed = self.catalog_service._parse_catalog_item(raw_catalog_item)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["catalog_id"], "MLB12345678")
        self.assertEqual(parsed["title"], "Smartphone Galaxy S23 5G 128GB")
        self.assertEqual(parsed["price"], 2899.90)
        self.assertEqual(parsed["brand"], "Samsung")
        self.assertEqual(parsed["gtin"], "7891234567890")
        self.assertTrue(parsed["is_catalog"])

    def test_search_offers_parser(self):
        """Testa o parsing de itens da busca geral com FULL e parcelamento sem juros"""
        raw_search_item = {
            "id": "MLB555444333",
            "title": "Mochila Impermeável Reforçada Executiva",
            "price": 149.90,
            "original_price": 199.90,
            "thumbnail": "http://http2.mlstatic.com/D_555-I.jpg",
            "permalink": "https://produto.mercadolivre.com.br/MLB-555444333",
            "catalog_listing": True,
            "catalog_product_id": "MLB987654",
            "shipping": {
                "free_shipping": True,
                "logistic_type": "fulfillment"
            },
            "installments": {
                "quantity": 10,
                "amount": 14.99,
                "rate": 0
            },
            "seller": {
                "id": 112233,
                "nickname": "STORE_EXECUTIVE",
                "seller_reputation": {
                    "power_seller_status": "platinum",
                    "level_id": "5_green"
                }
            }
        }
        parsed = self.search_service._parse_search_item(raw_search_item)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["id"], "MLB555444333")
        self.assertEqual(parsed["price"], 149.90)
        self.assertEqual(parsed["original_price"], 199.90)
        self.assertTrue(parsed["is_catalog"])
        self.assertEqual(parsed["catalog_id"], "MLB987654")
        self.assertTrue(parsed["free_shipping"])
        self.assertTrue(parsed["is_full"])
        self.assertTrue(parsed["is_interest_free"])
        self.assertEqual(parsed["installments_quantity"], 10)
        self.assertEqual(parsed["seller_name"], "STORE_EXECUTIVE")
        self.assertEqual(parsed["seller_reputation"], "platinum")
        self.assertTrue(parsed["image_url"].startswith("https://"))
        self.assertTrue(parsed["image_url"].endswith("-O.jpg"))

    @patch.object(MeliClient, 'get')
    def test_get_user_info_and_cache(self, mock_get):
        """Testa consulta de perfil de lojista e funcionamento do cache LRU"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 998877,
            "nickname": "ECOFLOW_BRASIL_OFICIAL",
            "seller_reputation": {
                "level_id": "5_green",
                "power_seller_status": "platinum"
            },
            "address": {
                "city": "São Paulo",
                "state": "SP"
            }
        }
        mock_get.return_value = mock_response

        # 1ª chamada: deve consultar API
        info1 = self.catalog_service.get_user_info(998877)
        self.assertEqual(info1["nickname"], "ECOFLOW_BRASIL_OFICIAL")
        self.assertEqual(info1["power_seller_status"], "platinum")
        self.assertEqual(mock_get.call_count, 1)

        # 2ª chamada: deve retornar do cache sem chamar API novamente
        info2 = self.catalog_service.get_user_info("998877")
        self.assertEqual(info2["nickname"], "ECOFLOW_BRASIL_OFICIAL")
        self.assertEqual(mock_get.call_count, 1)

    @patch.object(MeliCatalogService, 'get_user_info')
    def test_competitor_enrichment(self, mock_user_info):
        """Testa enriquecimento de concorrente com nome do vendedor"""
        mock_user_info.return_value = {
            "seller_id": "776655",
            "nickname": "SOLAR_STORE_BR",
            "reputation_level": "5_green",
            "power_seller_status": "gold",
            "city": "Curitiba",
            "state": "PR"
        }

        raw_item = {
            "id": "MLB332211",
            "price": 4999.00,
            "seller_id": 776655,
            "shipping": {"logistic_type": "fulfillment"}
        }
        buy_box_winner = {"item_id": "MLB332211"}

        parsed = self.catalog_service._parse_competitor_item(raw_item, buy_box_winner)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["item_id"], "MLB332211")
        self.assertEqual(parsed["seller_name"], "SOLAR_STORE_BR")
        self.assertEqual(parsed["power_seller_status"], "gold")
        self.assertTrue(parsed["is_buy_box_winner"])
        self.assertEqual(parsed["logistic_type"], "fulfillment")


if __name__ == "__main__":
    unittest.main()
