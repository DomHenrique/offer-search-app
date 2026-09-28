"""
services/listing_auditor.py
Motor de diagnóstico e auditoria de saúde para anúncios da Loja Própria.
Identifica ausência de EAN, atributos técnicos faltantes, divergência de preços
e calcula score de completude para otimização de vendas.
"""

import re
from typing import Dict, Any, List, Optional
from database.db_manager import DatabaseManager


RECOMMENDED_TECHNICAL_ATTRIBUTES = [
    {"key": "BRAND", "aliases": ["Marca", "brand", "Fabricante"], "label": "Marca"},
    {"key": "MODEL", "aliases": ["Modelo", "model", "Linha"], "label": "Modelo"},
    {"key": "VOLTAGE", "aliases": ["Voltagem", "Tensão", "voltage"], "label": "Voltagem / Tensão"},
    {"key": "CAPACITY", "aliases": ["Capacidade", "Potência", "capacity", "power"], "label": "Capacidade / Potência"},
    {"key": "COLOR", "aliases": ["Cor", "color"], "label": "Cor"},
    {"key": "WARRANTY", "aliases": ["Garantia", "warranty", "Tempo de garantia"], "label": "Garantia"},
    {"key": "DIMENSIONS", "aliases": ["Dimensões", "dimensoes", "Tamanho", "Peso"], "label": "Dimensões / Peso"}
]


class ListingAuditor:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def audit_own_store_listing(
        self,
        user_id: str,
        extracted_data: Dict[str, Any],
        matched_sku_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executa auditoria completa de saúde para o anúncio próprio:
        - Validação de GTIN/EAN
        - Verificação de Ficha Técnica e atributos essenciais
        - Alinhamento de Preço de Venda vs Custo/Revenda no estoque
        - Mapeamento de atributos que podem ser importados do fornecedor
        """
        issues: List[Dict[str, Any]] = []
        missing_attributes: List[str] = []
        fillable_from_supplier: Dict[str, Any] = {}

        raw_attrs = extracted_data.get("raw_attributes") or {}
        gtin = str(extracted_data.get("gtin") or "").strip()
        price = float(extracted_data.get("price") or 0.0)

        # 1. Auditoria de EAN / GTIN
        digits_gtin = re.sub(r'\D', '', gtin)
        if not digits_gtin or len(digits_gtin) not in [8, 12, 13, 14]:
            issues.append({
                "type": "MISSING_EAN",
                "severity": "HIGH",
                "badge": "🔴 Crítico",
                "title": "Código de Barras EAN / GTIN Ausente",
                "description": "O anúncio não possui código EAN/GTIN válido cadastrado.",
                "impact": "O Mercado Livre reduz a exposição orgânica e bloqueia a exibição nas campanhas do Google Shopping e Catálogo."
            })
            missing_attributes.append("EAN / Código de Barras")

        # 2. Auditoria de Ficha Técnica e Atributos Recomendados
        for req in RECOMMENDED_TECHNICAL_ATTRIBUTES:
            found = False
            for alias in req["aliases"]:
                if alias in raw_attrs and str(raw_attrs[alias]).strip():
                    found = True
                    break
            if not found:
                missing_attributes.append(req["label"])

        if missing_attributes:
            issues.append({
                "type": "INCOMPLETE_SPECS",
                "severity": "MEDIUM",
                "badge": "⚠️ Alerta",
                "title": f"Ficha Técnica Incompleta ({len(missing_attributes)} campos não preenchidos)",
                "description": f"Atributos faltantes: {', '.join(missing_attributes)}.",
                "impact": "Compradores utilizam filtros de atributos para buscar produtos. Anúncios incompletos perdem conversão."
            })

        # 3. Auditoria de Preço vs Estoque
        sku_code = ""
        cost_price = 0.0
        planned_resale_price = 0.0

        if matched_sku_data:
            sku_code = str(matched_sku_data.get("sku") or "").strip().upper()
            cost_price = float(matched_sku_data.get("preco_custo") or 0.0)
            planned_resale_price = float(matched_sku_data.get("preco_revenda") or 0.0)

            if price > 0 and cost_price > 0 and price < cost_price:
                issues.append({
                    "type": "SELLING_BELOW_COST",
                    "severity": "CRITICAL",
                    "badge": "🚨 Prejuízo Imediato",
                    "title": "Preço de Venda Abaixo do Custo de Estoque!",
                    "description": f"Preço no anúncio (R$ {price:.2f}) é menor que o custo de aquisição (R$ {cost_price:.2f}).",
                    "impact": f"Prejuízo bruto direto de R$ {cost_price - price:.2f} por cada unidade vendida!"
                })
            elif price > 0 and planned_resale_price > 0 and abs(price - planned_resale_price) >= 5.0:
                issues.append({
                    "type": "PRICE_DIVERGENCE",
                    "severity": "LOW",
                    "badge": "ℹ️ Divergência",
                    "title": "Divergência entre Preço do Anúncio e Preço Planejado",
                    "description": f"Anúncio está por R$ {price:.2f}, enquanto o preço planejado no inventário é R$ {planned_resale_price:.2f}.",
                    "impact": f"Diferença de R$ {price - planned_resale_price:+.2f} frente ao valor cadastrado no ERP/estoque."
                })

        # 4. Checagem de dados disponíveis no fornecedor para Preenchimento Rápido
        if sku_code:
            supplier_refs = self._get_supplier_attributes_for_sku(user_id, sku_code)
            if supplier_refs:
                for attr_name in missing_attributes:
                    if attr_name == "EAN / Código de Barras" and supplier_refs.get("gtin"):
                        fillable_from_supplier["EAN"] = supplier_refs["gtin"]
                    for k, v in (supplier_refs.get("raw_attributes") or {}).items():
                        if any(req["label"] == attr_name and k in req["aliases"] for req in RECOMMENDED_TECHNICAL_ATTRIBUTES):
                            fillable_from_supplier[attr_name] = v

        # Cálculo do Score de Completude (0 a 100)
        total_checks = 1 + len(RECOMMENDED_TECHNICAL_ATTRIBUTES)
        passed_checks = total_checks - len(missing_attributes)
        completeness_score = max(20, int((passed_checks / total_checks) * 100))
        if any(i["severity"] == "CRITICAL" for i in issues):
            completeness_score = min(completeness_score, 45)

        return {
            "is_own_store": True,
            "completeness_score": completeness_score,
            "status_label": "Excelente" if completeness_score >= 85 else ("Atenção Necessária" if completeness_score >= 60 else "Crítico"),
            "status_color": "#10b981" if completeness_score >= 85 else ("#f59e0b" if completeness_score >= 60 else "#ef4444"),
            "issues": issues,
            "missing_attributes": missing_attributes,
            "fillable_from_supplier": fillable_from_supplier,
            "can_quick_fill": bool(fillable_from_supplier)
        }

    def _get_supplier_attributes_for_sku(self, user_id: str, sku: str) -> Dict[str, Any]:
        """Busca atributos cadastrados de fornecedor para o SKU"""
        try:
            user_uuid = self.db._get_user_uuid(user_id)
            refs = (self.db.supabase.table("sku_reference_listings")
                    .select("*")
                    .eq("user_id", user_uuid)
                    .eq("sku", str(sku).strip().upper())
                    .eq("is_own_store", False)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute())
            if refs.data:
                return refs.data[0]
        except Exception:
            pass
        return {}
