"""
tests/test_product_scanner.py
Testes unitários e de integração para o Scanner Inteligente de Produtos,
Matching Multi-critério com Inventário e Auditoria de Loja Própria.
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import json

# Adiciona diretório raiz ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from services.reference_listings_extractor import extract_reference_listing
from services.inventory_matcher import InventoryMatcher, _tokenize, _clean_barcode
from services.listing_auditor import ListingAuditor
from app import app


class TestProductScanner(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = self.app.test_client()

    def test_barcode_and_token_helpers(self):
        """Valida sanitização de código de barras e tokenização"""
        self.assertEqual(_clean_barcode('789-1234-567890'), '7891234567890')
        self.assertEqual(_clean_barcode('123'), '')  # Muito curto

        tokens = _tokenize('Estação de Energia Portátil EcoFlow Delta 2 com 1024Wh')
        self.assertIn('estacao', tokens)
        self.assertIn('ecoflow', tokens)
        self.assertIn('delta', tokens)
        self.assertNotIn('de', tokens)  # Stopword

    def test_extract_reference_listing_roles(self):
        """Valida que a extração atribui papéis e flags corretamente"""
        # 1. Loja Própria
        res_own = extract_reference_listing('MLB999888777', role='own_store')
        self.assertEqual(res_own['listing_role'], 'own_store')
        self.assertTrue(res_own['is_own_store'])
        self.assertEqual(res_own['marketplace'], 'MercadoLivre')

        # 2. Fornecedor
        res_sup = extract_reference_listing('https://fornecedor-exemplo.com.br/delta-2', role='supplier')
        self.assertEqual(res_sup['listing_role'], 'supplier')
        self.assertFalse(res_sup['is_own_store'])
        self.assertEqual(res_sup['marketplace'], 'Fornecedor')

        # 3. Concorrente
        res_comp = extract_reference_listing('https://concorrente-loja.com.br/produto', role='competitor')
        self.assertEqual(res_comp['listing_role'], 'competitor')
        self.assertFalse(res_comp['is_own_store'])
        self.assertEqual(res_comp['marketplace'], 'Concorrente')

    def test_inventory_matcher_scoring_tiers(self):
        """Valida algoritmo multi-critério de pontuação"""
        mock_db = MagicMock()
        mock_db.get_consolidated_inventory.return_value = [
            {
                "sku": "ECO-DELTA2",
                "descricao": "Estação de Energia EcoFlow Delta 2 1024Wh",
                "termo_busca": "EcoFlow Delta 2",
                "ean": "7898765432101",
                "preco_custo": 1400.0,
                "preco_revenda": 1800.0,
                "quantidade_total": 10,
                "catalogs": [{"catalog_id": "MLB112233"}]
            },
            {
                "sku": "ECO-RIVER2",
                "descricao": "Estação Portátil EcoFlow River 2 256Wh",
                "termo_busca": "EcoFlow River 2",
                "ean": "7891112223334",
                "preco_custo": 800.0,
                "preco_revenda": 1100.0,
                "quantidade_total": 5,
                "catalogs": []
            }
        ]
        mock_db._get_user_uuid.return_value = "mock-uuid"
        mock_db.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        matcher = InventoryMatcher(mock_db)

        # 1. Match Exato por EAN (100%)
        matches_ean = matcher.find_matches_for_listing("1", {
            "title": "Produto Qualquer",
            "gtin": "7898765432101"
        })
        self.assertTrue(len(matches_ean) > 0)
        self.assertEqual(matches_ean[0]['sku'], 'ECO-DELTA2')
        self.assertEqual(matches_ean[0]['match_score'], 100)
        self.assertEqual(matches_ean[0]['match_tier'], 'EXACT_EAN')

        # 2. Match por Catálogo Conectado (95%)
        matches_cat = matcher.find_matches_for_listing("1", {
            "title": "Produto Sem EAN",
            "listing_id": "MLB112233"
        })
        self.assertEqual(matches_cat[0]['sku'], 'ECO-DELTA2')
        self.assertEqual(matches_cat[0]['match_score'], 95)
        self.assertEqual(matches_cat[0]['match_tier'], 'CONNECTED_CATALOG')

        # 3. Match por SKU no Título (90%)
        matches_sku = matcher.find_matches_for_listing("1", {
            "title": "Bateria Modelo ECO-RIVER2 Original com Garantia",
            "listing_id": "MLB9999"
        })
        self.assertEqual(matches_sku[0]['sku'], 'ECO-RIVER2')
        self.assertEqual(matches_sku[0]['match_score'], 90)
        self.assertEqual(matches_sku[0]['match_tier'], 'SKU_IN_TITLE')

        # 4. Similaridade Semântica (Token Match)
        matches_tokens = matcher.find_matches_for_listing("1", {
            "title": "Estação de Energia Delta 2",
            "brand": "EcoFlow",
            "model": "Delta 2"
        })
        self.assertEqual(matches_tokens[0]['sku'], 'ECO-DELTA2')
        self.assertGreaterEqual(matches_tokens[0]['match_score'], 60)

    def test_listing_auditor_own_store(self):
        """Valida diagnóstico de saúde e alertas para anúncio da Loja Própria"""
        auditor = ListingAuditor(MagicMock())

        # Anúncio com falha de EAN e venda abaixo do custo
        result = auditor.audit_own_store_listing(
            user_id="1",
            extracted_data={
                "title": "Anúncio Teste",
                "price": 1000.0,
                "gtin": "",  # Sem EAN
                "raw_attributes": {"Marca": "EcoFlow"}  # Faltam vários campos
            },
            matched_sku_data={
                "sku": "ECO-DELTA2",
                "preco_custo": 1400.0,
                "preco_revenda": 1800.0
            }
        )

        self.assertTrue(result['is_own_store'])
        self.assertLess(result['completeness_score'], 50)
        self.assertEqual(result['status_label'], 'Crítico')

        issue_types = [i['type'] for i in result['issues']]
        self.assertIn('MISSING_EAN', issue_types)
        self.assertIn('INCOMPLETE_SPECS', issue_types)
        self.assertIn('SELLING_BELOW_COST', issue_types)

    @patch('routes.inventory_routes.build_and_save_sku_dossier')
    def test_api_endpoints_workflow(self, mock_dossier):
        """Valida os 4 endpoints via TestClient do Flask"""
        mock_dossier.return_value = {"status": "success"}

        with self.client.session_transaction() as sess:
            sess['user_id'] = '1'
            sess['user_name'] = 'Tester'

        # 1. POST /inventory/api/scanner/extract-and-match
        resp = self.client.post('/inventory/api/scanner/extract-and-match', json={
            'url_or_id': 'MLB123456789',
            'role': 'own_store'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('extracted_data', data)
        self.assertIn('candidates', data)
        self.assertIn('audit', data)

        # 2. POST /inventory/api/scanner/confirm-link
        resp_confirm = self.client.post('/inventory/api/scanner/confirm-link', json={
            'sku': 'ECO-DELTA2',
            'extracted_data': {
                'listing_id': 'MLB123456789',
                'listing_url': 'https://produto.mercadolivre.com.br/MLB-123456789',
                'title': 'Anúncio Confirmado Teste',
                'price': 1890.0,
                'gtin': '7898765432101',
                'raw_attributes': {'Marca': 'EcoFlow'}
            },
            'role': 'own_store'
        })
        self.assertEqual(resp_confirm.status_code, 200)
        self.assertTrue(resp_confirm.get_json()['success'])

        # 3. POST /inventory/api/scanner/quick-fill-attributes
        resp_qfill = self.client.post('/inventory/api/scanner/quick-fill-attributes', json={
            'sku': 'ECO-DELTA2',
            'attributes': {'Voltagem': '110V/220V', 'Capacidade': '1024Wh'}
        })
        self.assertEqual(resp_qfill.status_code, 200)
        self.assertTrue(resp_qfill.get_json()['success'])

        # 4. POST /inventory/api/scanner/create-sku-from-listing
        resp_create = self.client.post('/inventory/api/scanner/create-sku-from-listing', json={
            'sku': 'ECO-TEST-SKU-NEW',
            'descricao': 'Novo SKU Criado via Scanner',
            'preco_custo': 950.0,
            'preco_revenda': 1300.0,
            'role': 'supplier',
            'extracted_data': {
                'listing_url': 'https://fornecedor.com.br/novo-item',
                'title': 'Novo Item Fornecedor',
                'price': 950.0
            }
        })
        self.assertEqual(resp_create.status_code, 200)
        self.assertTrue(resp_create.get_json()['success'])


if __name__ == '__main__':
    unittest.main()
