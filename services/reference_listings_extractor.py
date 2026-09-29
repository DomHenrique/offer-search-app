"""
services/reference_listings_extractor.py
Extrator de atributos e metadados de anúncios para Mercado Livre, Amazon,
lojas próprias e sites externos de fornecedores.
Suporta os papéis de anúncio: own_store, supplier e competitor.
"""

import json
import re
import requests
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup


def extract_reference_listing(
    url_or_id: str,
    marketplace_hint: Optional[str] = None,
    user_id: Optional[str] = None,
    role: str = "supplier"
) -> Dict[str, Any]:
    """
    Identifica o marketplace, extrai os metadados do anúncio ativo e retorna um dicionário normalizado:
    {
        'marketplace': 'MercadoLivre' | 'Amazon' | 'Fornecedor' | 'LojaPropria' | 'Concorrente',
        'listing_id': str,
        'listing_url': str,
        'title': str,
        'price': float,
        'image_url': str,
        'pictures': List[str],
        'gtin': str,
        'brand': str,
        'model': str,
        'seller': str,
        'raw_attributes': dict,
        'status': 'active',
        'listing_role': 'own_store' | 'supplier' | 'competitor',
        'is_own_store': bool
    }
    """
    raw_input = str(url_or_id or "").strip()
    if not raw_input:
        raise ValueError("URL ou ID do anúncio não informado.")

    clean_role = str(role or "supplier").strip().lower()
    if clean_role not in ["own_store", "supplier", "competitor"]:
        clean_role = "supplier"

    listing_data: Dict[str, Any] = {}

    # 1. Detecta se é Mercado Livre
    if "mercadolivre.com" in raw_input.lower() or re.match(r'^(MLB|MLA)\d+$', raw_input, re.IGNORECASE):
        listing_data = _extract_meli_listing(raw_input, user_id=user_id)

    # 2. Detecta se é Amazon
    elif "amazon.com" in raw_input.lower() or re.match(r'^[B0-9][A-Z0-9]{9}$', raw_input):
        listing_data = _extract_amazon_listing(raw_input)

    # 3. Loja Própria / Link Externo de Fornecedor / Outro E-commerce
    else:
        listing_data = _extract_generic_web_listing(raw_input, role=clean_role)

    # Injeta os metadados de papel e garantia de campos essenciais
    listing_data["listing_role"] = clean_role
    listing_data["is_own_store"] = (clean_role == "own_store")
    
    # Se for papel específico, ajusta o marketplace legível caso genérico
    if listing_data.get("marketplace") in ["LojaPropria", "Externo", "Fornecedor", "Concorrente"]:
        if clean_role == "supplier":
            listing_data["marketplace"] = "Fornecedor"
        elif clean_role == "own_store":
            listing_data["marketplace"] = "LojaPropria"
        elif clean_role == "competitor":
            listing_data["marketplace"] = "Concorrente"

    return listing_data
