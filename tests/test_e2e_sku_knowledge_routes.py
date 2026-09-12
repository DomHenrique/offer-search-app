"""
Teste de integração E2E para rotas Flask e persistência Supabase
Testa:
- POST /inventory/api/sku/<sku>/reference-listing
- POST /inventory/api/sku/<sku>/resynthesize-dossier
- GET /inventory/api/sku/<sku>/knowledge
- POST /catalog/api/audit-candidate
- DELETE /inventory/api/sku/<sku>/reference-listing/<id>
"""

import unittest
import json
from app import app
from database.db_manager import DatabaseManager


class TestE2ESkuKnowledgeRoutes(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        self.db = DatabaseManager()
        self.test_user_id = "test_e2e_user"
        self.test_sku = "TEST-AFN40-BI"

    def test_e2e_inventory_and_catalog_ai_flow(self):
        """Valida o ciclo de vida completo do Dossiê Canônico e Auditoria de Catálogos"""
        with self.app.session_transaction() as sess:
            sess['user_id'] = self.test_user_id
            sess['user_email'] = 'test_e2e@antigravity.ai'

        # 1. Adicionar anúncio de referência ao SKU
        res_add = self.app.post(
            f'/inventory/api/sku/{self.test_sku}/reference-listing',
            data=json.dumps({
                'url_or_id': 'https://www.mercadolivre.com.br/p/MLB28912345',
                'is_own_store': True
            }),
            content_type='application/json'
        )
        self.assertIn(res_add.status_code, [200, 201])
        data_add = json.loads(res_add.data)
        self.assertTrue(data_add.get('success'))
        saved_ref = data_add.get('reference') or {}
        ref_id = saved_ref.get('id')
        self.assertIsNotNone(ref_id)

        # 2. Consultar o Dossiê Canônico sintetizado
        res_know = self.app.get(f'/inventory/api/sku/{self.test_sku}/knowledge')
        self.assertEqual(res_know.status_code, 200)
        data_know = json.loads(res_know.data)
        self.assertTrue(data_know.get('success'))
        self.assertIsNotNone(data_know.get('knowledge'))
        self.assertGreaterEqual(len(data_know.get('reference_listings', [])), 1)

        # 3. Auditar uma oferta candidata de catálogo contra esse SKU
        res_audit = self.app.post(
            '/catalog/api/audit-candidate',
            data=json.dumps({
                'catalog_id': 'MLB28912345',
                'sku': self.test_sku,
                'title': 'Fritadeira Sem Óleo Air Fryer Mondial AFN-40-BI 127V',
                'price': 299.00
            }),
            content_type='application/json'
        )
        self.assertEqual(res_audit.status_code, 200)
        data_audit = json.loads(res_audit.data)
        self.assertTrue(data_audit.get('success'))
        audit_res = data_audit.get('audit', {})
        self.assertIn('score', audit_res)
        self.assertIn('verdict', audit_res)

        # 4. Remover o anúncio de referência de teste para limpeza
        if ref_id:
            res_del = self.app.delete(f'/inventory/api/sku/{self.test_sku}/reference-listing/{ref_id}')
            self.assertEqual(res_del.status_code, 200)
            data_del = json.loads(res_del.data)
            self.assertTrue(data_del.get('success'))


if __name__ == '__main__':
    unittest.main()
