"""
services/ai_matcher/dossier_builder.py
Grafo LangGraph para construção e síntese do Dossiê Canônico de Verdade (Ground Truth) do SKU.
Consolida descrições do estoque, pedidos de compra e anúncios ativos de referência da loja.
"""

import re
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from services.ai_matcher.schemas import DossierBuilderState, CanonicalDossierOutput
from services.ai_provider import get_active_user_ai_model


def synthesize_dossier_node(state: DossierBuilderState, chat_model=None) -> Dict[str, Any]:
    """Nó do agente que sintetiza o Dossiê Canônico de Verdade via LLM ou heurística"""
    sku = state["sku"]
    desc = state["descricao_pedido"] or sku
    fornecedor = state["fornecedor"] or ""
    custo = float(state.get("preco_custo") or 0.0)
    revenda = float(state.get("preco_revenda") or 0.0)
    refs = state.get("reference_listings") or []

    # Se tivermos chat_model ativo com structured output
    if chat_model:
        try:
            ref_texts = []
            for r in refs:
                m_place = r.get("marketplace", "")
                t = r.get("title", "")
                p = r.get("price", 0)
                ean = r.get("gtin", "")
                attrs = r.get("raw_attributes") or {}
                ref_texts.append(f"[{m_place}] {t} | Preço: R$ {p} | EAN: {ean} | Atributos: {attrs}")

            context_str = (
                f"SKU: {sku}\n"
                f"Descrição Compra: {desc}\n"
                f"Fornecedor: {fornecedor}\n"
                f"Preço Custo: R$ {custo:.2f} | Preço Revenda: R$ {revenda:.2f}\n"
                f"Anúncios de Referência Ativos:\n" + "\n".join(ref_texts if ref_texts else ["(Nenhum anúncio externo cadastrado ainda)"])
            )

            prompt = (
                "Você é o Curador Especialista de Conhecimento de Produtos para e-commerce e estoque.\n"
                "Sua missão é consolidar um Dossiê Canônico de Verdade (Ground Truth) à prova de falhas para o SKU informado.\n"
                "Identifique Marca, Modelo exato (incluindo sufixos como Plus, Pro, Max, Mini), Voltagem (110V, 127V, 220V ou Bivolt), "
                "Capacidade/Potência e código EAN oficial.\n"
                "Defina a lista de termos proibidos (anti-acessórios como cabos, capas, suportes que não devem ser confundidos com o produto principal) "
                "e estabeleça a faixa de sanidade de preço de forma realista com base nos custos e revendas.\n\n"
                f"{context_str}"
            )

            structured_llm = chat_model.with_structured_output(CanonicalDossierOutput)
            result: CanonicalDossierOutput = structured_llm.invoke(prompt)
            
            dossier_dict = result.model_dump()
            return {"dossier": dossier_dict}

        except Exception as e:
            print(f"⚠️ Erro no nó LLM do DossierBuilder: {e}. Aplicando contingência heurística...")

    # Fallback Heurístico Determinístico
    brand = "EcoFlow" if ("eco" in desc.lower() or "ecoflow" in fornecedor.lower()) else (fornecedor or "Genérica")
    
    # Extrai voltagem via regex
    voltage = ""
    if re.search(r'\b(110|127)v\b', desc, re.I):
        voltage = "127V"
    elif re.search(r'\b220v\b', desc, re.I):
        voltage = "220V"
    elif re.search(r'\bbivolt\b', desc, re.I):
        voltage = "Bivolt"

    # Extrai capacidade/potência via regex
    cap_match = re.search(r'\b(\d+\s*(?:wh|w|mah|gb|tb))\b', desc, re.I)
    cap = cap_match.group(1).upper() if cap_match else ""

    # Extrai EAN de algum anúncio de referência se houver
    gtin = ""
    for r in refs:
        if r.get("gtin"):
            gtin = r["gtin"]
            break

    base_price = revenda if revenda > 0 else (custo * 1.4 if custo > 0 else 1000.0)
    p_min = round(base_price * 0.45, 2)
    p_max = round(base_price * 2.2, 2)

    dossier_dict = {
        "brand": brand,
        "model": desc,
        "canonical_title": desc,
        "gtin_ean": gtin,
        "voltage": voltage,
        "capacity_or_power": cap,
        "specs": {"voltage": voltage, "capacity": cap},
        "negative_terms": ["capa", "bolsa", "cabo", "suporte", "mochila", "painel solar", "case", "conector", "adaptador"],
        "price_sanity_min": p_min,
        "price_sanity_max": p_max,
        "ai_summary": f"Produto {brand} - {desc}. Voltagem: {voltage or 'Não especificada'}. Faixa aceitável: R$ {p_min:.2f} a R$ {p_max:.2f}."
    }

    return {"dossier": dossier_dict}


def create_dossier_builder_graph(chat_model=None):
    """Cria e compila o grafo de construção de dossiê do LangGraph"""
    workflow = StateGraph(DossierBuilderState)

    def synthesize_step(state: DossierBuilderState):
        return synthesize_dossier_node(state, chat_model=chat_model)

    workflow.add_node("synthesize_dossier", synthesize_step)
    workflow.add_edge(START, "synthesize_dossier")
    workflow.add_edge("synthesize_dossier", END)

    return workflow.compile()


def build_and_save_sku_dossier(user_id: str, sku: str, db_manager) -> Dict[str, Any]:
    """
    Executa o grafo de construção do Dossiê Canônico para um SKU e salva no Supabase.
    """
    sku_clean = str(sku or "").strip().upper()
    sku_data = db_manager.get_sku_details(user_id, sku_clean) or {}
    refs = db_manager.get_sku_reference_listings(user_id, sku_clean)

    chat_model, provider, model_name = get_active_user_ai_model(user_id, db_manager)

    initial_state: DossierBuilderState = {
        "user_id": user_id,
        "sku": sku_clean,
        "descricao_pedido": sku_data.get("descricao") or sku_clean,
        "fornecedor": (sku_data.get("pedidos", [{}])[0].get("fornecedor", "") if sku_data.get("pedidos") else "") or "",
        "preco_custo": float(sku_data.get("preco_custo") or 0.0),
        "preco_revenda": float(sku_data.get("preco_revenda") or 0.0),
        "reference_listings": refs,
        "dossier": None
    }

    graph = create_dossier_builder_graph(chat_model=chat_model)
    final_state = graph.invoke(initial_state)

    dossier = final_state.get("dossier") or {}
    if dossier:
        db_manager.save_sku_knowledge(user_id, sku_clean, dossier)

    return dossier