def _extract_attributes_from_text(title: str, description: str = "") -> Dict[str, Any]:
    """Extrai atributos técnicos (marca, modelo, voltagem, potência/capacidade, EAN) a partir de texto"""
    text = f"{title} {description}".strip()
    attrs: Dict[str, Any] = {}

    # 1. Marca
    brand = ""
    brands_known = [
        "EcoFlow", "Ecoflow", "DJI", "Dji", "Bluetti", "Anker", "Jackery",
        "Apple", "Samsung", "Xiaomi", "Motorola", "LG", "Sony", "Dell",
        "Lenovo", "Asus", "Acer", "HP", "JBL", "Intelbras"
    ]
    for b in brands_known:
        if re.search(rf'\b{re.escape(b)}\b', text, re.IGNORECASE):
            brand = "EcoFlow" if b.lower() == "ecoflow" else ("DJI" if b.lower() == "dji" else b)
            break
    if not brand and title:
        first_word = title.split()[0]
        if len(first_word) > 2 and first_word.lower() not in [
            "estação", "estacao", "gerador", "bateria", "painel", "cabo", "fonte", "anúncio", "anuncio"
        ]:
            brand = first_word

    if brand:
        attrs["Marca"] = brand
        attrs["BRAND"] = brand

    # 2. Voltagem
    v_match = re.search(r'\b(110\s*V|127\s*V|220\s*V|Bivolt)\b', text, re.IGNORECASE)
    if v_match:
        raw_v = v_match.group(1).upper().replace(" ", "")
        voltage = "127V" if raw_v in ["110V", "127V"] else ("220V" if raw_v == "220V" else "Bivolt")
        attrs["Voltagem"] = voltage
        attrs["VOLTAGE"] = voltage

    # 3. Capacidade / Potência
    power_matches = re.findall(r'\b(\d+(?:\.\d+)?\s*(?:Wh|W|VA|mAh|Ah|kWh|kW))\b', text, re.IGNORECASE)
    if power_matches:
        cap_power = " ".join(power_matches[:2]).strip()
        attrs["Capacidade/Potência"] = cap_power
        attrs["CAPACITY"] = cap_power

    # 4. Modelo
    model_match = re.search(r'\b(River\s*(?:3\s*Plus|3|2\s*Pro|2\s*Max|2|Pro|Max|Plus|\w+)*|Delta\s*(?:2\s*Max|2\s*Pro|2|Pro|Max|\w+)*)\b', text, re.IGNORECASE)
    if model_match:
        attrs["Modelo"] = model_match.group(1).strip()
        attrs["MODEL"] = model_match.group(1).strip()

    # 5. GTIN / EAN
    ean_match = re.search(r'\b(?:EAN|GTIN|código de barras|barcode)[:\s]*(\d{12,14})\b', text, re.IGNORECASE)
    if not ean_match:
        ean_match = re.search(r'\b(789\d{10}|489\d{10})\b', text)
    if ean_match:
        attrs["GTIN"] = ean_match.group(1)
        attrs["EAN"] = ean_match.group(1)

    return attrs


def _scrape_meli_fallback(item_id: str, raw_input: str, is_catalog: bool) -> Optional[Dict[str, Any]]:
    """Fallback via Selenium headless para obter título real, imagem, preço e atributos quando a API der 401/403"""
    try:
        from scraping.web_scrap_catalog_ml import CatalogScraper
        scraper = CatalogScraper()
        driver = scraper.setup_driver()
        if not driver:
            return None

        try:
            if raw_input.startswith("http"):
                target_url = raw_input
            elif is_catalog or (item_id.startswith("MLB") and len(item_id) <= 12 and not item_id.isdigit()):
                target_url = f"https://www.mercadolivre.com.br/p/{item_id}/s?"
            else:
                target_url = f"https://produto.mercadolivre.com.br/{item_id}"

            print(f"🌐 [Scanner Extractor] Acessando {target_url} via Selenium headless...")
            driver.get(target_url)

            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            try:
                WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except Exception:
                pass

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # 1. Título
            h1 = soup.find('h1')
            og_t = soup.find('meta', property='og:title')
            tw_t = soup.find('meta', property='twitter:title')
            title = ""
            if h1 and h1.get_text(strip=True):
                title = h1.get_text(strip=True)
            elif og_t and og_t.get('content'):
                title = og_t['content'].strip()
            elif tw_t and tw_t.get('content'):
                title = tw_t['content'].strip()
            else:
                title = driver.title

            title = re.sub(r'\s*\|\s*Mercado\s*Livre.*$', '', title, flags=re.IGNORECASE).strip()
            title = re.sub(r'\s*-\s*Mercado\s*Livre.*$', '', title, flags=re.IGNORECASE).strip()

            if not title or title.lower() in ["mercado livre", "mercadolivre", "acesso negado"]:
                return None

            # 2. Imagem
            og_i = soup.find('meta', property='og:image')
            tw_i = soup.find('meta', property='twitter:image')
            image_url = ""
            if og_i and og_i.get('content'):
                image_url = og_i['content'].strip()
            elif tw_i and tw_i.get('content'):
                image_url = tw_i['content'].strip()

            # 3. Descrição
            og_d = soup.find('meta', property='og:description')
            description = og_d['content'].strip() if og_d and og_d.get('content') else ''

            # 4. Preço e Vendedor
            price = 0.0
            seller_name = "Mercado Livre"

            if is_catalog or '/p/' in target_url:
                try:
                    sellers_res = scraper.scrape_catalog_sellers(item_id)
                    sellers_list = sellers_res.get('sellers', []) if isinstance(sellers_res, dict) else []
                    if sellers_list:
                        best = sellers_list[0]
                        price = float(best.get('preco') or 0.0)
                        seller_name = best.get('seller_name') or "Mercado Livre Catálogo"
                except Exception as e_sellers:
                    print(f"Aviso ao buscar sellers do catálogo no fallback: {e_sellers}")

            if price <= 0.0:
                price_elem = soup.select_one('.ui-pdp-price__second-line .andes-money-amount__fraction, .andes-money-amount__fraction')
                if price_elem:
                    raw_val = price_elem.get_text(strip=True).replace('.', '').replace(',', '.')
                    try:
                        price = float(raw_val)
                    except Exception:
                        pass

            # 5. Atributos da Ficha Técnica
            attrs = _extract_attributes_from_text(title, description)
            for tr in soup.select('table tr, .ui-vpp-striped-specs__table tr, .ui-pdp-specs__table tr'):
                th = tr.select_one('th')
                td = tr.select_one('td')
                if th and td:
                    k = th.get_text(strip=True)
                    v = td.get_text(strip=True)
                    if k and v:
                        attrs[k] = v

            brand = attrs.get("Marca") or attrs.get("BRAND") or ""
            model = attrs.get("Modelo") or attrs.get("MODEL") or ""
            gtin = attrs.get("GTIN") or attrs.get("EAN") or ""

            return {
                "marketplace": "MercadoLivre",
                "listing_id": item_id,
                "listing_url": target_url,
                "title": title,
                "price": price,
                "image_url": image_url,
                "pictures": [image_url] if image_url else [],
                "gtin": str(gtin or "").strip(),
                "brand": str(brand or "").strip(),
                "model": str(model or "").strip(),
                "seller": seller_name,
                "raw_attributes": attrs,
                "status": "active"
            }
        finally:
            scraper.close_driver()
    except Exception as e:
        print(f"⚠️ [Scanner Extractor] Erro no fallback de scraping ML: {e}")
        return None


