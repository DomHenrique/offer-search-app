import time
import random
import re
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from fake_useragent import UserAgent

class AmazonDirectScraper:
    def __init__(self):
        self.driver = None
        self.base_url = 'https://www.amazon.com.br/s?k='

    def setup_driver(self) -> Optional[uc.Chrome]:
        try:
            options = uc.ChromeOptions()
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            ua = UserAgent()
            user_agent = ua.random
            options.add_argument(f'--user-agent={user_agent}')
            
            # Start undetected chromedriver
            self.driver = uc.Chrome(options=options, version_main=150) # often specifying version helps or letting it auto-detect
            return self.driver
        except Exception as e:
            print(f"❌ Erro ao configurar undetected_chromedriver: {e}")
            # Try again without version_main if it failed
            try:
                options = uc.ChromeOptions()
                options.add_argument('--headless=new')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                self.driver = uc.Chrome(options=options)
                return self.driver
            except Exception as e2:
                print(f"❌ Erro no fallback do undetected_chromedriver: {e2}")
                return None

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            finally:
                self.driver = None

    def is_captcha(self, page_source: str) -> bool:
        if "Type the characters you see in this image" in page_source:
            return True
        if "Digite os caracteres que você vê na imagem" in page_source:
            return True
        if "api/services/captcha" in page_source:
            return True
        return False

    def scrape_search(self, search_term: str) -> Optional[pd.DataFrame]:
        if not search_term or not search_term.strip():
            print("❌ Termo de pesquisa inválido (Amazon)")
            return None
        
        if not self.setup_driver():
            print("❌ Falha ao inicializar o driver da Amazon")
            return None
            
        try:
            formatted_term = search_term.replace(' ', '+')
            url = f"{self.base_url}{formatted_term}"
            
            print(f"📄 [Amazon Direct] Carregando: {url}")
            self.driver.get(url)
            
            # Wait for content to load or captcha
            time.sleep(random.uniform(2, 4))
            
            page_source = self.driver.page_source
            if self.is_captcha(page_source):
                print("⚠️ CAPTCHA detectado na Amazon. Bloqueio iminente.")
                return pd.DataFrame() # Retorna df vazio para acionar o fallback

            # Scroll a bit
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
            time.sleep(random.uniform(1, 2))
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight*2/3);")
            time.sleep(random.uniform(1, 2))
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(1, 2))
            
            # Use BeautifulSoup for faster parsing
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Pega containers de produto. Geralmente .s-result-item
            product_containers = soup.select('div[data-component-type="s-search-result"]')
            
            print(f"🔍 Encontrados {len(product_containers)} produtos na Amazon.")
            
            if len(product_containers) == 0:
                print("⚠️ Nenhum produto encontrado (possível layout diferente ou bloqueio oculto).")
                return pd.DataFrame()

            all_products = []
            
            for container in product_containers:
                try:
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
                        'ASIN': container.get('data-asin', ''),
                        'SPONSORED': False,
                        'PRIME': False,
                    }
                    
                    # Titulo
                    title_elem = container.select_one('h2 a span') or container.select_one('h2 span')
                    if title_elem:
                        product_data['TITLE'] = title_elem.text.strip()
                    
                    # Preço
                    price_whole = container.select_one('.a-price-whole')
                    price_fraction = container.select_one('.a-price-fraction')
                    if price_whole:
                        whole = price_whole.text.strip().replace('.', '').replace(',', '')
                        frac = price_fraction.text.strip() if price_fraction else "00"
                        price_str = f"{whole}.{frac}"
                        product_data['PRICE_NUMERIC'] = float(price_str)
                        product_data['PRICE'] = f"R$ {price_str.replace('.', ',')}"
                    
                    # Imagem
                    img_elem = container.select_one('.s-image')
                    if img_elem:
                        product_data['IMAGE_URL'] = img_elem.get('src', '')
                        
                    # URL
                    link_elem = container.select_one('h2 a') or container.select_one('a.a-link-normal.s-no-outline') or container.select_one('a.a-link-normal.s-underline-link-text')
                    if link_elem:
                        href = link_elem.get('href', '')
                        if href.startswith('/'):
                            href = f"https://www.amazon.com.br{href}"
                        product_data['PRODUCT_URL'] = href
                    
                    # Avaliação (Rating)
                    rating_elem = container.select_one('i[class*="a-icon-star"] span') or container.select_one('span[aria-label*="estrelas"]')
                    if rating_elem:
                        rating_text = rating_elem.text if not rating_elem.has_attr('aria-label') else rating_elem['aria-label']
                        # "4,5 de 5 estrelas"
                        match = re.search(r'(\d+[.,]\d+)', rating_text)
                        if match:
                            product_data['RATING'] = float(match.group(1).replace(',', '.'))
                            
                    # Numero de Avaliações
                    reviews_elem = container.select_one('a[href*="#customerReviews"] span') or container.select_one('span[aria-label*="avaliações"]')
                    if reviews_elem:
                        rev_text = reviews_elem.text.strip().replace('.', '')
                        match = re.search(r'(\d+)', rev_text)
                        if match:
                            product_data['REVIEWS_COUNT'] = int(match.group(1))
                            
                    # Prime
                    prime_elem = container.select_one('i.a-icon-prime')
                    if prime_elem:
                        product_data['PRIME'] = True
                        
                    # Sponsored
                    sponsored_elem = container.select_one('.s-sponsored-label-info-icon')
                    if sponsored_elem or "Patrocinado" in container.text:
                        product_data['SPONSORED'] = True

                    if product_data['TITLE'] and product_data['PRICE_NUMERIC'] > 0:
                        all_products.append(product_data)
                
                except Exception as e:
                    print(f"❌ Erro ao extrair item da Amazon: {e}")
                    continue
                    
            if not all_products:
                return pd.DataFrame()
                
            df = pd.DataFrame(all_products)
            print(f"🎉 Scraping Amazon concluído! Total: {len(df)} produtos válidos")
            return df
            
        except Exception as e:
            print(f"❌ Erro ao buscar na Amazon com Selenium: {e}")
            return pd.DataFrame()
        finally:
            self.close()

def get_amazon_direct_data(search_term: str) -> Optional[pd.DataFrame]:
    scraper = AmazonDirectScraper()
    return scraper.scrape_search(search_term)
