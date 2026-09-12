"""
Testes automatizados da suíte LangGraph Product Knowledge & AI Audit Engine
Valida:
1. Provedores de IA (suporte e metadados)
2. Extrator de atributos e identificação de marketplaces (ML e Amazon)
3. Guardião heurístico (filtros anti-acessório e sanidade de preço)
4. Auditor de Ofertas (LangGraph OfferAuditState / vereditos estruturados determinísticos)
"""

import unittest
from services.ai_provider import list_supported_providers, fetch_available_models
from services.reference_listings_extractor import extract_reference_listing
from services.ai_matcher.heuristic_guard import run_heuristic_guard
from services.ai_matcher.schemas import MatchAuditResult, CanonicalDossierOutput
from services.ai_matcher.offer_auditor import audit_single_candidate


class TestAIKnowledgeAuditEngine(unittest.TestCase):

    def test_01_ai_provider_metadata(self):
        """Verifica se os provedores Google, OpenAI, Anthropic e Groq estão devidamente configurados"""
        providers = list_supported_providers()
        prov_dict = {p['id']: p for p in providers}
        
        self.assertIn('google', prov_dict)
        self.assertIn('openai', prov_dict)
        self.assertIn('anthropic', prov_dict)
        self.assertIn('groq', prov_dict)
        self.assertTrue(len(prov_dict['google']['curated_models']) > 0)
        self.assertTrue(len(prov_dict['openai']['curated_models']) > 0)

    def test_02_reference_listing_extractor(self):
        """Verifica a extração e normalização de URLs do Mercado Livre e Amazon"""
        # Teste extração Mercado Livre por URL / p/
        listing_ml = extract_reference_listing("https://www.mercadolivre.com.br/p/MLB28912345")
        self.assertEqual(listing_ml['marketplace'], 'MercadoLivre')
        self.assertIn('MLB', listing_ml['listing_id'])

        # Teste extração Amazon por URL
        listing_amz = extract_reference_listing("https://www.amazon.com.br/dp/B09V3K3Q85")
        self.assertEqual(listing_amz['marketplace'], 'Amazon')
        self.assertEqual(listing_amz['listing_id'], 'B09V3K3Q85')

    def test_03_heuristic_guard_accessory_detection(self):
        """Verifica se o Guardião Heurístico bloqueia acessórios sem gastar tokens"""
        dossier = {
            'canonical_title': 'Apple iPhone 15 Pro Max 256GB',
            'brand': 'Apple',
            'model': 'iPhone 15 Pro Max',
            'negative_terms': ['capa', 'película', 'capinha', 'cabo', 'suporte', 'case', 'carregador'],
            'price_sanity_min': 5000.0,
            'price_sanity_max': 12000.0
        }

        # 1. Candidato que é uma capa/capinha (acessório)
        candidate_acc = {
            'title': "Capa Case Silicone Aveludada MagSafe para iPhone 15 Pro Max",
            'price': 89.90
        }
        passed, result = run_heuristic_guard(candidate_acc, dossier)
        self.assertFalse(passed, "Deveria ter sido barrado pelo Guardião Heurístico")
        self.assertIsNotNone(result)
        self.assertEqual(result.verdict, "ACCESSORY_WARNING")
        self.assertLessEqual(result.score, 20)

        # 2. Candidato com preço suspeito / anômalo (< 70% do mínimo)
        candidate_price_low = {
            'title': "Apple iPhone 15 Pro Max 256GB Titânio Natural",
            'price': 990.00  # 990 reais num iPhone de 5000+
        }
        passed_p, result_p = run_heuristic_guard(candidate_price_low, dossier)
        self.assertFalse(passed_p, "Preço anômalo deveria disparar alarme de sanidade")
        self.assertIsNotNone(result_p)
        self.assertIn("preço", result_p.explanation.lower())

        # 3. Candidato legítimo (deve passar para a auditoria semântica)
        candidate_legit = {
            'title': "Apple iPhone 15 Pro Max 256GB Titânio Natural Original Lacrado",
            'price': 6499.00
        }
        passed_legit, result_legit = run_heuristic_guard(candidate_legit, dossier)
        self.assertTrue(passed_legit, "Produto legítimo deve passar na triagem heurística")
        self.assertIsNone(result_legit)

    def test_04_offer_audit_fallback_and_verdicts(self):
        """Testa o grafo de auditoria do LangGraph em cenário determinístico (sem chaves ativas)"""
        dossier = {
            'canonical_title': 'Fritadeira Sem Óleo Air Fryer Mondial AFN-40-BI 127V',
            'brand': 'Mondial',
            'model': 'AFN-40-BI',
            'voltage': '127V',
            'gtin_ean': '7899882301111',
            'specs': {
                'brand': 'Mondial',
                'model': 'AFN-40-BI',
                'voltage': '127V',
                'gtin_ean': '7899882301111'
            },
            'negative_terms': ['cesto', 'grade', 'forma', 'cabo', 'puxador'],
            'price_sanity_min': 200.0,
            'price_sanity_max': 550.0
        }

        # 1. Match idêntico com EAN
        candidate_exact = {
            'title': "Fritadeira Sem Óleo Air Fryer Mondial AFN-40-BI 127V 7899882301111",
            'price': 299.90,
            'gtin': '7899882301111',
            'attributes': {'Voltagem': '127V'}
        }
        res_exact = audit_single_candidate("test_user", "AFN-40-BI", candidate_exact, dossier)
        self.assertGreaterEqual(res_exact['score'], 80)
        self.assertIn(res_exact['verdict'], ['EXACT_MATCH', 'COMPATIBLE_MATCH'])

        # 2. Divergência de voltagem
        candidate_diff_volt = {
            'title': "Fritadeira Air Fryer Mondial AFN-40-BI 220V",
            'price': 299.90,
            'attributes': {'Voltagem': '220V'}
        }
        res_diff_volt = audit_single_candidate("test_user", "AFN-40-BI", candidate_diff_volt, dossier)
        self.assertEqual(res_diff_volt['verdict'], 'VARIATION_MISMATCH')
        self.assertFalse(res_diff_volt['specs_breakdown'].get('voltage_match'))

        # 3. Acessório barrado
        candidate_acc = {
            'title': "Cesto Removível Antiaderente para Fritadeira Mondial AFN-40-BI",
            'price': 65.00
        }
        res_acc = audit_single_candidate("test_user", "AFN-40-BI", candidate_acc, dossier)
        self.assertEqual(res_acc['verdict'], 'ACCESSORY_WARNING')
        self.assertLessEqual(res_acc['score'], 20)


if __name__ == '__main__':
    unittest.main()
