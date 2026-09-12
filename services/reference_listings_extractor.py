"""
services/reference_listings_extractor.py
Extrator de atributos e metadados de anúncios ativos para Mercado Livre, Amazon e Loja Própria.
Utilizado para alimentar a base de conhecimento e o Dossiê Canônico do SKU.
"""

import re
import requests
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup


def extract_reference_listing(url_or_id: str, marketplace_hint: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Identifica o marketplace, extrai os metadados do anúncio ativo e retorna um dicionário normalizado:
    {
        'marketplace': 'MercadoLivre' | 'Amazon' | 'LojaPropria' | 'Manual',
        'listing_id': str,
        'listing_url': str,
        'title': str,
        'price': float,
        'image_url': str,
        'gtin': str,
        'raw_attributes': dict,
        'status': 'active'
    }
    """
    raw_input = str(url_or_id or "").strip()
    if not raw_input:
        raise ValueError("URL ou ID do anúncio não informado.")

    # 1. Detecta se é Mercado Livre
    if "mercadolivre.com" in raw_input.lower() or re.match(r'^(MLB|MLA)\d+$', raw_input, re.IGNORECASE):
        return _extract_meli_listing(raw_input, user_id=user_id)

    # 2. Detecta se é Amazon
    elif "amazon.com" in raw_input.lower() or re.match(r'^[B0-9][A-Z0-9]{9}$', raw_input):
        return _extract_amazon_listing(raw_input)

    # 3. Loja Própria / Link Externo Genérico
    else:
        return _extract_generic_web_listing(raw_input)


def _extract_meli_listing(raw_input: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Extrai anúncio ou produto de catálogo do Mercado Livre via API oficial"""
    # Extrai o ID do item ou catálogo
    match_catalog = re.search(r'/p/(MLB\d+)', raw_input, re.IGNORECASE)
    match_item = re.search(r'(MLB-?\d+)', raw_input, re.IGNORECASE)

    item_id = ""
    is_catalog = False
    if match_catalog:
        item_id = match_catalog.group(1).upper()
        is_catalog = True
    elif match_item:
        item_id = match_item.group(1).replace('-', '').upper()
    else:
        item_id = raw_input.strip().upper()

    # Tenta consultar como produto de catálogo primeiro se for formato catalog
    if is_catalog or item_id.startswith("MLB") and len(item_id) <= 12:
        try:
            from services.meli.catalog import MeliCatalogService
            cat_svc = MeliCatalogService()
            cat_data = cat_svc.get_product_detail(item_id, user_id=user_id)
            if cat_data:
                return {
                    "marketplace": "MercadoLivre",
                    "listing_id": item_id,
                    "listing_url": cat_data.get("permalink") or f"https://www.mercadolivre.com.br/p/{item_id}",
                    "title": cat_data.get("name") or cat_data.get("title") or f"Catálogo {item_id}",
                    "price": float(cat_data.get("price") or 0.0),
                    "image_url": cat_data.get("image_url") or "",
                    "gtin": cat_data.get("gtin") or "",
                    "raw_attributes": cat_data.get("attributes") or {},
                    "status": cat_data.get("status") or "active"
                }
        except Exception:
            pass

    # Consulta como anúncio regular via API pública de items do Mercado Livre
    try:
        url = f"https://api.mercadolibre.com/items/{item_id}"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            attributes = {}
            gtin = ""
            for attr in data.get("attributes", []):
                aid = attr.get("name") or attr.get("id")
                val = attr.get("value_name")
                if aid and val:
                    attributes[aid] = val
                if (attr.get("id") or "").upper() in ["GTIN", "EAN"] and val:
                    gtin = val

            pictures = data.get("pictures", [])
            image_url = pictures[0].get("secure_url") or pictures[0].get("url") if pictures else (data.get("thumbnail") or "")

            return {
                "marketplace": "MercadoLivre",
                "listing_id": item_id,
                "listing_url": data.get("permalink") or f"https://produto.mercadolivre.com.br/{item_id}",
                "title": data.get("title") or "",
                "price": float(data.get("price") or 0.0),
                "image_url": image_url,
                "gtin": gtin,
                "raw_attributes": attributes,
                "status": data.get("status") or "active"
            }
    except Exception as e:
        print(f"Aviso ao buscar item na API pública do ML: {e}")

    # Fallback caso API não responda
    return {
        "marketplace": "MercadoLivre",
        "listing_id": item_id,
        "listing_url": raw_input if raw_input.startswith("http") else f"https://produto.mercadolivre.com.br/{item_id}",
        "title": f"Anúncio Mercado Livre {item_id}",
        "price": 0.0,
        "image_url": "",
        "gtin": "",
        "raw_attributes": {},
        "status": "active"
    }


def _extract_amazon_listing(raw_input: str) -> Dict[str, Any]:
    """Extrai ASIN e metadados de anúncio da Amazon"""
    match_asin = re.search(r'/(?:dp|gp/product)/([B0-9][A-Z0-9]{9})', raw_input)
    if not match_asin:
        match_asin = re.search(r'\b([B0-9][A-Z0-9]{9})\b', raw_input)

    asin = match_asin.group(1).upper() if match_asin else raw_input.strip().upper()
    url = raw_input if raw_input.startswith("http") else f"https://www.amazon.com.br/dp/{asin}"

    return {
        "marketplace": "Amazon",
        "listing_id": asin,
        "listing_url": url,
        "title": f"Produto Amazon {asin}",
        "price": 0.0,
        "image_url": "",
        "gtin": "",
        "raw_attributes": {"ASIN": asin},
        "status": "active"
    }


def _extract_generic_web_listing(url: str) -> Dict[str, Any]:
    """Extrai OpenGraph e metadados HTML de lojas próprias ou fornecedores"""
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            title = ""
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()
            elif soup.title:
                title = soup.title.string.strip()

            image_url = ""
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                image_url = og_img["content"].strip()

            price = 0.0
            og_price = soup.find("meta", property="product:price:amount")
            if og_price and og_price.get("content"):
                try:
                    price = float(og_price["content"].replace(',', '.'))
                except:
                    pass

            return {
                "marketplace": "LojaPropria",
                "listing_id": re.sub(r'[^a-zA-Z0-9]', '', url)[-12:],
                "listing_url": url,
                "title": title or "Produto Loja Própria",
                "price": price,
                "image_url": image_url,
                "gtin": "",
                "raw_attributes": {"Fonte": "OpenGraph"},
                "status": "active"
            }
    except Exception as e:
        print(f"Aviso ao extrair metadados OpenGraph: {e}")

    return {
        "marketplace": "LojaPropria",
        "listing_id": "",
        "listing_url": url,
        "title": "Produto Externo",
        "price": 0.0,
        "image_url": "",
        "gtin": "",
        "raw_attributes": {},
        "status": "active"
    }
