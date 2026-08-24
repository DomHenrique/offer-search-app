import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('SUPABASE_URL', 'https://mock.supabase.co')
os.environ.setdefault('SUPABASE_KEY', 'mock-key')

with patch('supabase.create_client', return_value=MagicMock()):
    from routes.extension_routes import _calculate_margin_metrics, extension_bp

from flask import Flask


class TestExtensionRoutes(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-secret'
        self.app.register_blueprint(extension_bp)
        self.client = self.app.test_client()

    def test_calculate_margin_metrics_profitable(self):
        # Custo 2195, Venda 5518.03 -> Taxa ML (16% = 882.88) -> Lucro Líquido = 5518.03 - 882.88 - 2195 = 2440.15 (44.2%)
        metrics = _calculate_margin_metrics(cost=2195.0, sell_price=5518.03)
        self.assertEqual(metrics['status'], 'EXCELLENT_MARGIN')
        self.assertGreater(metrics['net_profit'], 2000.0)
        self.assertGreater(metrics['margin_pct'], 15.0)

    def test_calculate_margin_metrics_negative(self):
        # Custo 1000, Venda 800 -> Prejuízo
        metrics = _calculate_margin_metrics(cost=1000.0, sell_price=800.0)
        self.assertEqual(metrics['status'], 'NEGATIVE_MARGIN')
        self.assertLess(metrics['net_profit'], 0.0)

    def test_calculate_margin_metrics_zero_price(self):
        metrics = _calculate_margin_metrics(cost=500.0, sell_price=0.0)
        self.assertEqual(metrics['status'], 'NO_PRICE')
        self.assertEqual(metrics['net_profit'], 0.0)

    @patch('routes.extension_routes.db_manager')
    def test_get_product_intel_unlinked(self, mock_db):
        mock_db.get_sku_catalogs.return_value = []
        mock_db.get_consolidated_inventory.return_value = [
            {'sku': 'SKU-001', 'descricao': 'Produto Teste', 'preco_custo': 100.0, 'quantidade_total': 5}
        ]

        res = self.client.get('/api/extension/product-intel?catalog_id=MLB999999')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data['is_linked'])
        self.assertEqual(data['catalog_id'], 'MLB999999')
        self.assertTrue(len(data['suggestions']) > 0)

    @patch('routes.extension_routes.db_manager')
    def test_get_product_intel_linked(self, mock_db):
        mock_db.get_sku_catalogs.return_value = [
            {
                'catalog_id': 'MLB62844982',
                'sku': 'ECO-GR32EU1010',
                'buybox_min_price': 5518.03,
                'buybox_winner': 'EcoFlow Oficial'
            }
        ]
        mock_db.get_consolidated_inventory.return_value = [
            {
                'sku': 'ECO-GR32EU1010',
                'descricao': 'Gerador River 3 Max Plus',
                'preco_custo': 2195.0,
                'preco_site_pix': 2439.0,
                'quantidade_total': 2
            }
        ]

        res = self.client.get('/api/extension/product-intel?catalog_id=MLB62844982')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['is_linked'])
        self.assertEqual(data['sku'], 'ECO-GR32EU1010')
        self.assertEqual(data['estoque_total'], 2)
        self.assertIn('margin', data)
        self.assertEqual(data['margin']['status'], 'EXCELLENT_MARGIN')

    @patch('routes.extension_routes.db_manager')
    def test_inventory_list_search(self, mock_db):
        mock_db.get_consolidated_inventory.return_value = [
            {'sku': 'ECO-01', 'descricao': 'Ecoflow Delta', 'preco_custo': 5000.0, 'quantidade_total': 3},
            {'sku': 'PAN-02', 'descricao': 'Painel Solar 160W', 'preco_custo': 800.0, 'quantidade_total': 10}
        ]

        res = self.client.get('/api/extension/inventory-list?q=delta')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['items'][0]['sku'], 'ECO-01')

    @patch('routes.extension_routes.db_manager')
    def test_link_sku_success(self, mock_db):
        mock_db.link_catalog_to_sku.return_value = {'status': 'ok'}
        mock_db.get_consolidated_inventory.return_value = [
            {'sku': 'ECO-01', 'descricao': 'Ecoflow Delta', 'preco_custo': 5000.0, 'quantidade_total': 3}
        ]

        payload = {
            'catalog_id': 'MLB12345',
            'sku': 'ECO-01',
            'catalog_title': 'Ecoflow Delta 220V',
            'buybox_min_price': 7500.0
        }
        res = self.client.post('/api/extension/link-sku', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['product_intel']['is_linked'])
        self.assertEqual(data['product_intel']['sku'], 'ECO-01')


if __name__ == '__main__':
    unittest.main()
