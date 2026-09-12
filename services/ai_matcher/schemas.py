"""
services/ai_matcher/schemas.py
Esquemas Pydantic e tipos de estado do LangGraph para auditoria de ofertas e síntese de dossiê.
"""

from typing import List, Dict, Any, Optional, TypedDict
from pydantic import BaseModel, Field


class CanonicalDossierOutput(BaseModel):
    """Esquema de saída estruturada para o Dossiê Canônico de Verdade do SKU"""
    brand: str = Field(description="Marca oficial do produto (ex: EcoFlow, Apple, DJI)")
    model: str = Field(description="Modelo exato e linha comercial (ex: River 3 Plus, iPhone 15 Pro)")
    canonical_title: str = Field(description="Título comercial limpo e padronizado do produto")
    gtin_ean: Optional[str] = Field(default="", description="Código de barras EAN/GTIN oficial se identificado")
    voltage: Optional[str] = Field(default="", description="Voltagem do SKU (ex: 110V, 127V, 220V, Bivolt)")
    capacity_or_power: Optional[str] = Field(default="", description="Capacidade central, potência ou armazenamento (ex: 286Wh, 600W, 256GB)")
    specs: Dict[str, Any] = Field(default_factory=dict, description="Dicionário com atributos técnicos consolidados")
    negative_terms: List[str] = Field(
        default_factory=lambda: ["capa", "bolsa", "cabo", "suporte", "mochila", "painel solar", "case", "conector"],
        description="Palavras-chave que caracterizam acessórios ou partes avulsas incompatíveis com o produto principal"
    )
    price_sanity_min: float = Field(description="Preço mínimo abaixo do qual uma oferta certamente é acessório ou golpe")
    price_sanity_max: float = Field(description="Preço máximo acima do qual uma oferta é provavelmente um combo/kit inflado")
    ai_summary: str = Field(description="Resumo claro em 1 ou 2 parágrafos em português explicando o que caracteriza este produto")


class MatchAuditResult(BaseModel):
    """Esquema de saída da auditoria de correspondência entre uma oferta e o SKU"""
    score: int = Field(ge=0, le=100, description="Score percentual de certeza de 0 a 100")
    verdict: str = Field(
        description="Classificação: EXACT_MATCH (mesmo produto exato), VARIATION_MISMATCH (mesmo produto, variação diferente ex: voltagem), ACCESSORY_WARNING (é acessório/peça avulsa), WRONG_PRODUCT (produto totalmente diferente)"
    )
    badge_label: str = Field(description="Rótulo curto para o badge na UI (ex: 'Match 96%', 'Variação 220V', 'Acessório 15%')")
    badge_color: str = Field(description="Cor Bootstrap do badge: 'success' (verde), 'warning' (amarelo), 'danger' (vermelho) ou 'secondary'")
    explanation: str = Field(description="Orientação clara e direta do agente em português para o operador do sistema")
    specs_breakdown: Dict[str, Any] = Field(
        default_factory=dict,
        description="Confronto ponto a ponto de marca, modelo, voltagem, preço e integridade de unidade"
    )
    is_safe_to_autolink: bool = Field(description="True se o operador pode confiar plenamente no vínculo sem riscos")


class OfferAuditState(TypedDict):
    """Estado do grafo de auditoria de oferta no LangGraph"""
    user_id: str
    sku: str
    dossier: Dict[str, Any]
    candidate: Dict[str, Any]
    heuristic_passed: bool
    heuristic_reason: str
    audit_result: Optional[Dict[str, Any]]


class DossierBuilderState(TypedDict):
    """Estado do grafo de construção do dossiê no LangGraph"""
    user_id: str
    sku: str
    descricao_pedido: str
    fornecedor: str
    preco_custo: float
    preco_revenda: float
    reference_listings: List[Dict[str, Any]]
    dossier: Optional[Dict[str, Any]]
