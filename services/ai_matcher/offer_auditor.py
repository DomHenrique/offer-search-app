"""
services/ai_matcher/offer_auditor.py
Grafo de Auditoria de Ofertas e Catálogos utilizando LangGraph e LangChain.
Avalia a correspondência entre ofertas encontradas (Mercado Livre / Amazon) e o Dossiê Canônico do SKU.
"""

import re
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
from langgraph.graph import StateGraph, START, END

from services.ai_matcher.schemas import OfferAuditState, MatchAuditResult
from services.ai_matcher.heuristic_guard import run_heuristic_guard
from services.ai_matcher.dossier_builder import build_and_save_sku_dossier
from services.ai_provider import get_active_user_ai_model


def heuristic_step(state: OfferAuditState) -> Dict[str, Any]:
    """Nó do Guardião Heurístico sem custo de tokens"""
    candidate = state["candidate"]
    dossier = state["dossier"]

    passed, early_result = run_heuristic_guard(candidate, dossier)
    if not passed and early_result:
        return {
            "heuristic_passed": False,
            "heuristic_reason": early_result.explanation,
            "audit_result": early_result.model_dump()
        }

    return {
        "heuristic_passed": True,
        "heuristic_reason": "Passou pela triagem heurística preliminar."
    }


def llm_audit_step(state: OfferAuditState, chat_model=None) -> Dict[str, Any]:
    """Nó de Auditoria Semântica com IA ou contingência inteligente"""
    candidate = state["candidate"]
    dossier = state["dossier"] or {}

    cand_title = candidate.get("title") or candidate.get("nome") or candidate.get("name") or "Sem título"
    cand_price = float(candidate.get("price") or candidate.get("preco") or candidate.get("buybox_min_price") or 0.0)
    cand_attrs = candidate.get("attributes") or {}

    # Se a LLM estiver configurada e ativa
    if chat_model:
        try:
            prompt = (
                "Você é o Agente Auditor de Correspondência de Catálogos e Produtos de Estoque.\n"
                "Sua missão é confrontar a Oferta Candidata com o Dossiê Canônico de Verdade do nosso SKU "
                "e determinar com absoluta certeza se tratam do MESMO produto, uma variação técnica ou algo incompatível.\n\n"
                "DOSSIÊ CANÔNICO DO PRODUTO (Estoque):\n"
                f"- SKU: {state.get('sku')}\n"
                f"- Título Canônico: {dossier.get('canonical_title')}\n"
                f"- Marca: {dossier.get('brand')}\n"
                f"- Modelo Exato: {dossier.get('model')}\n"
                f"- EAN/GTIN: {dossier.get('gtin_ean') or 'Não informado'}\n"
                f"- Voltagem: {dossier.get('voltage') or 'Não especificada'}\n"
                f"- Especificações: {dossier.get('specs')}\n"
                f"- Faixa de Sanidade de Preço: R$ {dossier.get('price_sanity_min', 0):.2f} até R$ {dossier.get('price_sanity_max', 0):.2f}\n\n"
                "OFERTA CANDIDATA ENCONTRADA:\n"
                f"- ID Catálogo/Anúncio: {candidate.get('catalog_id') or candidate.get('id')}\n"
                f"- Título da Oferta: {cand_title}\n"
                f"- Preço: R$ {cand_price:.2f}\n"
                f"- Atributos Técnicos da Oferta: {cand_attrs}\n\n"
                "REGRAS DE CLASSIFICAÇÃO:\n"
                "1. EXACT_MATCH (Score 90-100%): É estritamente o mesmo produto, mesma voltagem, mesma capacidade e geração.\n"
                "2. VARIATION_MISMATCH (Score 65-85%): É o mesmo modelo principal, mas a voltagem (ex: 220V em vez de 127V) ou cor difere.\n"
                "3. ACCESSORY_WARNING (Score 5-30%): Trata-se de bolsa, cabo, suporte, painel solar avulso ou combo desproporcional.\n"
                "4. WRONG_PRODUCT (Score 0-25%): Produto de outra linha, outra marca ou modelo diferente.\n"
                "Seja rigoroso, objetivo e gere uma explicação clara em português para orientar o operador."
            )

            structured_llm = chat_model.with_structured_output(MatchAuditResult)
            result: MatchAuditResult = structured_llm.invoke(prompt)
            return {"audit_result": result.model_dump()}

        except Exception as e:
            print(f"⚠️ Erro na chamada da LLM de auditoria: {e}. Executando fallback determinístico...")

    # Fallback Semântico / Heurístico Inteligente
    cand_lower = cand_title.lower()
    dossier_voltage = str(dossier.get("voltage") or "").upper()
    
    # Checagem de voltagem
    cand_voltage = ""
    if re.search(r'\b(110|127)v\b', cand_lower):
        cand_voltage = "127V"
    elif re.search(r'\b220v\b', cand_lower):
        cand_voltage = "220V"
    elif re.search(r'\bbivolt\b', cand_lower):
        cand_voltage = "Bivolt"

    # Comparativo de Marca
    brand = (dossier.get("brand") or "").lower()
    brand_match = brand in cand_lower if brand else True

    # Comparativo de Voltagem
    voltage_match = True
    if dossier_voltage and cand_voltage:
        voltage_match = (dossier_voltage == cand_voltage) or ("BIVOLT" in [dossier_voltage, cand_voltage])

    if not brand_match:
        res = MatchAuditResult(
            score=20,
            verdict="WRONG_PRODUCT",
            badge_label="Marca Diferente (20%)",
            badge_color="danger",
            explanation=f"A marca do anúncio parece diferir da marca registrada no Dossiê ({dossier.get('brand')}).",
            is_safe_to_autolink=False
        )
    elif not voltage_match:
        res = MatchAuditResult(
            score=72,
            verdict="VARIATION_MISMATCH",
            badge_label=f"Variação {cand_voltage} (72%)",
            badge_color="warning",
            explanation=f"Mesmo modelo aparente, porém a voltagem detectada é {cand_voltage} (seu estoque registra {dossier_voltage}).",
            is_safe_to_autolink=False
        )
    else:
        res = MatchAuditResult(
            score=94,
            verdict="EXACT_MATCH",
            badge_label="Compatível (94%)",
            badge_color="success",
            explanation="Produto compatível com as especificações do Dossiê Canônico do SKU.",
            is_safe_to_autolink=True
        )

    return {"audit_result": res.model_dump()}


