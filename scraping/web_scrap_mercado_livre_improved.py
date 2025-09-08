# Web Scraping Mercado Livre - Versão Melhorada
# Baseado no web_scrap_segplano com integração ao sistema atual
# Suporta busca padrão (ofertas do dia) e busca com termo específico
# Agora com extração de thumbnails das páginas de produto quando necessário
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import random
import re
import os
from typing import List, Dict, Optional, Tuple
import requests
from urllib.parse import quote_plus, urljoin
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    print("Selenium não está instalado. Por favor, instale com: pip install selenium")
    SELENIUM_AVAILABLE = False

class MercadoLivreThumbnailExtractor:
    """Extrai thumbnails de produtos do Mercado Livre"""
    def __init__(self, use_selenium: bool = False):
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        if self.use_selenium:
            self.driver = None

    def clean_url(self, url: str) -> str:
        """Limpa a URL removendo parâmetros desnecessários"""
        clean_url = url.split('#')[0]
        return clean_url

    def get_page_content_requests(self, url: str) -> Optional[str]:
        """Obtém o conteúdo da página usando requests"""
        try:
            # Adiciona delay para melhor carregamento da página
            time.sleep(random.uniform(2, 4))  # 2-4 segundos de delay
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"Erro ao fazer requisição para {url}: {e}")
            return None

    def get_page_content_selenium(self, url: str) -> Optional[str]:
        """Obtém o conteúdo da página usando Selenium para melhor carregamento"""
        if not SELENIUM_AVAILABLE:
            return None
            
        driver = None
        try:
            # Configura o driver
            firefox_options = Options()
            firefox_options.add_argument('--headless')
            firefox_options.add_argument('--no-sandbox')
            firefox_options.add_argument('--disable-dev-shm-usage')
            firefox_options.add_argument('--disable-gpu')
            firefox_options.add_argument('--window-size=1920,1080')
            
            driver = webdriver.Firefox(options=firefox_options)
            
            # Carrega a página
            print(f"🚗 Carregando página com Selenium: {url}")
            driver.get(url)
            
            # Espera o carregamento da página
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Scroll para carregar conteúdo dinâmico
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Espera carregar conteúdo dinâmico
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)  # Espera estabilizar
            
            # Espera carregar as imagens
            time.sleep(3)
            
            page_source = driver.page_source
            print("✅ Página carregada com Selenium")
            return page_source
            
        except Exception as e:
            print(f"❌ Erro ao carregar página com Selenium: {e}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    def extract_thumbnail_from_product_page(self, product_url: str) -> Optional[str]:
        """Extrai thumbnail da página individual do produto - Versão mais robusta"""
        if not product_url:
            return None
        
        clean_url = self.clean_url(product_url)
        
        # Primeiro tenta com Selenium para melhor carregamento
        html_content = self.get_page_content_selenium(clean_url)
        if not html_content:
            # Fallback para requests
            print("🔄 Fallback para requests...")
            html_content = self.get_page_content_requests(clean_url)
        
        if not html_content:
            return None
            
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Estratégia 1: Meta Tag Open Graph (Mais Confiável)
            og_image_elem = soup.find('meta', attrs={'property': 'og:image'})
            if og_image_elem:
                img_url = og_image_elem.get('content')
                if img_url and self.is_valid_image_url(img_url):
                    return urljoin(product_url, img_url)
            
            # Estratégia 2: Meta Tag Twitter
            twitter_image_elem = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter_image_elem:
                img_url = twitter_image_elem.get('content')
                if img_url and self.is_valid_image_url(img_url):
                    return urljoin(product_url, img_url)
            
            # Estratégia 3: Seletores Específicos da Galeria (Baseados no HTML Fornecido)
            # Priorizando o seletor específico fornecido
            gallery_selectors = [
                'span.ui-pdp-gallery__wrapper:nth-child(3) > figure:nth-child(2) > img:nth-child(1)',  # Seletor específico fornecido
                'figure.ui-pdp-gallery__figure img.ui-pdp-image.ui-pdp-gallery__figure__image',
                '.ui-pdp-gallery__figure img.ui-pdp-image',
                '.ui-pdp-gallery__figure img',
                '.ui-pdp-gallery__wrapper img',
                'span.ui-pdp-gallery__wrapper > figure > img',
                'div.ui-pdp-gallery__column span.ui-pdp-gallery__wrapper figure.ui-pdp-gallery__figure img'
            ]
            
            for selector in gallery_selectors:
                elements = soup.select(selector)
                for element in elements:
                    # Tenta múltiplos atributos de src
                    img_url = (
                        element.get('src') or 
                        element.get('data-src') or 
                        element.get('data-lazy-src') or
                        element.get('data-zoom') or
                        element.get('data-large') or
                        element.get('data-original')
                    )
                    
                    if img_url and self.is_valid_image_url(img_url):
                        return urljoin(product_url, img_url)
            
            # Estratégia 4: Seletores Genéricos para Imagens na Página
            generic_selectors = [
                'img.ui-pdp-image[data-testid="ui-pdp-image"]',
                'img.ui-pdp-image:not([data-testid="ui-pdp-gallery-image"])',
                'img.ui-pdp-image',
                '.ui-pdp-container img[src*="http"]',
                '.ui-pdp-main-image',
                'img[src*="mlb"][src*="jpg"]',
                'img[src*="mlstatic"][src*="jpg"]',
                'img[src*="mlb"][src*="png"]',
                'img[src*="mlstatic"][src*="png"]',
                'img[src*="http"]:not([src*="data:"]):not([src*="icon"]):not([src*="logo"])'
            ]
            
            for selector in generic_selectors:
                elements = soup.select(selector)
                for element in elements:
                    # Tenta múltiplos atributos de src
                    img_url = (
                        element.get('src') or 
                        element.get('data-src') or 
                        element.get('data-lazy-src') or
                        element.get('data-zoom') or
                        element.get('data-large') or
                        element.get('data-original')
                    )
                    
                    if img_url and self.is_valid_image_url(img_url):
                        # Verifica se é uma imagem do produto (não é placeholder ou logo)
                        alt_text = (element.get('alt', '') or '').lower()
                        if any(bad_word in alt_text for bad_word in ['logo', 'banner', 'placeholder', 'default']):
                            continue
                            
                        return urljoin(product_url, img_url)
            
            print(f"❌ Nenhuma thumbnail válida encontrada na página do produto")
            return None
            
        except Exception as e:
            print(f"❌ Erro ao parsear página do produto para thumbnail: {e}")
            return None

    def is_valid_image_url(self, url: str) -> bool:
        """Verifica se a URL é de uma imagem válida"""
        if not url or url.startswith('data:'):
            return False
        
        url_lower = url.lower()
        
        # Verifica extensões de imagem
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        if any(ext in url_lower for ext in valid_extensions):
            return True
        
        # Se é do dominio do ML e parece ser imagem
        if 'mlb-s' in url_lower or 'mercadolibre' in url_lower or 'mlstatic' in url_lower:
            return True
        
        return False

    def is_better_image(self, new_url: str, current_url: Optional[str]) -> bool:
        """Determina se a nova imagem é melhor que a atual"""
        if not current_url:
            return True
        # Prefere URLs com indicadores de alta qualidade
        quality_indicators = ['_W', '_Q', 'large', 'big', 'high', '500x500', '800x800']
        new_score = sum(1 for indicator in quality_indicators if indicator in new_url)
        current_score = sum(1 for indicator in quality_indicators if indicator in current_url)
        return new_score > current_score

    def __del__(self):
        """Cleanup do driver"""
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
            except:
                pass

class MercadoLivreScraperImproved:
    def __init__(self):
        """Inicializa o scraper do Mercado Livre"""
        self.driver = None
        self.base_url = 'https://lista.mercadolivre.com.br/'
        self.offers_url = 'https://www.mercadolivre.com.br/ofertas?category=MLB1051'
        # Session para requisições HTTP
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referer': 'https://www.mercadolivre.com.br/',
        })
        # Inicializa extrator de thumbnails
        self.thumbnail_extractor = MercadoLivreThumbnailExtractor(use_selenium=False)

    def setup_driver(self) -> Optional[webdriver.Firefox]:
        """Configura o driver do Firefox em modo headless"""
        if not SELENIUM_AVAILABLE:
            print("❌ Selenium não disponível")
            return None
        try:
            firefox_options = Options()
            # Configurações para rodar em segundo plano
            firefox_options.add_argument("--headless")
            firefox_options.add_argument("--no-sandbox")
            firefox_options.add_argument("--disable-dev-shm-usage")
            firefox_options.add_argument("--disable-gpu")
            firefox_options.add_argument("--window-size=1920,1080")
            # User agent realista
            firefox_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0")
            self.driver = webdriver.Firefox(options=firefox_options)
            # Remove propriedades que identificam automação
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return self.driver
        except Exception as e:
            print(f"❌ Erro ao configurar Firefox driver: {e}")
            return None

    def get_page_with_selenium(self, url: str, wait_time: int = 10) -> Optional[str]:
        """Carrega a página usando Selenium"""
        if not self.driver:
            return None
        try:
            self.driver.get(url)
            # Aguarda a página carregar
            time.sleep(random.uniform(1, 3))
            # Aguarda elementos específicos aparecerem
            try:
                WebDriverWait(self.driver, wait_time).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                pass
            # Scroll para carregar mais conteúdo
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
            return self.driver.page_source
        except Exception as e:
            print(f"❌ Erro ao carregar página {url}: {e}")
            return None

    def get_page_with_requests(self, url: str) -> Optional[str]:
        """Carrega a página usando requests (fallback)"""
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                return response.text
            else:
                print(f"❌ Erro HTTP {response.status_code} para {url}")
                return None
        except Exception as e:
            print(f"❌ Erro ao carregar página com requests {url}: {e}")
            return None

    def extract_image_with_fallback(self, container, product_url: str = "") -> str:
        """Extrai imagem com fallback para página do produto"""
        image_url = ""
        # Primeiro, tenta extrair da página de listagem com seletores mais específicos
        image_selectors = [
            "img.poly-component__picture",
            "div.poly-card__portada img",
            "img[src*='mlstatic']",
            ".ui-search-result__image img",
            "img.ui-search-result-image__element",
            "img.ui-search-result__content img",
            "img"
        ]
        for selector in image_selectors:
            try:
                img_elem = container.select_one(selector)
                if img_elem:
                    img_src = (img_elem.get('src') or 
                             img_elem.get('data-src') or
                             img_elem.get('data-lazy-src'))
                    if (img_src and 'mlstatic' in img_src and 
                        not img_src.startswith('data:') and
                        len(img_src) > 20):
                        image_url = img_src
                        break
            except:
                continue

        # Se não encontrou imagem na listagem e tem URL do produto, tenta extrair da página do produto
        if not image_url and product_url:
            try:
                print(f"🔍 Tentando extrair imagem da página do produto: {product_url[:50]}...")
                thumbnail_url = self.thumbnail_extractor.extract_thumbnail_from_product_page(product_url)
                if thumbnail_url:
                    image_url = thumbnail_url
                    print(f"✅ Imagem extraída da página do produto")
                else:
                    print(f"❌ Não foi possível extrair imagem da página do produto")
            except Exception as e:
                print(f"❌ Erro ao extrair imagem da página do produto: {e}")
        return image_url

    def extract_products_from_offers_page(self, html_content: str) -> List[Dict]:
        """Extrai produtos da página de ofertas do dia"""
        products = []
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            # Procura pelos containers de produtos na página de ofertas
            product_containers = soup.find_all('div', class_=re.compile(r'ui-search-layout__item|poly-card|item'))
            print(f"🔍 Encontrados {len(product_containers)} containers de produtos na página de ofertas")
            for i, container in enumerate(product_containers):
                try:
                    product_data = {
                        'title': '',
                        'price': '',
                        'price_numeric': 0.0,
                        'original_price': '',
                        'original_price_numeric': 0.0,
                        'discount_percent': 0,
                        'rating': 0,
                        'review_count': 0,
                        'image_url': '',
                        'product_url': '',
                        'store_name': '',
                        'brand': ''
                    }
                    # 1. LINK DO PRODUTO (extrair primeiro para usar no fallback da imagem)
                    link_selectors = [
                        "a[href*='produto']", "a[href*='item']", "a[href*='MLB']"
                    ]
                    for selector in link_selectors:
                        try:
                            link_elem = container.select_one(selector)
                            if link_elem:
                                product_url = link_elem.get('href')
                                if product_url and 'mercadolivre' in product_url:
                                    product_data['product_url'] = product_url
                                    break
                        except:
                            continue
                    # 2. TÍTULO
                    title_selectors = [
                        "h3.poly-component__title",
                        "h2.poly-component__title", 
                        "a.poly-component__title",
                        ".ui-search-item__title",
                        "h3", "h2", "a[title]"
                    ]
                    for selector in title_selectors:
                        try:
                            title_elem = container.select_one(selector)
                            if title_elem:
                                title_text = title_elem.get_text(strip=True) or title_elem.get('title', '')
                                if len(title_text) > 10:  # Título válido
                                    product_data['title'] = title_text
                                    break
                        except:
                            continue
                    # 3. PREÇO ATUAL
                    price_selectors = [
                        ".andes-money-amount__fraction",
                        ".price-tag-fraction",
                        ".andes-money-amount",
                        "span[class*='price']",
                        ".ui-search-price__part"
                    ]
                    for selector in price_selectors:
                        try:
                            price_elem = container.select_one(selector)
                            if price_elem:
                                price_text = price_elem.get_text(strip=True)
                                if price_text and re.search(r'\d', price_text):
                                    product_data['price'] = f"R$ {price_text}"
                                    # Extrai valor numérico
                                    numeric_price = re.sub(r'[^\d,.]', '', price_text)
                                    numeric_price = numeric_price.replace('.', '').replace(',', '.')
                                    try:
                                        product_data['price_numeric'] = float(numeric_price)
                                    except:
                                        product_data['price_numeric'] = 0.0
                                    break
                        except:
                            continue
                    # 4. PREÇO ORIGINAL (se houver desconto)
                    original_price_selectors = [
                        ".andes-money-amount__original",
                        ".ui-search-price__original",
                        "span[class*='original']"
                    ]
                    for selector in original_price_selectors:
                        try:
                            orig_elem = container.select_one(selector)
                            if orig_elem:
                                orig_text = orig_elem.get_text(strip=True)
                                if orig_text and re.search(r'\d', orig_text):
                                    product_data['original_price'] = f"R$ {orig_text}"
                                    # Extrai valor numérico
                                    numeric_orig = re.sub(r'[^\d,.]', '', orig_text)
                                    numeric_orig = numeric_orig.replace('.', '').replace(',', '.')
                                    try:
                                        product_data['original_price_numeric'] = float(numeric_orig)
                                        # Calcula desconto
                                        if product_data['original_price_numeric'] > 0 and product_data['price_numeric'] > 0:
                                            discount = ((product_data['original_price_numeric'] - product_data['price_numeric']) / product_data['original_price_numeric']) * 100
                                            product_data['discount_percent'] = round(discount, 2)
                                    except:
                                        pass
                                    break
                        except:
                            continue
                    # 5. IMAGEM (com fallback para página do produto)
                    product_data['image_url'] = self.extract_image_with_fallback(
                        container, product_data['product_url']
                    )
                    # 6. NOME DA LOJA
                    store_selectors = [
                        "span.poly-component__seller",
                        ".ui-search-item__group__element--stores__name",
                        "span.ui-search-item__store-name",
                        "span[class*='seller']",
                        "div[class*='seller'] span",
                        ".ui-search-item__store-name a",
                        "span.ui-search-color--BLACK"
                    ]
                    for selector in store_selectors:
                        try:
                            store_elem = container.select_one(selector)
                            if store_elem:
                                store_text = store_elem.get_text(strip=True)
                                # Filtra textos que parecem ser nome de loja
                                if (store_text and 
                                    len(store_text) > 2 and 
                                    len(store_text) < 100 and
                                    not store_text.lower().startswith(('r', 'por', 'de', 'em', 'até')) and
                                    not store_text.isdigit() and
                                    'vendido por' not in store_text.lower()):
                                    # Remove prefixos comuns
                                    store_text = re.sub(r'^(por\s+|vendido\s+por\s+)', '', store_text, flags=re.IGNORECASE).strip()
                                    if store_text:
                                        product_data['store_name'] = store_text
                                        break
                        except:
                            continue
                    # 7. AVALIAÇÕES (RATING)
                    rating_selectors = [
                        "div.poly-component__reviews",
                        "span[class*='review']", 
                        "div[class*='rating']",
                        ".ui-search-reviews",
                        "span.ui-search-reviews__rating-number"
                    ]
                    for selector in rating_selectors:
                        try:
                            rating_elem = container.select_one(selector)
                            if rating_elem:
                                aria_label = rating_elem.get('aria-label', '')
                                text_content = rating_elem.get_text(strip=True)
                                # Procura por padrões como "4.8 de 5 estrelas" ou "4.5"
                                rating_match = re.search(r'(\d+\.?\d*)\s*(?:de\s*5|estrelas?)?', aria_label + ' ' + text_content, re.IGNORECASE)
                                if rating_match:
                                    rating_str = rating_match.group(1)
                                    rating_float = float(rating_str)
                                    if rating_float > 5:
                                        product_data['rating'] = 5  # Limita a 5 estrelas máximo
                                    else:
                                        product_data['rating'] = round(rating_float)
                                    break
                        except:
                            continue
                    # 8. NÚMERO DE AVALIAÇÕES
                    review_count_selectors = [
                        "span.poly-reviews__count",
                        ".ui-search-reviews__amount",
                        "span[class*='review-count']",
                        "span[class*='reviews']"
                    ]
                    for selector in review_count_selectors:
                        try:
                            review_elem = container.select_one(selector)
                            if review_elem:
                                review_text = review_elem.get_text(strip=True)
                                # Extrai número de avaliações (ex: "(123)" ou "123 avaliações")
                                number_match = re.search(r'(\d+)', review_text)
                                if number_match:
                                    product_data['review_count'] = int(number_match.group(1))
                                    break
                        except:
                            continue
                    # Só adiciona se tem dados mínimos (título e preço)
                    if product_data['title'] and product_data['price']:
                        products.append(product_data)
                        review_info = f"{product_data['rating']}⭐ ({product_data['review_count']} reviews)" if product_data['rating'] > 0 or product_data['review_count'] > 0 else "Sem avaliações"
                        discount_info = f" | {product_data['discount_percent']}% OFF" if product_data['discount_percent'] > 0 else ""
                        img_info = " | 🖼️ Com imagem" if product_data['image_url'] else " | ❌ Sem imagem"
                        print(f"✅ Produto {len(products)}: {product_data['title'][:40]}... | {product_data['store_name'] or 'Loja não identificada'} | {review_info}{discount_info}{img_info}")
                except Exception as e:
                    print(f"❌ Erro ao processar produto {i+1}: {e}")
                    continue
        except Exception as e:
            print(f"❌ Erro ao extrair dados dos produtos: {e}")
        
        # Aplica filtro de smartphone para ofertas do dia (consistência com Amazon)
        if not products:
            print("🎯 Total de produtos extraídos da página de ofertas: 0")
            return products
            
        print(f"🔍 Aplicando filtro de smartphone para {len(products)} produtos...")
        filtered_products = []
        for product in products:
            title = product.get('title', '').lower()
            # Verifica se é um produto de smartphone/celular
            if any(keyword in title for keyword in ['smartphone', 'celular', 'mobile', 'iphone', 'galaxy', 'xiaomi', 'redmi', 'motorola', 'nokia', 'lg', 'sony', 'huawei']):
                filtered_products.append(product)
        
        # Aplica filtro de preço mínimo
        min_price = float(os.getenv("MIN_PRICE_FILTER", 1.0))
        if min_price > 1.0:  # Só aplica se for maior que 1 real
            print(f"💰 Aplicando filtro de preço mínimo: R$ {min_price}")
            price_filtered_products = []
            for product in filtered_products:
                price_numeric = product.get('price_numeric', 0.0)
                if price_numeric >= min_price:
                    price_filtered_products.append(product)
            filtered_products = price_filtered_products
            print(f"💰 Produtos após filtro de preço: {len(filtered_products)}")
        
        print(f"🎯 Total de produtos extraídos da página de ofertas: {len(products)} (filtrados: {len(filtered_products)})")
        return filtered_products

    def extract_products_from_search_page(self, html_content: str) -> List[Dict]:
        """Extrai produtos da página de busca"""
        products = []
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            # Procura pelos containers de produtos na página de busca (múltiplos seletores)
            product_containers = []
            # Tenta diferentes seletores para encontrar produtos
            selectors = [
                'li.ui-search-layout__item',
                'div.ui-search-result',
                'article.ui-search-item',
                'li[class*="ui-search"]',
                'div[class*="ui-search"]'
            ]
            for selector in selectors:
                containers = soup.select(selector)
                if containers:
                    product_containers = containers
                    print(f"🔍 Encontrados {len(product_containers)} containers de produtos na página de busca usando seletor: {selector}")
                    break
            if not product_containers:
                print("❌ Nenhum container de produto encontrado na página de busca")
                return products

            for i, container in enumerate(product_containers):
                try:
                    product_data = {
                        'title': '',
                        'price': '',
                        'price_numeric': 0.0,
                        'original_price': '',
                        'original_price_numeric': 0.0,
                        'discount_percent': 0,
                        'rating': 0,
                        'review_count': 0,
                        'image_url': '',
                        'product_url': '',
                        'store_name': '',
                        'brand': ''
                    }
                    # 1. LINK DO PRODUTO (extrair primeiro para usar no fallback da imagem)
                    link_selectors = [
                        'a.ui-search-link',
                        'a[href*="produto"]',
                        'a[href*="item"]',
                        'a[href*="MLB"]',
                        'a[class*="link"]'
                    ]
                    for selector in link_selectors:
                        link_elem = container.select_one(selector)
                        if link_elem:
                            product_url = link_elem.get('href')
                            if product_url and 'mercadolivre' in product_url:
                                product_data['product_url'] = product_url
                                break
                    # 2. TÍTULO (múltiplos seletores)
                    title_selectors = [
                        '.ui-search-item__title',
                        'h2.ui-search-item__title',
                        '.ui-search-item__title-label',
                        'h2[class*="title"]',
                        'a[class*="title"]'
                    ]
                    for selector in title_selectors:
                        title_elem = container.select_one(selector)
                        if title_elem:
                            product_data['title'] = title_elem.get_text(strip=True)
                            break
                    # 3. PREÇO (múltiplos seletores)
                    price_selectors = [
                        '.andes-money-amount__fraction',
                        '.price-tag-fraction',
                        '.ui-search-price__part',
                        'span[class*="price"]',
                        'div[class*="price"]'
                    ]
                    for selector in price_selectors:
                        price_elem = container.select_one(selector)
                        if price_elem:
                            price_text = price_elem.get_text(strip=True)
                            if price_text:
                                product_data['price'] = f"R$ {price_text}"
                                # Extrai valor numérico
                                numeric_price = re.sub(r'[^\d,.]', '', price_text)
                                numeric_price = numeric_price.replace('.', '').replace(',', '.')
                                try:
                                    product_data['price_numeric'] = float(numeric_price)
                                except:
                                    product_data['price_numeric'] = 0.0
                                break
                    # 4. PREÇO ORIGINAL
                    orig_price_elem = container.select_one('.andes-money-amount__original')
                    if orig_price_elem:
                        orig_text = orig_price_elem.get_text(strip=True)
                        if orig_text:
                            product_data['original_price'] = f"R$ {orig_text}"
                            # Extrai valor numérico
                            numeric_orig = re.sub(r'[^\d,.]', '', orig_text)
                            numeric_orig = numeric_orig.replace('.', '').replace(',', '.')
                            try:
                                product_data['original_price_numeric'] = float(numeric_orig)
                                # Calcula desconto
                                if product_data['original_price_numeric'] > 0 and product_data['price_numeric'] > 0:
                                    discount = ((product_data['original_price_numeric'] - product_data['price_numeric']) / product_data['original_price_numeric']) * 100
                                    product_data['discount_percent'] = round(discount, 2)
                            except:
                                pass
                    # 5. IMAGEM (com fallback para página do produto)
                    # Primeiro tenta extrair da página de busca
                    img_elem = container.select_one('.ui-search-result__image img')
                    if img_elem:
                        img_src = img_elem.get('src') or img_elem.get('data-src')
                        if img_src and 'mlstatic' in img_src:
                            product_data['image_url'] = img_src
                    # Se não encontrou, usa o fallback
                    if not product_data['image_url']:
                        product_data['image_url'] = self.extract_image_with_fallback(
                            container, product_data['product_url']
                        )
                    # 6. NOME DA LOJA (múltiplos seletores)
                    store_selectors = [
                        '.ui-search-item__store-name',
                        '.ui-search-item__subtitle',
                        'span[class*="store"]',
                        'div[class*="store"]'
                    ]
                    for selector in store_selectors:
                        store_elem = container.select_one(selector)
                        if store_elem:
                            store_text = store_elem.get_text(strip=True)
                            if store_text:
                                product_data['store_name'] = store_text
                                break
                    # 7. AVALIAÇÕES
                    rating_elem = container.select_one('.ui-search-reviews__rating-number')
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True)
                        try:
                            product_data['rating'] = float(rating_text)
                        except:
                            pass
                    # Só adiciona se tem dados mínimos (título e preço)
                    if product_data['title'] and product_data['price']:
                        products.append(product_data)
                        review_info = f"{product_data['rating']}⭐" if product_data['rating'] > 0 else "Sem avaliações"
                        discount_info = f" | {product_data['discount_percent']}% OFF" if product_data['discount_percent'] > 0 else ""
                        img_info = " | 🖼️ Com imagem" if product_data['image_url'] else " | ❌ Sem imagem"
                        print(f"✅ Produto {len(products)}: {product_data['title'][:40]}... | {product_data['store_name'] or 'Loja não identificada'} | {review_info}{discount_info}{img_info}")
                except Exception as e:
                    print(f"❌ Erro ao processar produto {i+1}: {e}")
                    continue
        except Exception as e:
            print(f"❌ Erro ao extrair dados dos produtos: {e}")
        print(f"🎯 Total de produtos extraídos da página de busca: {len(products)}")
        return products

    def scrape_offers_page(self, limit: int = 50) -> List[Dict]:
        """Faz scraping da página de ofertas do dia"""
        print(f"🛒 Iniciando scraping da página de ofertas do dia...")
        # Tenta primeiro com Selenium
        if self.setup_driver():
            html_content = self.get_page_with_selenium(self.offers_url)
            if html_content:
                products = self.extract_products_from_offers_page(html_content)
                self.driver.quit()
                return products[:limit]
        # Fallback para requests
        print("🔄 Tentando com requests...")
        html_content = self.get_page_with_requests(self.offers_url)
        if html_content:
            return self.extract_products_from_offers_page(html_content)[:limit]
        print("❌ Falha ao carregar página de ofertas")
        return []

    def scrape_search_page(self, search_term: str, limit: int = 50) -> List[Dict]:
        """Faz scraping da página de busca"""
        print(f"🔍 Iniciando scraping para: '{search_term}'")
        # Formata o termo de pesquisa para URL
        formatted_term = quote_plus(search_term)
        search_url = f"{self.base_url}{formatted_term}"
        # Tenta primeiro com Selenium
        if self.setup_driver():
            html_content = self.get_page_with_selenium(search_url)
            if html_content:
                products = self.extract_products_from_search_page(html_content)
                self.driver.quit()
                return products[:limit]
        # Fallback para requests
        print("🔄 Tentando com requests...")
        html_content = self.get_page_with_requests(search_url)
        if html_content:
            return self.extract_products_from_search_page(html_content)[:limit]
        print("❌ Falha ao carregar página de busca")
        return []

    def to_dataframe(self, products: List[Dict], search_term: str = "") -> pd.DataFrame:
        """Converte lista de produtos para DataFrame"""
        if not products:
            return pd.DataFrame()
        df_data = []
        for product in products:
            df_data.append({
                'TITLE': product.get('title', ''),
                'PRICE': product.get('price', ''),
                'PRICE_NUMERIC': product.get('price_numeric', 0.0),
                'ORIGINAL_PRICE': product.get('original_price', ''),
                'ORIGINAL_PRICE_NUMERIC': product.get('original_price_numeric', 0.0),
                'DISCOUNT_PERCENT': product.get('discount_percent', 0),
                'RATING': product.get('rating', 0),
                'REVIEWS': product.get('review_count', 0),
                'IMAGE_URL': product.get('image_url', ''),
                'PRODUCT_URL': product.get('product_url', ''),
                'STORE_NAME': product.get('store_name', ''),
                'BRAND': product.get('brand', ''),
                'SEARCH_TERM': search_term or 'ofertas_do_dia',
                'SCRAPY_DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'MARKETPLACE': 'MercadoLivre'
            })
        return pd.DataFrame(df_data)

    def save_to_csv(self, df: pd.DataFrame, search_term: str = "mercado_livre") -> str:
        """Salva DataFrame em arquivo CSV"""
        if df.empty:
            return ""
        os.makedirs('scraped_data', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        search_clean = re.sub(r'[^\w\-_]', '_', search_term)[:30]
        filename = f"ml_improved_{search_clean}_{timestamp}.csv"
        filepath = os.path.join('scraped_data', filename)
        df.to_csv(filepath, index=False, encoding='utf-8')
        print(f"💾 Dados salvos em: {filepath}")
        return filepath

def scrape_mercado_livre_improved(search_term: str = "", limit: int = 50, save_csv: bool = False) -> pd.DataFrame:
    """
    Função principal para scraping do Mercado Livre melhorado
    Args:
        search_term (str): Termo de busca. Se vazio, faz scraping das ofertas do dia
        limit (int): Limite de produtos a retornar
        save_csv (bool): Se deve salvar em CSV
    Returns:
        pd.DataFrame: DataFrame com os produtos
    """
    scraper = MercadoLivreScraperImproved()
    if search_term and search_term.strip():
        # Busca com termo específico
        products = scraper.scrape_search_page(search_term.strip(), limit)
        search_label = search_term.strip()
    else:
        # Busca padrão - ofertas do dia
        products = scraper.scrape_offers_page(limit)
        search_label = "ofertas_do_dia"
    df = scraper.to_dataframe(products, search_label)
    if save_csv and not df.empty:
        scraper.save_to_csv(df, search_label)
    return df

def get_mercado_livre_data_improved(search_term: str = "", pages: int = 1) -> pd.DataFrame:
    """
    Função de compatibilidade com o sistema existente
    Args:
        search_term (str): Termo de busca. Se vazio, faz scraping das ofertas do dia
        pages (int): Número de páginas (convertido para limit)
    Returns:
        pd.DataFrame: DataFrame com os produtos
    """
    limit = pages * 48  # Aproximadamente 48 produtos por página
    return scrape_mercado_livre_improved(search_term, limit, save_csv=False)

def extract_ml_thumbnail(url: str, download: bool = False, 
                        filename: Optional[str] = None) -> Optional[str]:
    """
    Função simples para extrair thumbnail do Mercado Livre
    Args:
        url: URL do produto
        download: Se deve baixar a imagem (padrão: False)
        filename: Nome personalizado do arquivo
    Returns:
        URL da imagem
    """
    extractor = MercadoLivreThumbnailExtractor()
    thumbnail_url = extractor.extract_thumbnail_from_product_page(url)
    return thumbnail_url  # Sempre retorna apenas a URL agora

if __name__ == "__main__":
    print("=== 🛒 Teste do Scraper Melhorado do Mercado Livre com Extração de Thumbnails ===")
    # Teste 1: Ofertas do dia (busca padrão)
    print("--- 🔍 Teste 1: Ofertas do Dia (Busca Padrão) ---")
    df_offers = scrape_mercado_livre_improved(limit=5, save_csv=True)
    if not df_offers.empty:
        print(f"✅ Sucesso! {len(df_offers)} produtos das ofertas do dia")
        print("\nPrimeiros produtos:")
        for i, row in df_offers.head(3).iterrows():
            img_status = "Com imagem" if row['IMAGE_URL'] else "Sem imagem"
            print(f"  {i+1}. {row['TITLE'][:50]}... - {row['PRICE']} ({img_status})")
    else:
        print("❌ Falha ao obter ofertas do dia")
    print("\n" + "="*60 + "\n")
    # Teste 2: Busca com termo específico
    print("--- 🔍 Teste 2: Busca por 'celular' ---")
    df_search = scrape_mercado_livre_improved("celular", limit=5, save_csv=True)
    if not df_search.empty:
        print(f"✅ Sucesso! {len(df_search)} produtos encontrados para 'celular'")
        print("\nPrimeiros produtos:")
        for i, row in df_search.head(3).iterrows():
            img_status = "Com imagem" if row['IMAGE_URL'] else "Sem imagem"
            print(f"  {i+1}. {row['TITLE'][:50]}... - {row['PRICE']} ({img_status})")
    else:
        print("❌ Falha ao buscar produtos para 'celular'")
    print("\n=== 🎉 Teste Concluído ===")

# Função adicional para testar extração de thumbnail específica
def test_thumbnail_extraction():
    """Testa extração de thumbnail de uma URL específica"""
    print("\n--- 🖼️ Teste de Extração de Thumbnail ---")
    # Você pode testar com uma URL específica do ML
    test_url = "https://produto.mercadolivre.com.br/MLB-1234567890-produto-teste"  # Substituir por URL real
    print(f"Testando extração de thumbnail de: {test_url}")
    thumbnail_url = extract_ml_thumbnail(test_url, download=False)
    if thumbnail_url:
        print(f"✅ Thumbnail encontrada: {thumbnail_url}")
    else:
        print("❌ Não foi possível extrair thumbnail")

if __name__ == "__main__":
    test_thumbnail_extraction()
