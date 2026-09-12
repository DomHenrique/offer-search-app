"""
services/ai_matcher/heuristic_guard.py
Guardião Heurístico ultrarrápido (Custo Zero de Tokens).
Elimina 80% dos acessórios, peças de reposição e ofertas com preços fora da sanidade
antes de qualquer chamada aos agentes LLM.
"""

import re
from typing import Dict, Any, Tuple, Optional
from services.ai_matcher.schemas import MatchAuditResult


def run_heuristic_guard(candidate: Dict[str, Any], dossier: Dict[str, Any]) -> Tuple[bool, Optional[MatchAuditResult]]:
    """
    Executa a verificação preliminar por regras estritas.
    Retorna:
      - (True, None): se o candidato for plausível e deve ser auditado pela LLM.
      - (False, MatchAuditResult): se o candidato foi reprovado ou confirmado diretamente.
    """
    if not dossier:
        # Se não há dossiê, deixa passar para o auditor geral
        return True, None

    candidate_title = (candidate.get("title") or candidate.get("nome") or candidate.get("name") or "").lower()
    candidate_price = float(candidate.get("price") or candidate.get("preco") or candidate.get("buybox_min_price") or 0.0)
    candidate_gtin = str(candidate.get("gtin") or candidate.get("ean") or "").strip()

    dossier_gtin = str(dossier.get("gtin_ean") or "").strip()
    negative_terms = [str(t).lower().strip() for t in dossier.get("negative_terms") or [] if t]
    price_min = float(dossier.get("price_sanity_min") or 0.0)
    price_max = float(dossier.get("price_sanity_max") or 0.0)

    # 1. Checagem de Lista Negra de Termos Proibidos (Anti-Acessórios)
    for term in negative_terms:
        # Busca como palavra inteira para evitar falsos positivos
        pattern = rf'\b{re.escape(term)}\b'
        if re.search(pattern, candidate_title):
            # Se o próprio dossiê canônico tem o termo no título principal, ignora
            if term not in (dossier.get("canonical_title") or "").lower():
                result = MatchAuditResult(
                    score=10,
                    verdict="ACCESSORY_WARNING",
                    badge_label="Acessório (10%)",
                    badge_color="danger",
                    explanation=f"Oferta reprovada pelo Guardião Heurístico: contém o termo '{term}', caracterizando acessório ou peça avulsa.",
                    specs_breakdown={
                        "rule": "negative_term_detected",
                        "detected_term": term,
                        "candidate_title": candidate_title
                    },
                    is_safe_to_autolink=False
                )
                return False, result

    # 2. Checagem de Sanidade Financeira (Preço Anômalo)
    if candidate_price > 0 and price_min > 0:
        if candidate_price < (price_min * 0.7):
            result = MatchAuditResult(
                score=15,
                verdict="ACCESSORY_WARNING",
                badge_label="Preço Anômalo (15%)",
                badge_color="danger",
                explanation=f"Preço de R$ {candidate_price:.2f} está muito abaixo do valor de sanidade (mínimo R$ {price_min:.2f}). Trata-se de acessório, cabo ou peça de reposição.",
                specs_breakdown={
                    "rule": "price_sanity_below_min",
                    "candidate_price": candidate_price,
                    "sanity_min": price_min
                },
                is_safe_to_autolink=False
            )
            return False, result

    # 3. Se tiver correspondência EAN idêntica, pontua diretamente
    if candidate_gtin and dossier_gtin and candidate_gtin == dossier_gtin:
        # EAN idêntico é uma confirmação quase garantida
        result = MatchAuditResult(
            score=98,
            verdict="EXACT_MATCH",
            badge_label="EAN Idêntico (98%)",
            badge_color="success",
            explanation=f"Código de barras oficial (EAN/GTIN {candidate_gtin}) idêntico ao do Dossiê do produto. Certeza absoluta de correspondência.",
            specs_breakdown={
                "rule": "ean_exact_match",
                "ean": candidate_gtin
            },
            is_safe_to_autolink=True
        )
        return False, result

    # Passou no Guardião Heurístico sem reprovação imediata nem EAN absoluto
    return True, None
