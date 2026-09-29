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
EXCLUDED_BRAND_WORDS = {
    "mercado", "libre", "livre", "loja", "produto", "anúncio", "anuncio",
    "estação", "estacao", "gerador", "bateria", "painel", "cabo", "fonte",
    "kit", "combo", "novo", "original", "promoção", "promocao", "super",
    "mini", "mega", "ultra", "pro", "plus", "max", "alta", "potente",
    "sistema", "aparelho", "modulo", "módulo", "conversor", "inversor",
    "delta", "river"
}

def _is_blocked_text(text: str) -> bool:
    """Verifica se o texto do título ou página indica página de bloqueio ou desafio"""
    if not text:
        return True
    t = text.strip().lower()
    blocked_phrases = [
        "mercado libre", "mercado livre", "mercadolivre", "acesso negado",
        "segurança — mercado livre", "seguranca — mercado livre", "segurança",
        "atenção", "por segurança", "complete esta etapa", "não sou um robô",
        "nao sou um robo", "robot", "this page requires javascript",
        "account-verification", "403 forbidden", "page not found", "erro 404"
    ]
    for bp in blocked_phrases:
        if bp in t:
            return True
    return False

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

    # Se ainda não achou marca, verifica se é linha EcoFlow conhecida (Delta ou River)
    if not brand and re.search(r'\b(River|Delta)\b', text, re.IGNORECASE):
        brand = "EcoFlow"

    if not brand and title:
        first_word = title.split()[0].strip()
        if len(first_word) > 2 and first_word.lower() not in EXCLUDED_BRAND_WORDS:
            brand = first_word

    if brand and brand.lower() not in EXCLUDED_BRAND_WORDS:
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
    model_match = re.search(
        r'\b(River\s*(?:3\s*Plus|3\s*Max|3|2\s*Pro|2\s*Max|2|Pro|Max|Plus|\w+)*|'
        r'Delta\s*(?:3\s*Plus|3\s*Max|3|2\s*Max|2\s*Pro|2|Pro|Max|Plus|\w+)*)\b',
        text, re.IGNORECASE
    )
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


