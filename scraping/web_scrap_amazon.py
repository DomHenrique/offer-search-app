import time
import random
import re
import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from fake_useragent import UserAgent


class AmazonDirectScraper:
    def __init__(self):
        self.driver = None
        self.base_url = 'https://www.amazon.com.br/s?k='

    def setup_driver(self) -> Optional[webdriver.Firefox]:
        """Configura o WebDriver Firefox em modo headless para navegação estável"""
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

            # Inicia Firefox WebDriver
            self.driver = webdriver.Firefox(options=firefox_options)
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            self.driver.set_page_load_timeout(35)
            return self.driver
        except Exception as e:
            print(f"❌ Erro ao configurar Firefox para Amazon: {e}")
            return None

    def close(self):
        """Finaliza a instância do navegador"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None

    def inject_amazon_cookies(self, user_id: Optional[str] = None) -> bool:
        """
        Carrega os cookies salvos no Supabase pela extensão Chrome e injeta no WebDriver
        para navegar autenticado na Amazon Brasil sem bloqueios de WAF/CAPTCHA.
        """
        if not self.driver:
            return False
        try:
            from database.db_manager import DatabaseManager
            db = DatabaseManager()
            session_data = db.get_amazon_session(user_id=user_id)
            if not session_data or not session_data.get('cookies'):
                print("ℹ️ [Amazon] Nenhum cookie de sessão da Amazon encontrado no banco.")
                return False

            cookies = session_data.get('cookies', [])
            print(f"🍪 [Amazon] Injetando {len(cookies)} cookies de sessão no WebDriver Firefox...")

            # É necessário carregar o domínio antes de injetar os cookies
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

            print(f"✅ [Amazon] {injected} cookies da Amazon injetados com sucesso!")
            return True
        except Exception as e:
            print(f"⚠️ [Amazon] Erro ao injetar cookies da Amazon: {e}")
            return False

    def is_captcha(self, page_source: str) -> bool:
        """Verifica se a página retornada é um desafio de CAPTCHA"""
        if not page_source:
            return False
        captcha_signatures = [
            "Type the characters you see in this image",
            "Digite os caracteres que você vê na imagem",
            "api/services/captcha",
            "Robot Check",
            "Desculpe, ocorreu um erro"
        ]
        return any(sig in page_source for sig in captcha_signatures)

    def scrape_search(self, search_term: str, user_id: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Executa a busca de produtos na Amazon com injeção de sessão e parsing avançado.
        """
        if not search_term or not search_term.strip():
            print("❌ Termo de pesquisa inválido (Amazon)")
            return pd.DataFrame()

        if not self.setup_driver():
            print("❌ Falha ao inicializar o driver da Amazon")
            return pd.DataFrame()

        try:
            # 1. Injeta cookies autênticos da sessão do usuário
            self.inject_amazon_cookies(user_id=user_id)

            # 2. Navega para a busca
            formatted_term = search_term.replace(' ', '+')
            url = f"{self.base_url}{formatted_term}"
            print(f"📄 [Amazon Direct] Carregando: {url}")
            self.driver.get(url)

            # Espera inicial para renderização
            time.sleep(random.uniform(1.5, 3.0))

            page_source = self.driver.page_source
            if self.is_captcha(page_source):
                print("⚠️ [Amazon] CAPTCHA detectado na Amazon.")
                return pd.DataFrame()

            # Scroll suave para carregar imagens e itens lazy-loaded
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight*2/3);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            # 3. Parsing com BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Busca containers de resultados de produto
            product_containers = soup.select('div[data-component-type="s-search-result"], div.s-result-item[data-asin]')
            # Filtra containers sem ASIN válido
            valid_containers = [c for c in product_containers if c.get('data-asin') and len(c.get('data-asin').strip()) > 2]

            print(f"🔍 [Amazon] Encontrados {len(valid_containers)} containers de produtos válidos.")

            if not valid_containers:
                print("⚠️ [Amazon] Nenhum produto encontrado nos seletores principais.")
                return pd.DataFrame()

            all_products = []

            for container in valid_containers:
                try:
                    asin = container.get('data-asin', '').strip()
                    
                    product_data = {
                        'TITLE': '',
                        'PRICE': '',
                        'PRICE_NUMERIC': 0.0,
                        'RATING': 0.0,
                        'REVIEWS_COUNT': 0,
                        'IMAGE_URL': '',
                        'PRODUCT_URL': '',
                        'MARKETPLACE': 'Amazon',
                        'SEARCH_TERM': search_term,
                        'SCRAPY_DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'ASIN': asin,
                        'SPONSORED': False,
                        'PRIME': False,
                    }

                    # Título
                    title_elem = (
                        container.select_one('h2 a span') or 
                        container.select_one('h2 span') or 
                        container.select_one('h2 a') or 
                        container.select_one('.a-size-base-plus.a-color-base.a-text-normal') or
                        container.select_one('.a-size-medium.a-color-base.a-text-normal')
                    )
                    if title_elem:
                        product_data['TITLE'] = title_elem.text.strip()

                    # Preço
                    price_offscreen = container.select_one('.a-price .a-offscreen')
                    if price_offscreen and price_offscreen.text:
                        price_text = price_offscreen.text.strip()
                        product_data['PRICE'] = price_text
                        # Extrai numérico
                        numeric_str = re.sub(r'[^\d,.]', '', price_text).replace('.', '').replace(',', '.')
                        try:
                            product_data['PRICE_NUMERIC'] = float(numeric_str)
                        except Exception:
                            product_data['PRICE_NUMERIC'] = 0.0
                    else:
                        # Fallback de preço por fração
                        price_whole = container.select_one('.a-price-whole')
                        price_fraction = container.select_one('.a-price-fraction')
                        if price_whole:
                            whole = price_whole.text.strip().replace('.', '').replace(',', '')
                            frac = price_fraction.text.strip() if price_fraction else "00"
                            price_str = f"{whole}.{frac}"
                            try:
                                product_data['PRICE_NUMERIC'] = float(price_str)
                                product_data['PRICE'] = f"R$ {price_str.replace('.', ',')}"
                            except Exception:
                                pass

                    # Imagem
                    img_elem = container.select_one('.s-image, img.s-image, img[data-image-latency="s-product-image"]')
                    if img_elem:
                        product_data['IMAGE_URL'] = img_elem.get('src', '')

                    # URL do Produto
                    link_elem = (
                        container.select_one('h2 a') or 
                        container.select_one('a.a-link-normal.s-no-outline') or 
                        container.select_one('a.a-link-normal.s-underline-link-text')
                    )
                    if link_elem:
                        href = link_elem.get('href', '')
                        if href.startswith('/'):
                            href = f"https://www.amazon.com.br{href}"
                        # Limpa URLs com parâmetros excessivos
                        if '/dp/' in href:
                            dp_match = re.search(r'(/dp/[A-Z0-9]+)', href)
                            if dp_match:
                                href = f"https://www.amazon.com.br{dp_match.group(1)}"
                        product_data['PRODUCT_URL'] = href

                    # Avaliação (Rating)
                    rating_elem = (
                        container.select_one('i[class*="a-icon-star"] span') or 
                        container.select_one('span[aria-label*="estrelas"]') or
                        container.select_one('i.a-icon-star-small')
                    )
                    if rating_elem:
                        rating_text = rating_elem.text if not rating_elem.has_attr('aria-label') else rating_elem['aria-label']
                        match = re.search(r'(\d+[.,]\d+)', rating_text)
                        if match:
                            product_data['RATING'] = float(match.group(1).replace(',', '.'))

                    # Quantidade de Avaliações
                    reviews_elem = (
                        container.select_one('a[href*="#customerReviews"] span') or 
                        container.select_one('span[aria-label*="avaliações"]') or
                        container.select_one('span.a-size-base.s-underline-text')
                    )
                    if reviews_elem:
                        rev_text = reviews_elem.text.strip().replace('.', '')
                        match = re.search(r'(\d+)', rev_text)
                        if match:
                            product_data['REVIEWS_COUNT'] = int(match.group(1))

                    # Selos Prime e Patrocinado
                    if container.select_one('i.a-icon-prime, .s-prime'):
                        product_data['PRIME'] = True

                    if container.select_one('.s-sponsored-label-info-icon') or "Patrocinado" in container.text:
                        product_data['SPONSORED'] = True

                    # Detecção de Múltiplas Ofertas / Catálogo (All Offers / Outros vendedores)
                    is_catalog = False
                    sellers_count = 1
                    container_text = container.text

                    # 1. Procura por links de offer-listing ou gatilho de ofertas
                    olp_link = container.select_one('a[href*="offer-listing"], a[href*="aod"], a[data-action="show-all-offers-display"]')
                    if olp_link:
                        is_catalog = True
                        olp_text = olp_link.text.strip()
                        match_count = re.search(r'(\d+)\s*(?:outras?\s*ofertas?|opções|vendedores)', olp_text, re.IGNORECASE)
                        if match_count:
                            sellers_count = int(match_count.group(1)) + 1

                    # 2. Procura no texto do card por padrões de múltiplos concorrentes
                    if not is_catalog:
                        multi_match = re.search(r'(?:outras?|mais)\s*(\d+)\s*(?:ofertas?|opções|vendedores)', container_text, re.IGNORECASE)
                        if multi_match:
                            is_catalog = True
                            sellers_count = int(multi_match.group(1)) + 1
                        elif re.search(r'outras\s*opções\s*de\s*compra|outros\s*vendedores', container_text, re.IGNORECASE):
                            is_catalog = True
                            sellers_count = 2

                    # Todo ASIN válido na Amazon é uma página de catálogo indexável
                    product_data['IS_CATALOG'] = is_catalog
                    product_data['SELLERS_COUNT'] = sellers_count
                    product_data['BUYBOX_MIN_PRICE'] = product_data['PRICE_NUMERIC']

                    # Validação de produto válido
                    if product_data['TITLE'] and (product_data['PRICE_NUMERIC'] > 0 or product_data['PRICE']):
                        all_products.append(product_data)

                except Exception as e_item:
                    print(f"❌ [Amazon] Erro ao extrair item: {e_item}")
                    continue

            if not all_products:
                return pd.DataFrame()

            df = pd.DataFrame(all_products)
            print(f"🎉 [Amazon] Scraping concluído! Total: {len(df)} produtos válidos")
            return df

        except Exception as e:
            print(f"❌ [Amazon] Erro ao buscar com Firefox headless: {e}")
            return pd.DataFrame()
        finally:
            self.close()


def get_amazon_direct_data(search_term: str, user_id: Optional[str] = None) -> Optional[pd.DataFrame]:
    """Função utilitária para execução direta da raspagem na Amazon"""
    scraper = AmazonDirectScraper()
    return scraper.scrape_search(search_term, user_id=user_id)