def _extract_meli_listing(raw_input: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Extrai anúncio ou produto de catálogo do Mercado Livre via API oficial ou pública, com fallback em scraping"""
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

    # 1. Tenta consultar como produto de catálogo se for /p/MLB...
    if is_catalog or (item_id.startswith("MLB") and len(item_id) <= 12 and not item_id.isdigit()):
        try:
            from services.meli.catalog import MeliCatalogService
            cat_svc = MeliCatalogService()
            cat_data = cat_svc.get_product_detail(item_id, user_id=user_id)
            if cat_data and cat_data.get("name") and not cat_data.get("name").startswith("Catálogo MLB"):
                attrs = cat_data.get("attributes") or {}
                brand = attrs.get("Marca") or attrs.get("BRAND") or ""
                model = attrs.get("Modelo") or attrs.get("MODEL") or ""
                gtin = cat_data.get("gtin") or attrs.get("GTIN") or attrs.get("EAN") or ""

                return {
                    "marketplace": "MercadoLivre",
                    "listing_id": item_id,
                    "listing_url": cat_data.get("permalink") or f"https://www.mercadolivre.com.br/p/{item_id}",
                    "title": cat_data.get("name") or cat_data.get("title") or f"Catálogo {item_id}",
                    "price": float(cat_data.get("price") or 0.0),
                    "image_url": cat_data.get("image_url") or "",
                    "pictures": [cat_data.get("image_url")] if cat_data.get("image_url") else [],
                    "gtin": str(gtin or "").strip(),
                    "brand": str(brand or "").strip(),
                    "model": str(model or "").strip(),
                    "seller": cat_data.get("seller") or "Mercado Livre Catálogo",
                    "raw_attributes": attrs,
                    "status": cat_data.get("status") or "active"
                }
        except Exception as e:
            print(f"Aviso ao consultar catálogo ML via API: {e}")

    # 2. Consulta como anúncio regular via API pública de items do Mercado Livre
    try:
        url = f"https://api.mercadolibre.com/items/{item_id}"
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if resp.status_code == 200:
            data = resp.json()
            if data.get("title"):
                attributes = {}
                gtin = ""
                brand = ""
                model = ""

                for attr in data.get("attributes", []):
                    aid = attr.get("name") or attr.get("id")
                    val = attr.get("value_name")
                    if aid and val:
                        attributes[aid] = val
                    attr_id_upper = (attr.get("id") or "").upper()
                    if attr_id_upper in ["GTIN", "EAN", "BARCODE"] and val:
                        gtin = val
                    elif attr_id_upper == "BRAND" and val:
                        brand = val
                    elif attr_id_upper == "MODEL" and val:
                        model = val

                pictures = [p.get("secure_url") or p.get("url") for p in data.get("pictures", []) if p.get("secure_url") or p.get("url")]
                image_url = pictures[0] if pictures else (data.get("thumbnail") or "")

                seller_id = str(data.get("seller_id") or "")
                seller_name = f"Vendedor #{seller_id}" if seller_id else "Vendedor ML"

                return {
                    "marketplace": "MercadoLivre",
                    "listing_id": item_id,
                    "listing_url": data.get("permalink") or f"https://produto.mercadolivre.com.br/{item_id}",
                    "title": data.get("title") or "",
                    "price": float(data.get("price") or 0.0),
                    "image_url": image_url,
                    "pictures": pictures,
                    "gtin": str(gtin or "").strip(),
                    "brand": str(brand or "").strip(),
                    "model": str(model or "").strip(),
                    "seller": seller_name,
                    "raw_attributes": attributes,
                    "status": data.get("status") or "active"
                }
    except Exception as e:
        print(f"Aviso ao buscar item na API pública do ML: {e}")

    # 3. Fallback inteligente via Selenium Scraping para capturar dados reais
    scraped_data = _scrape_meli_fallback(item_id, raw_input, is_catalog)
    if scraped_data:
        return scraped_data

    # 4. Fallback final caso não haja conexão com a web
    return {
        "marketplace": "MercadoLivre",
        "listing_id": item_id,
        "listing_url": raw_input if raw_input.startswith("http") else f"https://produto.mercadolivre.com.br/{item_id}",
        "title": f"Anúncio Mercado Livre {item_id}",
        "price": 0.0,
        "image_url": "",
        "pictures": [],
        "gtin": "",
        "brand": "",
        "model": "",
        "seller": "Mercado Livre",
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

    title = f"Produto Amazon {asin}"
    price = 0.0
    image_url = ""

    # Tenta obter título e imagem via OpenGraph se for uma URL completa
    if raw_input.startswith("http"):
        try:
            resp = requests.get(url, timeout=5, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                og_t = soup.find("meta", property="og:title")
                if og_t and og_t.get("content"):
                    title = og_t["content"].strip()
                og_i = soup.find("meta", property="og:image")
                if og_i and og_i.get("content"):
                    image_url = og_i["content"].strip()
        except Exception:
            pass

    return {
        "marketplace": "Amazon",
        "listing_id": asin,
        "listing_url": url,
        "title": title,
        "price": price,
        "image_url": image_url,
        "pictures": [image_url] if image_url else [],
        "gtin": "",
        "brand": "",
        "model": "",
        "seller": "Amazon",
        "raw_attributes": {"ASIN": asin},
        "status": "active"
    }


def _extract_generic_web_listing(url: str, role: str = "supplier") -> Dict[str, Any]:
    """Extrai OpenGraph, schema.org JSON-LD e tabelas técnicas de sites de fornecedores ou lojas"""
    default_market = "Fornecedor" if role == "supplier" else ("LojaPropria" if role == "own_store" else "Concorrente")

    try:
        resp = requests.get(url, timeout=9, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')

            title = ""
            image_url = ""
            price = 0.0
            gtin = ""
            brand = ""
            model = ""
            attributes: Dict[str, str] = {}

            # 1. Tenta extrair dados estruturados JSON-LD (schema.org/Product)
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "{}")
                    # Pode ser um único item ou um graph
                    items = data if isinstance(data, list) else [data]
                    if "@graph" in data and isinstance(data["@graph"], list):
                        items.extend(data["@graph"])

                    for item in items:
                        if isinstance(item, dict) and item.get("@type") in ["Product", "IndividualProduct"]:
                            title = title or item.get("name") or ""
                            gtin = gtin or item.get("gtin13") or item.get("gtin") or item.get("gtin8") or item.get("ean") or ""
                            
                            b_val = item.get("brand")
                            if isinstance(b_val, dict):
                                brand = brand or b_val.get("name") or ""
                            elif isinstance(b_val, str):
                                brand = brand or b_val

                            model = model or item.get("model") or item.get("mpn") or ""
                            
                            # Imagens
                            img = item.get("image")
                            if isinstance(img, list) and img:
                                image_url = image_url or (img[0] if isinstance(img[0], str) else img[0].get("url", ""))
                            elif isinstance(img, str):
                                image_url = image_url or img
                            elif isinstance(img, dict):
                                image_url = image_url or img.get("url", "")

                            # Ofertas e Preço
                            offers = item.get("offers")
                            if isinstance(offers, dict):
                                try:
                                    price = price or float(offers.get("price") or 0.0)
                                except:
                                    pass
                            elif isinstance(offers, list) and offers:
                                try:
                                    price = price or float(offers[0].get("price") or 0.0)
                                except:
                                    pass
                except Exception:
                    continue

            # 2. OpenGraph e Meta tags para complementar
            if not title:
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    title = og_title["content"].strip()
                elif soup.title:
                    title = soup.title.string.strip()

            if not image_url:
                og_img = soup.find("meta", property="og:image")
                if og_img and og_img.get("content"):
                    image_url = og_img["content"].strip()

            if price <= 0:
                for price_meta in ["product:price:amount", "og:price:amount", "twitter:data1"]:
                    meta = soup.find("meta", property=price_meta) or soup.find("meta", attrs={"name": price_meta})
                    if meta and meta.get("content"):
                        try:
                            clean_p = re.sub(r'[^\d,\.]', '', meta["content"]).replace(',', '.')
                            price = float(clean_p)
                            break
                        except:
                            pass

            # 3. Extrai atributos de tabelas de especificações comuns
            for row in soup.find_all("tr"):
                cols = row.find_all(["th", "td"])
                if len(cols) == 2:
                    k = cols[0].get_text(strip=True)
                    v = cols[1].get_text(strip=True)
                    if k and v and len(k) < 60 and len(v) < 200:
                        attributes[k] = v
                        k_upper = k.upper()
                        if not gtin and any(x in k_upper for x in ["EAN", "GTIN", "CÓDIGO DE BARRAS"]):
                            gtin = v
                        if not brand and any(x in k_upper for x in ["MARCA", "FABRICANTE"]):
                            brand = v
                        if not model and any(x in k_upper for x in ["MODELO", "MODEL"]):
                            model = v

            pictures = [image_url] if image_url else []

            # Gera um listing_id determinístico baseado no domínio e path
            listing_id = re.sub(r'[^a-zA-Z0-9]', '', url)[-14:].upper()

            return {
                "marketplace": default_market,
                "listing_id": listing_id,
                "listing_url": url,
                "title": title or f"Produto {default_market}",
                "price": price,
                "image_url": image_url,
                "pictures": pictures,
                "gtin": str(gtin or "").strip(),
                "brand": str(brand or "").strip(),
                "model": str(model or "").strip(),
                "seller": default_market,
                "raw_attributes": attributes,
                "status": "active"
            }
    except Exception as e:
        print(f"Aviso ao extrair metadados web genéricos: {e}")

    return {
        "marketplace": default_market,
        "listing_id": "",
        "listing_url": url,
        "title": f"Produto {default_market}",
        "price": 0.0,
        "image_url": "",
        "pictures": [],
        "gtin": "",
        "brand": "",
        "model": "",
        "seller": default_market,
        "raw_attributes": {},
        "status": "active"
    }
