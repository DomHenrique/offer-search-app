"""
tests/test_meli_catalog_filter.py
Testes unitários para validação do filtro estrito de catálogos ativos com concorrentes.
"""

import unittest
from unittest.mock import MagicMock, patch
from services.meli.catalog import MeliCatalogService


class TestMeliCatalogFilter(unittest.TestCase):

    def setUp(self):
        self.mock_client = MagicMock()
        self.catalog_service = MeliCatalogService(client=self.mock_client)

    @patch.object(MeliCatalogService, '_enrich_prices')
    def test_search_catalog_products_filters_inactive_catalogs(self, mock_enrich):
        # Simula retorno do Meli com catálogo ativo e catálogo sem vendedores
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "MLB50138807",
                    "name": "Gerador Ecoflow River 3 Plus 286wh",
                    "status": "active",
                    "pictures": [{"url": "https://img.jpg"}]
                },
                {
                    "id": "MLB49179811",
                    "name": "Kit Ecoflow Gerador Delta 2 1800w 220v + Painel 160w",
                    "status": "active",
                    "pictures": [{"url": "https://img2.jpg"}]
                }
            ],
            "paging": {"total": 2, "offset": 0, "limit": 50}
        }
        self.mock_client.get.return_value = mock_response

        # Simula o enriquecimento de preços e contagem de vendedores
        def side_effect_enrich(products, user_id=None):
            for p in products:
                if p["catalog_id"] == "MLB50138807":
                    p["price"] = 2300.0
                    p["buybox_min_price"] = 2300.0
                    p["sellers_count"] = 3
                elif p["catalog_id"] == "MLB49179811":
                    p["price"] = 0.0
                    p["buybox_min_price"] = 0.0
                    p["sellers_count"] = 0

        mock_enrich.side_effect = side_effect_enrich

        # Executa com only_active=True (padrão)
        res = self.catalog_service.search_catalog_products("Ecoflow", only_active=True)

        self.assertTrue(res["success"])
        self.assertEqual(len(res["results"]), 1)
        self.assertEqual(res["results"][0]["catalog_id"], "MLB50138807")
        self.assertEqual(res["results"][0]["price"], 2300.0)
        self.assertEqual(res["results"][0]["sellers_count"], 3)

    @patch.object(MeliCatalogService, '_enrich_prices')
    def test_search_catalog_products_allows_all_when_only_active_false(self, mock_enrich):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"id": "MLB50138807", "name": "Ativo"},
                {"id": "MLB49179811", "name": "Inativo"}
            ],
            "paging": {"total": 2, "offset": 0, "limit": 50}
        }
        self.mock_client.get.return_value = mock_response

        def side_effect_enrich(products, user_id=None):
            for p in products:
                if p["catalog_id"] == "MLB50138807":
                    p["price"] = 2300.0
                    p["sellers_count"] = 3
                else:
                    p["price"] = 0.0
                    p["sellers_count"] = 0

        mock_enrich.side_effect = side_effect_enrich

        res = self.catalog_service.search_catalog_products("Ecoflow", only_active=False)
        self.assertEqual(len(res["results"]), 2)


if __name__ == '__main__':
    unittest.main()
