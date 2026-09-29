"""
tests/test_bulk_batch_actions.py
Testes unitários e de integração para Ações em Massa (Bulk Actions):
- Vinculação e Desvinculação em Lote de Catálogos (DatabaseManager e Rotas)
- Varredura Sequencial de Concorrentes em Lote e Polling
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db_manager import DatabaseManager
from app import app
from routes.catalog_routes import catalog_sellers_status


class TestBulkBatchActions(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['SECRET_KEY'] = 'test-secret-bulk'
        self.client = self.app.test_client()
        self.db = DatabaseManager()

    @patch('database.db_manager.DatabaseManager._get_user_uuid', return_value='11111111-1111-1111-1111-111111111111')
    def test_db_unlink_catalogs_batch_10_plus(self, mock_user_uuid):
        """Testa o método unlink_catalogs_batch com 12 catálogos (10+)"""
        mock_supabase = MagicMock()
        self.db.supabase = mock_supabase

        catalog_ids = [f"MLB1000{i}" for i in range(12)]
        sku = "ECO-DELTA2"

        success = self.db.unlink_catalogs_batch("user-123", sku, catalog_ids)
        self.assertTrue(success)

        # Verifica se chamou a tabela sku_catalogs e delete com in_
        mock_supabase.table.assert_called_with("sku_catalogs")
        table_mock = mock_supabase.table.return_value
        table_mock.delete.assert_called_once()
        del_mock = table_mock.delete.return_value
        del_mock.eq.assert_any_call("user_id", '11111111-1111-1111-1111-111111111111')
        del_mock.eq.return_value.eq.assert_called_with("sku", "ECO-DELTA2")
        del_mock.eq.return_value.eq.return_value.in_.assert_called_with("catalog_id", catalog_ids)

    @patch('database.db_manager.DatabaseManager._get_user_uuid', return_value='11111111-1111-1111-1111-111111111111')
    def test_db_link_catalogs_batch(self, mock_user_uuid):
        """Testa o método link_catalogs_batch com múltiplos formatos de entrada"""
        mock_supabase = MagicMock()
        mock_upsert = MagicMock()
        mock_upsert.execute.return_value.data = [{"catalog_id": "MLB1"}, {"catalog_id": "MLB2"}]
        mock_supabase.table.return_value.upsert.return_value = mock_upsert
        self.db.supabase = mock_supabase

        catalogs_data = [
            "MLB1",
            {"catalog_id": "MLB2", "catalog_title": "EcoFlow River 3", "buybox_min_price": 2999.0}
        ]
        sku = "ECO-RIVER3"

        res = self.db.link_catalogs_batch("user-123", sku, catalogs_data)
        self.assertEqual(len(res), 2)
        mock_supabase.table.assert_called_with("sku_catalogs")

    def test_api_unlink_catalogs_batch(self):
        """Testa a rota POST /inventory/unlink-catalogs-batch"""
        with self.client.session_transaction() as sess:
            sess['user_id'] = '11111111-1111-1111-1111-111111111111'

        with patch.object(DatabaseManager, 'unlink_catalogs_batch', return_value=True):
            resp = self.client.post('/inventory/unlink-catalogs-batch', json={
                'sku': 'ECO-DELTA2',
                'catalog_ids': ['MLB1001', 'MLB1002', 'MLB1003']
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data['success'])
            self.assertEqual(data['unlinked_count'], 3)
            self.assertEqual(data['sku'], 'ECO-DELTA2')

    def test_api_link_catalogs_batch(self):
        """Testa a rota POST /inventory/link-catalogs-batch"""
        with self.client.session_transaction() as sess:
            sess['user_id'] = '11111111-1111-1111-1111-111111111111'

        with patch.object(DatabaseManager, 'link_catalogs_batch', return_value=[{'catalog_id': 'MLB1'}, {'catalog_id': 'MLB2'}]):
            resp = self.client.post('/inventory/link-catalogs-batch', json={
                'sku': 'ECO-DELTA2',
                'catalog_items': ['MLB1', 'MLB2']
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data['success'])
            self.assertEqual(data['linked_count'], 2)

    def test_api_batch_scrape_sellers_and_polling(self):
        """Testa a rota POST /catalog/batch-scrape-sellers e endpoint de polling"""
        with self.client.session_transaction() as sess:
            sess['user_id'] = '11111111-1111-1111-1111-111111111111'

        with patch('routes.catalog_routes.threading.Thread') as mock_thread:
            resp = self.client.post('/catalog/batch-scrape-sellers', json={
                'catalog_ids': ['MLB101', 'MLB102', 'MLB103']
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data['success'])
            self.assertEqual(data['total'], 3)
            self.assertIn('batch_id', data)

            batch_id = data['batch_id']
            # Simula atualização na memória de status
            catalog_sellers_status[batch_id]['progress'] = 66
            catalog_sellers_status[batch_id]['message'] = 'Processando item 2 de 3'

            # Polling
            poll_resp = self.client.get(f'/catalog/sellers-status/{batch_id}')
            self.assertEqual(poll_resp.status_code, 200)
            poll_data = poll_resp.get_json()
            self.assertEqual(poll_data['progress'], 66)
            self.assertEqual(poll_data['message'], 'Processando item 2 de 3')


if __name__ == '__main__':
    unittest.main()
