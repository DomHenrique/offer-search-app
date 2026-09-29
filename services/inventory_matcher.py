"""
services/inventory_matcher.py
Motor de matching e comparação inteligente de dados extraídos de produtos
contra o inventário consolidado de SKUs do usuário.
"""

import re
import unicodedata
from typing import List, Dict, Any, Optional
from database.db_manager import DatabaseManager


STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "ou", "com", "sem", "para", "em", "no", "na",
    "nos", "nas", "a", "o", "as", "os", "um", "uma", "uns", "umas", "kit", "original"
}


def _tokenize(text: str) -> set:
    """Extrai palavras limpas sem acentos com mais de 1 caractere, ignorando stopwords"""
    normalized = unicodedata.normalize('NFKD', str(text or "")).encode('ASCII', 'ignore').decode('utf-8').lower()
    raw_tokens = re.findall(r'[a-z0-9]+', normalized)
    return {t for t in raw_tokens if len(t) > 1 and t not in STOPWORDS}


def _clean_barcode(code: str) -> str:
    """Extrai apenas dígitos do código de barras"""
    digits = re.sub(r'\D', '', str(code or ""))
    return digits if len(digits) >= 7 else ""


class InventoryMatcher:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def find_matches_for_listing(self, user_id: str, extracted_data: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Compara os dados extraídos de um anúncio com os SKUs do inventário do usuário,
        retornando uma lista ordenada de candidatos com pontuação e justificativa.
        """
        inventory = self.db.get_consolidated_inventory(user_id)
        if not inventory:
            return []

        extracted_gtin = _clean_barcode(extracted_data.get("gtin"))
        extracted_id = str(extracted_data.get("listing_id") or "").strip().upper()
        extracted_title = str(extracted_data.get("title") or "")
        extracted_brand = str(extracted_data.get("brand") or "").strip().lower()
        extracted_model = str(extracted_data.get("model") or "").strip().lower()

        extracted_tokens = _tokenize(extracted_title)
        if extracted_brand:
            extracted_tokens.add(extracted_brand)
        if extracted_model:
            extracted_tokens.update(_tokenize(extracted_model))

        # Pré-carrega referências existentes do usuário para cruzamento de GTIN histórico
        sku_references_map: Dict[str, List[Dict]] = {}
        try:
            user_uuid = self.db._get_user_uuid(user_id)
            refs_res = (self.db.supabase.table("sku_reference_listings")
                        .select("sku, gtin, listing_id, marketplace")
                        .eq("user_id", user_uuid)
                        .execute())
            for r in (refs_res.data or []):
                s = str(r.get("sku") or "").strip().upper()
                if s not in sku_references_map:
                    sku_references_map[s] = []
                sku_references_map[s].append(r)
        except Exception:
            pass

        candidates = []

        for item in inventory:
            sku = str(item.get("sku") or "").strip().upper()
            descricao = str(item.get("descricao") or "")
            termo_busca = str(item.get("termo_busca") or "")
            catalogs = item.get("catalogs") or []
            item_tokens = _tokenize(f"{sku} {descricao} {termo_busca}")

            score = 0
            match_tier = "NONE"
            match_badge = ""
            reasons = []

            # 1. Checagem de EAN / GTIN Exato (100%)
            item_gtins = set()
            if item.get("ean"):
                item_gtins.add(_clean_barcode(item.get("ean")))
            if item.get("ncm"):
                # Alguns sistemas colocam código complementar
                pass
            for ref in sku_references_map.get(sku, []):
                if ref.get("gtin"):
                    item_gtins.add(_clean_barcode(ref.get("gtin")))

            if extracted_gtin and extracted_gtin in item_gtins:
                score = 100
                match_tier = "EXACT_EAN"
                match_badge = "🔥 Match Exato por Código de Barras (EAN)"
                reasons.append(f"EAN {extracted_gtin} coincide perfeitamente com o cadastro do SKU.")

            # 2. Checagem de Catálogo MLB já Conectado (95%)
            elif extracted_id:
                has_catalog_match = False
                for cat in catalogs:
                    cat_id = str(cat.get("catalog_id") or "").strip().upper()
                    if cat_id and (cat_id == extracted_id or extracted_id in cat_id or cat_id in extracted_id):
                        has_catalog_match = True
                        break

                if not has_catalog_match:
                    for ref in sku_references_map.get(sku, []):
                        if str(ref.get("listing_id") or "").strip().upper() == extracted_id:
                            has_catalog_match = True
                            break

                if has_catalog_match:
                    score = 95
                    match_tier = "CONNECTED_CATALOG"
                    match_badge = f"🔗 Catálogo {extracted_id} já Conectado ao SKU"
                    reasons.append(f"Este identificador ({extracted_id}) já está vinculado ao SKU.")

            # 3. Código SKU Literal Presente no Título (90%)
            if score == 0 and sku:
                # Verifica se o código do SKU (limpo de hífens) está contido no título
                sku_clean = re.sub(r'[^a-zA-Z0-9]', '', sku).lower()
                title_clean = re.sub(r'[^a-zA-Z0-9]', '', extracted_title).lower()
                if len(sku_clean) >= 4 and (sku.lower() in extracted_title.lower() or sku_clean in title_clean):
                    score = 90
                    match_tier = "SKU_IN_TITLE"
                    match_badge = f"🏷️ Código {sku} Encontrado no Título"
                    reasons.append(f"O código do SKU '{sku}' foi identificado diretamente no nome do anúncio.")

            # 4. Similaridade Semântica & Token Overlap (0% a 85%)
            if score == 0:
                common_tokens = extracted_tokens.intersection(item_tokens)
                if common_tokens:
                    base_ratio = len(common_tokens) / max(len(extracted_tokens), 1)
                    calculated_score = int(base_ratio * 70)

                    # Bônus se marca estiver presente
                    if extracted_brand and (extracted_brand in str(descricao).lower() or extracted_brand in str(termo_busca).lower()):
                        calculated_score += 15

                    # Bônus se modelo estiver presente (literal ou núcleo do modelo ex: "delta 3" em "delta 3 plus")
                    if extracted_model:
                        model_norm = extracted_model.lower()
                        model_core = re.sub(r'\b(plus|max|pro|mini|ultra)\b', '', model_norm).strip()
                        desc_lower = str(descricao).lower()
                        term_lower = str(termo_busca).lower()
                        if model_norm in desc_lower or model_norm in term_lower:
                            calculated_score += 20
                        elif len(model_core) >= 4 and (model_core in desc_lower or model_core in term_lower):
                            calculated_score += 15

                    score = min(85, max(15, calculated_score))

                    if score >= 65:
                        match_tier = "HIGH_SIMILARITY"
                        match_badge = "⚡ Alta Afinidade de Modelo e Marca"
                        reasons.append(f"Termos coincidentes: {', '.join(list(common_tokens)[:4])}")
                    elif score >= 35:
                        match_tier = "PARTIAL_SIMILARITY"
                        match_badge = "🔍 Similaridade Parcial de Título"
                        reasons.append(f"Alguns termos em comum: {', '.join(list(common_tokens)[:3])}")
                    else:
                        match_tier = "LOW_SIMILARITY"
                        match_badge = "⚪ Baixa Probabilidade"

            # Busca imagem de catálogo ou referência se existir para enriquecer a UI
            candidate_image = ""
            for cat in catalogs:
                if isinstance(cat, dict) and cat.get("imagem"):
                    candidate_image = cat["imagem"]
                    break
            if not candidate_image:
                for ref in sku_references_map.get(sku, []):
                    if isinstance(ref, dict) and ref.get("image_url"):
                        candidate_image = ref["image_url"]
                        break

            # Formata o candidato
            candidates.append({
                "sku": sku,
                "descricao": descricao,
                "termo_busca": termo_busca,
                "quantidade_total": item.get("quantidade_total", 0),
                "preco_custo": float(item.get("preco_custo") or 0.0),
                "preco_revenda": float(item.get("preco_revenda") or 0.0),
                "image_url": candidate_image,
                "match_score": score,
                "match_tier": match_tier,
                "match_badge": match_badge,
                "reasons": reasons,
                "catalogs_count": len(catalogs)
            })

        # Ordena candidatos por pontuação decrescente
        candidates.sort(key=lambda x: (x["match_score"], x["quantidade_total"]), reverse=True)

        # Filtra os top candidatos com score > 0 (ou retorna até 3 primeiros se todos forem 0 para permitir escolha manual)
        top_candidates = [c for c in candidates if c["match_score"] > 0][:limit]
        if not top_candidates and candidates:
            top_candidates = candidates[:3]

        return top_candidates
