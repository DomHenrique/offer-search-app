# scraping/web_scrap_amazon_catalog.py
"""
Módulo de Scraping de Catálogos e Concorrentes da Amazon Brasil (All Offers Drawer).
Responsável por:
  - Navegar até o ASIN (/dp/{ASIN}) com injeção de cookies de sessão da Amazon.
  - Acionar a gaveta lateral flutuante (#all-offers-display / #aod-offer-list).
  - Extrair todos os vendedores concorrentes disputando a BuyBox.
  - Extrair dados do produto principal (Título, Imagem, BuyBox Winner, Preço Mínimo).
"""

import time
import random
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options as FirefoxOptions

from database.db_manager import DatabaseManager


class AmazonCatalogScraper:
    """
    Scraper de concorrentes da Amazon (gaveta lateral All Offers / ASIN).
    """

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.driver: Optional[webdriver.Firefox] = None
        self.db = DatabaseManager()
        self.base_dp_url = "https://www.amazon.com.br/dp/{asin}"

    def setup_driver(self) -> Optional[webdriver.Firefox]:
        """Configura o WebDriver Firefox em modo headless."""
        try:
            firefox_options = FirefoxOptions()
            firefox_options.add_argument("--headless")
            firefox_options.add_argument("--no-sandbox")
            firefox_options.add_argument("--disable-dev-shm-usage")
            firefox_options.add_argument("--disable-gpu")
            firefox_options.add_argument("--window-size=1920,1080")
            firefox_options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) "
                "Gecko/20100101 Firefox/120.0"
            )

            self.driver = webdriver.Firefox(options=firefox_options)
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            self.driver.set_page_load_timeout(35)
            return self.driver
        except Exception as e:
            print(f"❌ [Amazon Catalog] Erro ao configurar Firefox driver: {e}")
            return None

    def close_driver(self):
        """Fecha o navegador com segurança."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None

    def inject_amazon_cookies(self) -> bool:
        """Injeta cookies de autenticação da Amazon salvos no Supabase."""
        if not self.driver:
            return False
        try:
            session_data = self.db.get_amazon_session(user_id=self.user_id)
            if not session_data or not session_data.get('cookies'):
                print("ℹ️ [Amazon Catalog] Nenhum cookie de sessão encontrado no banco.")
                return False

            cookies = session_data.get('cookies', [])
            print(f"🍪 [Amazon Catalog] Injetando {len(cookies)} cookies de sessão...")

            self.driver.get("https://www.amazon.com.br/robots.txt")
            time.sleep(1)

            injected = 0
            for c in cookies:
                try:
                    cookie_dict = {
                        'name': c['name'],
                        'value': c['value'],
                        'path': c.get('path', '/'),
                    }
                    domain = c.get('domain', '')
                    if domain:
                        cookie_dict['domain'] = domain.lstrip('.')
                    if c.get('secure'):
                        cookie_dict['secure'] = True
                    if c.get('httpOnly'):
                        cookie_dict['httpOnly'] = True

                    self.driver.add_cookie(cookie_dict)
                    injected += 1
                except Exception:
                    pass

            print(f"✅ [Amazon Catalog] {injected} cookies da Amazon injetados com sucesso!")
            return True
        except Exception as e:
            print(f"⚠️ [Amazon Catalog] Erro ao injetar cookies: {e}")
            return False

    def scrape_catalog_sellers(self, asin: str) -> Dict:
        """
        Navega até o produto pelo ASIN, abre a gaveta All Offers e extrai todos os concorrentes.

        Returns:
            Dict com:
              - catalog_id: str (ASIN)
              - catalog_title: str
              - catalog_image: str
              - catalog_url: str
              - buybox_winner: str
              - buybox_min_price: float
              - sellers_count: int
              - sellers: List[Dict]
        """
        asin = str(asin).strip().upper()
        if not re.match(r'^[A-Z0-9]{10}$', asin):
            print(f"❌ [Amazon Catalog] ASIN inválido: {asin}")
            return {"catalog_id": asin, "sellers": [], "sellers_count": 0}

        if not self.setup_driver():
            return {"catalog_id": asin, "sellers": [], "sellers_count": 0}

        try:
            self.inject_amazon_cookies()

            dp_url = self.base_dp_url.format(asin=asin)
            print(f"📄 [Amazon Catalog] Carregando produto: {dp_url}")
            self.driver.get(dp_url)
            time.sleep(random.uniform(2.0, 3.5))

            # Verifica CAPTCHA
            if "Digite os caracteres que você vê abaixo" in self.driver.page_source or "validateCaptcha" in self.driver.page_source:
                print("⚠️ [Amazon Catalog] Detecção de CAPTCHA ao acessar página do produto.")
                return {"catalog_id": asin, "sellers": [], "sellers_count": 0, "error": "CAPTCHA detectado"}

            soup_page = BeautifulSoup(self.driver.page_source, 'html.parser')

            # 1. Metadados do Produto Principal
            title_elem = soup_page.select_one('#productTitle, h1#title span')
            title = title_elem.text.strip() if title_elem else f"Produto Amazon {asin}"

            img_elem = soup_page.select_one('#landingImage, #imgBlkFront, #main-image, img[data-a-image-name="landingImage"]')
            image_url = img_elem.get('src') or img_elem.get('data-old-hires') if img_elem else ""

            # Vencedor da BuyBox Principal
            buybox_seller_elem = (
                soup_page.select_one('#tabular-buybox .tabular-buybox-container a[id*="sellerProfile"]') or
                soup_page.select_one('#merchant-info a span, #merchant-info a') or
                soup_page.select_one('#sellerProfileTriggerId')
            )
            buybox_seller = buybox_seller_elem.text.strip() if buybox_seller_elem else "Amazon Brasil"

            # Preço da BuyBox Principal
            price_elem = soup_page.select_one('#corePrice_feature_div .a-offscreen, #apex_desktop .a-price .a-offscreen')
            buybox_price = 0.0
            if price_elem and price_elem.text:
                price_clean = re.sub(r'[^\d,.]', '', price_elem.text).replace('.', '').replace(',', '.')
                try:
                    buybox_price = float(price_clean)
                except Exception:
                    pass

            # 2. Acionar a Gaveta Lateral (#all-offers-display / #olpLinkWidget_feature_div)
            print("🔍 [Amazon Catalog] Procurando gatilho de All Offers / Outros vendedores...")
            drawer_opened = False

            triggers = [
                '#olpLinkWidget_feature_div a',
                'a#fod-ingress-link',
                'span[data-action="show-all-offers-display"] a',
                'span[data-action="show-all-offers-display"]',
                '.daodl-content a',
                'a[href*="offer-listing"]',
                '#all-offers-display'
            ]

            for sel in triggers:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in elems:
                        if el.is_displayed():
                            print(f"👉 [Amazon Catalog] Clicando no gatilho de ofertas: '{sel}'")
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                            time.sleep(0.5)
                            el.click()
                            drawer_opened = True
                            break
                    if drawer_opened:
                        break
                except Exception:
                    continue

            # Aguarda a gaveta carregar
            if drawer_opened:
                try:
                    WebDriverWait(self.driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#all-offers-display, #aod-offer-list, .aod-offer"))
                    )
                    time.sleep(1.5)
                except Exception:
                    print("⚠️ [Amazon Catalog] Timeout aguardando renderização do drawer All Offers.")

            # 3. Parse dos Concorrentes na Gaveta Lateral
            soup_drawer = BeautifulSoup(self.driver.page_source, 'html.parser')
            raw_offers = soup_drawer.select('#aod-offer-list .aod-offer, #all-offers-display .aod-offer, #aod-pinned-offer')

            sellers = []
            seen_sellers = set()

            for idx, offer in enumerate(raw_offers):
                try:
                    # Seller Name
                    seller_elem = (
                        offer.select_one('#aod-offer-soldBy a') or
                        offer.select_one('#aod-offer-soldBy span') or
                        offer.select_one('a#sellerProfileTriggerId') or
                        offer.select_one('.aod-offer-soldBy')
                    )
                    s_name = seller_elem.text.strip() if seller_elem else ""
                    if not s_name or "amazon" in s_name.lower():
                        s_name = "Amazon Brasil"

                    # Preço
                    price_elem_offer = (
                        offer.select_one('.apexPriceToPay .a-offscreen') or
                        offer.select_one('.a-price .a-offscreen') or
                        offer.select_one('.a-price-whole')
                    )
                    price_str = price_elem_offer.text.strip() if price_elem_offer else ""
                    price_num = 0.0
                    if price_str:
                        p_clean = re.sub(r'[^\d,.]', '', price_str).replace('.', '').replace(',', '.')
                        try:
                            price_num = float(p_clean)
                        except Exception:
                            pass

                    if price_num == 0.0:
                        continue

                    # Enviado por (Ships From) & Prime/FBA
                    ships_elem = offer.select_one('#aod-offer-shipsFrom span, .aod-offer-shipsFrom')
                    ships_from = ships_elem.text.strip() if ships_elem else ""
                    is_fba_prime = "amazon" in ships_from.lower() or bool(offer.select_one('i.a-icon-prime, .aod-prime-badge'))

                    # Frete / Prazo
                    delivery_elem = offer.select_one('div[id*="delivery-promise"], .aod-delivery-promise, #aod-delivery-promise-1')
                    delivery_text = delivery_elem.text.strip() if delivery_elem else "Consulte entrega"
                    frete_gratis = "grátis" in delivery_text.lower() or "frete grátis" in delivery_text.lower() or is_fba_prime

                    # Condição (Novo vs Usado)
                    condition_elem = offer.select_one('#aod-offer-heading, .aod-offer-heading')
                    condition_text = condition_elem.text.strip().lower() if condition_elem else "novo"
                    condicao = "usado" if any(u in condition_text for u in ['usado', 'reembalado', 'seminovo', 'used']) else "novo"

                    # Reputação
                    rep_elem = offer.select_one('#aod-offer-seller-rating, .aod-offer-seller-rating, span[id*="seller-rating"]')
                    reputacao = rep_elem.text.strip() if rep_elem else ""

                    seller_key = f"{s_name}_{price_num}"
                    if seller_key in seen_sellers:
                        continue
                    seen_sellers.add(seller_key)

                    sellers.append({
                        "catalog_id": asin,
                        "seller_name": s_name,
                        "seller_id_ml": f"AMZ_{re.sub(r'[^A-Za-z0-9]', '', s_name)[:15].upper()}",
                        "preco": price_num,
                        "preco_str": f"R$ {price_num:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
                        "frete_gratis": frete_gratis,
                        "frete_full": is_fba_prime,
                        "reputacao": reputacao,
                        "condicao": condicao,
                        "is_best_offer": (idx == 0 or offer.get('id') == 'aod-pinned-offer'),
                        "posicao": idx + 1,
                        "prazo_entrega": delivery_text[:80]
                    })
                except Exception as ex_item:
                    print(f"⚠️ [Amazon Catalog] Erro ao parsear oferta individual: {ex_item}")

            # Se a gaveta não continha ofertas separadas (item único de buybox), adiciona a oferta principal
            if not sellers and buybox_price > 0:
                sellers.append({
                    "catalog_id": asin,
                    "seller_name": buybox_seller,
                    "seller_id_ml": f"AMZ_{re.sub(r'[^A-Za-z0-9]', '', buybox_seller)[:15].upper()}",
                    "preco": buybox_price,
                    "preco_str": f"R$ {buybox_price:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
                    "frete_gratis": True,
                    "frete_full": True,
                    "reputacao": "Vendedor Principal",
                    "condicao": "novo",
                    "is_best_offer": True,
                    "posicao": 1,
                    "prazo_entrega": "Entrega Prime"
                })

            min_price = min([s["preco"] for s in sellers]) if sellers else buybox_price
            winner_name = sellers[0]["seller_name"] if sellers else buybox_seller

            print(f"🎉 [Amazon Catalog] Coleta concluída para ASIN {asin}: {len(sellers)} sellers encontrados!")

            catalog_payload = {
                "catalog_id": asin,
                "catalog_title": title,
                "catalog_image": image_url,
                "catalog_url": dp_url,
                "buybox_winner": winner_name,
                "buybox_min_price": min_price,
                "sellers_count": max(len(sellers), 1),
                "marketplace": "Amazon",
                "sellers": sellers
            }

            # Salva catálogo e sellers no Supabase
            self._save_scraped_data(catalog_payload)

            return catalog_payload

        except Exception as e:
            print(f"❌ [Amazon Catalog] Erro fatal durante scraping de {asin}: {e}")
            return {"catalog_id": asin, "sellers": [], "sellers_count": 0, "error": str(e)}
        finally:
            self.close_driver()

    def _save_scraped_data(self, catalog_data: Dict):
        """Persiste os metadados do catálogo e os sellers no banco de dados Supabase."""
        try:
            asin = catalog_data["catalog_id"]

            # 1. Salva o catálogo na tabela catalogos via db.save_catalog
            cat_payload = {
                "catalog_id": asin,
                "nome": catalog_data.get("catalog_title", f"Catálogo Amazon {asin}"),
                "imagem": catalog_data.get("catalog_image", ""),
                "termo_pesquisa": catalog_data.get("termo_pesquisa", ""),
                "user_id": self.user_id or "1"
            }
            self.db.save_catalog(cat_payload)

            # 2. Insere sellers em catalog_sellers
            sellers = catalog_data.get("sellers", [])
            if sellers:
                self.db.save_catalog_sellers(asin, sellers)
                print(f"💾 [Amazon Catalog] {len(sellers)} sellers do ASIN {asin} salvos no banco.")
        except Exception as e:
            print(f"❌ [Amazon Catalog] Erro ao salvar dados no Supabase: {e}")


def get_amazon_catalog_sellers(asin: str, user_id: Optional[str] = None) -> Dict:
    """Função utilitária para acionar o scraper de catálogo da Amazon."""
    scraper = AmazonCatalogScraper(user_id=user_id)
    return scraper.scrape_catalog_sellers(asin)