def _scrape_meli_fallback(
    item_id: str,
    raw_input: str,
    is_catalog: bool,
    user_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Fallback via Selenium headless com suporte a JSON-LD, sanitização de URL e fallback em slug"""
    try:
        from scraping.web_scrap_catalog_ml import CatalogScraper
        import json
        import time

        # Sanitiza a URL de entrada removendo fragmentos (#...) e query params (?...)
        clean_url = raw_input.split("#")[0].split("?")[0].strip()

        # Extrai previamente título e atributos baseados no slug da URL como fallback infalível
        slug_title = ""
        slug_attrs: Dict[str, Any] = {}
        match_slug = re.search(r'/(MLB-?\d+)-([a-zA-Z0-9-]+)(?:_JM)?', clean_url, re.IGNORECASE)
        if match_slug:
            slug_words = match_slug.group(2).replace('-', ' ').strip()
            slug_title = " ".join([w.capitalize() if len(w) > 2 else w.upper() for w in slug_words.split()])
            slug_attrs = _extract_attributes_from_text(slug_title, "")

        if clean_url.startswith("http"):
            target_url = clean_url
        elif is_catalog or (item_id.startswith("MLB") and len(item_id) <= 12 and not item_id.isdigit()):
            target_url = f"https://www.mercadolivre.com.br/p/{item_id}/s?"
        else:
            target_url = f"https://produto.mercadolivre.com.br/{item_id}"

        scraper = CatalogScraper()
        driver = scraper.setup_driver()
        if not driver:
            # Se não conseguiu iniciar o driver mas tem slug, retorna os dados do slug
            if slug_title:
                brand = slug_attrs.get("Marca") or slug_attrs.get("BRAND") or ""
                model = slug_attrs.get("Modelo") or slug_attrs.get("MODEL") or ""
                return {
                    "marketplace": "MercadoLivre",
                    "listing_id": item_id,
                    "listing_url": target_url,
                    "title": slug_title,
                    "price": 0.0,
                    "image_url": "",
                    "pictures": [],
                    "gtin": str(slug_attrs.get("GTIN") or "").strip(),
                    "brand": str(brand or "").strip(),
                    "model": str(model or "").strip(),
                    "seller": "Mercado Livre",
                    "raw_attributes": slug_attrs,
                    "status": "active"
                }
            return None

        try:
            print(f"🌐 [Scanner Extractor] Acessando {target_url} via Selenium headless...")
            driver.get(target_url)
            time.sleep(2)

            curr_url = (driver.current_url or "").lower()
            curr_title = (driver.title or "").strip().lower()

            # Se caiu em tela de verificação ou segurança, tenta injetar cookies salvos
            if "captcha/wall" in curr_url or "account-verification" in curr_url or _is_blocked_text(curr_title):
                if user_id:
                    print("⚠️ Desafio de segurança detectado. Tentando injetar cookies de sessão...")
                    if scraper.inject_ml_cookies(user_id=user_id):
                        driver.get(target_url)
                        time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # 1. Busca dados estruturados Schema.org JSON-LD (Product)
            json_ld_product: Dict[str, Any] = {}
            for script in soup.find_all('script', type='application/ld+json'):
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('@type') == 'Product':
                        json_ld_product = data
                        break
                except Exception:
                    pass

            # 2. Título
            title = ""
            if json_ld_product.get("name"):
                title = str(json_ld_product["name"]).strip()

            if not title or _is_blocked_text(title):
                h1 = soup.find('h1')
                og_t = soup.find('meta', property='og:title')
                tw_t = soup.find('meta', property='twitter:title')
                if h1 and h1.get_text(strip=True) and not _is_blocked_text(h1.get_text(strip=True)):
                    title = h1.get_text(strip=True)
                elif og_t and og_t.get('content') and not _is_blocked_text(og_t['content']):
                    title = og_t['content'].strip()
                elif tw_t and tw_t.get('content') and not _is_blocked_text(tw_t['content']):
                    title = tw_t['content'].strip()
                elif driver.title and not _is_blocked_text(driver.title):
                    title = driver.title.strip()

            # Limpeza de ruídos no título
            title = re.sub(r'^\s*\(\d+\+?\)\s*', '', title).strip()
            title = re.sub(r'\s*\|\s*Mercado\s*Livre.*$', '', title, flags=re.IGNORECASE).strip()
            title = re.sub(r'\s*-\s*Mercado\s*Livre.*$', '', title, flags=re.IGNORECASE).strip()
            title = re.sub(r'\s*\|\s*Frete\s*gr[aá]tis.*$', '', title, flags=re.IGNORECASE).strip()
            title = re.sub(r'\s*\|\s*Parcelamento\s*sem\s*juros.*$', '', title, flags=re.IGNORECASE).strip()

            if not title or _is_blocked_text(title):
                if slug_title:
                    title = slug_title
                else:
                    return None

            # 3. Imagem
            image_url = ""
            if json_ld_product.get("image"):
                img_val = json_ld_product["image"]
                if isinstance(img_val, list) and img_val:
                    image_url = str(img_val[0]).strip()
                elif isinstance(img_val, str):
                    image_url = img_val.strip()

            if not image_url:
                og_i = soup.find('meta', property='og:image')
                tw_i = soup.find('meta', property='twitter:image')
                if og_i and og_i.get('content'):
                    image_url = og_i['content'].strip()
                elif tw_i and tw_i.get('content'):
                    image_url = tw_i['content'].strip()
                else:
                    img_el = soup.select_one('.ui-pdp-gallery__figure img, .ui-pdp-image')
                    if img_el and img_el.get('src'):
                        image_url = img_el['src'].strip()

            # 4. Descrição
            og_d = soup.find('meta', property='og:description')
            description = og_d['content'].strip() if og_d and og_d.get('content') else ''

            # 5. Preço e Vendedor
            price = 0.0
            seller_name = "Mercado Livre"

            if json_ld_product.get("offers"):
                offers = json_ld_product["offers"]
                if isinstance(offers, dict) and offers.get("price") is not None:
                    try:
                        price = float(offers["price"])
                    except Exception:
                        pass
                elif isinstance(offers, list) and len(offers) > 0 and offers[0].get("price") is not None:
                    try:
                        price = float(offers[0]["price"])
                    except Exception:
                        pass

            if is_catalog or '/p/' in target_url:
                try:
                    sellers_res = scraper.scrape_catalog_sellers(item_id, user_id=user_id)
                    sellers_list = sellers_res.get('sellers', []) if isinstance(sellers_res, dict) else []
                    if sellers_list:
                        best = sellers_list[0]
                        price = float(best.get('preco') or 0.0)
                        seller_name = best.get('seller_name') or "Mercado Livre Catálogo"
                except Exception as e_sellers:
                    print(f"Aviso ao buscar sellers do catálogo no fallback: {e_sellers}")

            if price <= 0.0:
                price_elem = soup.select_one(
                    '.ui-pdp-price__second-line .andes-money-amount__fraction, '
                    '.poly-price__current .andes-money-amount__fraction, '
                    '.andes-money-amount__fraction'
                )
                if price_elem:
                    raw_val = price_elem.get_text(strip=True).replace('.', '').replace(',', '.')
                    try:
                        cents_elem = soup.select_one(
                            '.ui-pdp-price__second-line .andes-money-amount__cents, '
                            '.poly-price__current .andes-money-amount__cents, '
                            '.andes-money-amount__cents'
                        )
                        cents_val = 0.0
                        if cents_elem and cents_elem.get_text(strip=True).isdigit():
                            cents_val = float(cents_elem.get_text(strip=True)) / 100.0
                        price = float(raw_val) + cents_val
                    except Exception:
                        pass

            # Extração refinada de vendedor da página
            seller_elem = soup.select_one(
                '.ui-seller-data-header__title, '
                '.ui-pdp-seller-summary__link, '
                '.ui-pdp-seller-summary__link-trigger-button, '
                '.ui-pdp-seller__link-trigger'
            )
            if seller_elem and seller_elem.get_text(strip=True):
                seller_text = seller_elem.get_text(strip=True)
                if seller_text.lower() not in ["mercado livre", "loja oficial do mercado livre"]:
                    seller_name = seller_text

            # 6. Atributos da Ficha Técnica
            attrs = _extract_attributes_from_text(title, description)
            if slug_attrs:
                for k, v in slug_attrs.items():
                    if k not in attrs or not attrs[k]:
                        attrs[k] = v

            if json_ld_product.get("brand"):
                b_val = json_ld_product["brand"]
                if isinstance(b_val, dict) and b_val.get("name"):
                    attrs["Marca"] = str(b_val["name"]).strip()
                    attrs["BRAND"] = str(b_val["name"]).strip()
                elif isinstance(b_val, str) and b_val.strip():
                    attrs["Marca"] = b_val.strip()
                    attrs["BRAND"] = b_val.strip()

            for tr in soup.select('table tr, .ui-vpp-striped-specs__table tr, .ui-pdp-specs__table tr'):
                th = tr.select_one('th')
                td = tr.select_one('td')
                if th and td:
                    k = th.get_text(strip=True)
                    v = td.get_text(strip=True)
                    if k and v:
                        attrs[k] = v

            brand = attrs.get("Marca") or attrs.get("BRAND") or ""
            if str(brand).strip().lower() in EXCLUDED_BRAND_WORDS:
                brand = ""
                attrs.pop("Marca", None)
                attrs.pop("BRAND", None)

            model = attrs.get("Modelo") or attrs.get("MODEL") or ""
            gtin = attrs.get("GTIN") or attrs.get("EAN") or json_ld_product.get("gtin13") or json_ld_product.get("gtin") or ""

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
    scraped_data = _scrape_meli_fallback(item_id, raw_input, is_catalog, user_id=user_id)
    if scraped_data:
        return scraped_data

    # 4. Fallback final caso não haja conexão com a web (utiliza slug da URL se existir)
    clean_url = raw_input.split("#")[0].split("?")[0].strip()
    match_slug = re.search(r'/(MLB-?\d+)-([a-zA-Z0-9-]+)(?:_JM)?', clean_url, re.IGNORECASE)
    fallback_title = f"Anúncio Mercado Livre {item_id}"
    fallback_attrs: Dict[str, Any] = {}
    if match_slug:
        slug_words = match_slug.group(2).replace('-', ' ').strip()
        fallback_title = " ".join([w.capitalize() if len(w) > 2 else w.upper() for w in slug_words.split()])
        fallback_attrs = _extract_attributes_from_text(fallback_title, "")

    fallback_brand = fallback_attrs.get("Marca") or fallback_attrs.get("BRAND") or ""
    fallback_model = fallback_attrs.get("Modelo") or fallback_attrs.get("MODEL") or ""

    return {
        "marketplace": "MercadoLivre",
        "listing_id": item_id,
        "listing_url": clean_url if clean_url.startswith("http") else f"https://produto.mercadolivre.com.br/{item_id}",
        "title": fallback_title,
        "price": 0.0,
        "image_url": "",
        "pictures": [],
        "gtin": str(fallback_attrs.get("GTIN") or "").strip(),
        "brand": str(fallback_brand or "").strip(),
        "model": str(fallback_model or "").strip(),
        "seller": "Mercado Livre",
        "raw_attributes": fallback_attrs,
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