def route_heuristic_or_llm(state: OfferAuditState) -> str:
    """Roteamento condicional no LangGraph"""
    if state.get("audit_result") is not None:
        return END
    return "llm_audit_step"


def create_offer_audit_graph(chat_model=None):
    """Compila o grafo de auditoria de ofertas do LangGraph"""
    workflow = StateGraph(OfferAuditState)

    workflow.add_node("heuristic_step", heuristic_step)
    workflow.add_node("llm_audit_step", lambda s: llm_audit_step(s, chat_model=chat_model))

    workflow.add_edge(START, "heuristic_step")
    workflow.add_conditional_edges(
        "heuristic_step",
        route_heuristic_or_llm,
        {
            END: END,
            "llm_audit_step": "llm_audit_step"
        }
    )
    workflow.add_edge("llm_audit_step", END)

    return workflow.compile()


def audit_single_candidate(user_id: str, sku: str, candidate: Dict[str, Any], dossier: Dict[str, Any], chat_model=None) -> Dict[str, Any]:
    """Audita uma única oferta candidata contra o Dossiê Canônico do SKU"""
    initial_state: OfferAuditState = {
        "user_id": user_id,
        "sku": sku,
        "dossier": dossier,
        "candidate": candidate,
        "heuristic_passed": True,
        "heuristic_reason": "",
        "audit_result": None
    }

    graph = create_offer_audit_graph(chat_model=chat_model)
    final_state = graph.invoke(initial_state)
    return final_state.get("audit_result") or {}


def audit_offers_batch(user_id: str, sku: str, candidates: List[Dict[str, Any]], db_manager) -> List[Dict[str, Any]]:
    """
    Audita uma lista de ofertas ou catálogos candidatos contra o Dossiê do SKU em paralelo.
    Enriquece cada candidato na lista com a chave 'ai_audit'.
    """
    if not sku or not candidates:
        return candidates

    sku_clean = str(sku).strip().upper()
    dossier = db_manager.get_sku_knowledge(user_id, sku_clean)
    if not dossier:
        # Cria e salva o dossiê inicial caso ainda não exista
        dossier = build_and_save_sku_dossier(user_id, sku_clean, db_manager)

    chat_model, _, _ = get_active_user_ai_model(user_id, db_manager)

    def _audit_one(c: Dict[str, Any]):
        try:
            audit = audit_single_candidate(user_id, sku_clean, c, dossier, chat_model=chat_model)
            c["ai_audit"] = audit
            # Salva também no banco caso o catálogo já esteja vinculado
            cid = c.get("catalog_id") or c.get("id")
            if cid:
                db_manager.update_sku_catalog_audit(user_id, sku_clean, cid, audit)
        except Exception as e:
            print(f"Erro ao auditar candidato {c.get('catalog_id')}: {e}")
            c["ai_audit"] = {
                "score": 50,
                "verdict": "UNKNOWN",
                "badge_label": "Pendente",
                "badge_color": "secondary",
                "explanation": "Auditoria pendente de reprocessamento."
            }
        return c

    # Executa auditoria em paralelo para agilidade
    max_workers = min(8, len(candidates)) if len(candidates) > 0 else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        enriched_candidates = list(executor.map(_audit_one, candidates))

    return enriched_candidates
