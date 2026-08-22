# Web Scraping Mercado Livre - Versão Melhorada com Filtro
# Coleta dados estruturados com pareamento correto e ignora seletores específicos

from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import random
import re
import os
from typing import List, Dict, Optional, Tuple

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.firefox.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    print("Selenium não está instalado. Por favor, instale com: pip install selenium")
    SELENIUM_AVAILABLE = False

class MercadoLivreScraper:
    def __init__(self, ignored_selectors: List[str] = None):
        """
        Inicializa o scraper do Mercado Livre
        
        Args:
            ignored_selectors (List[str]): Lista de seletores CSS para ignorar durante o scraping
        """
        self.driver = None
        self.base_url = 'https://lista.mercadolivre.com.br/'
        # Seletores que devem ser ignorados (exemplo: banners, propagandas, etc.)
        self.ignored_selectors = ignored_selectors or [
            '.brand-wrapper-desktop-new__container-right',  # Seletor fornecido pelo usuário
            '.ui-search-sponsored-disclaimer',  # Anúncios patrocinados
            '.ui-search-advertising',  # Publicidade
            '.ui-search-banner',  # Banners
            '.andes-carousel',  # Carrosséis de propaganda
        ]
        
    def setup_driver(self) -> Optional[webdriver.Firefox]:
        """Configura o driver do Firefox em modo headless"""
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

    def inject_ml_cookies(self, user_id: Optional[str] = None) -> bool:
        """
        Carrega os cookies salvos no Supabase pela extensão Chrome e injeta no WebDriver
        para navegar autenticado no Mercado Livre sem bloqueios de WAF/CAPTCHA.
        """
        if not self.driver:
            return False
        try:
            from database.db_manager import DatabaseManager
            db = DatabaseManager()
            session_data = db.get_ml_session(user_id=user_id)
            if not session_data or not session_data.get('cookies'):
                print("ℹ️ [ML] Nenhum cookie de sessão do ML encontrado no banco.")
                return False

            cookies = session_data.get('cookies', [])
            print(f"🍪 [ML] Injetando {len(cookies)} cookies de sessão no WebDriver Firefox...")

            # É necessário carregar o domínio antes de injetar os cookies
            self.driver.get("https://www.mercadolivre.com.br/robots.txt")
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

            print(f"✅ [ML] {injected} cookies do Mercado Livre injetados com sucesso!")
            return True
        except Exception as e:
            print(f"⚠️ [ML] Erro ao injetar cookies do Mercado Livre: {e}")
            return False
    
    def is_element_ignored(self, element) -> bool:
        """
        Verifica se um elemento deve ser ignorado baseado nos seletores configurados
        
        Args:
            element: Elemento Selenium a ser verificado
            
        Returns:
            bool: True se o elemento deve ser ignorado, False caso contrário
        """
        try:
            # Verifica se o próprio elemento corresponde a algum seletor ignorado
            for selector in self.ignored_selectors:
                try:
                    # Tenta encontrar o seletor dentro do elemento atual
                    if element.find_elements(By.CSS_SELECTOR, selector):
                        return True
                    
                    # Verifica se o elemento atual corresponde ao seletor
                    parent = element.find_element(By.XPATH, './..')
                    if parent.find_elements(By.CSS_SELECTOR, f"{selector}"):
                        # Verifica se o elemento atual está dentro do seletor ignorado
                        ignored_elements = parent.find_elements(By.CSS_SELECTOR, selector)
                        for ignored_elem in ignored_elements:
                            if element == ignored_elem or self._is_child_of(element, ignored_elem):
                                return True
                except:
                    continue
            
            # Verifica se está dentro de um elemento ignorado percorrendo os pais
            current = element
            for _ in range(10):  # Limita a busca a 10 níveis acima
                try:
                    current = current.find_element(By.XPATH, './..')
                    class_names = current.get_attribute('class') or ''
                    
                    for selector in self.ignored_selectors:
                        selector_clean = selector.replace('.', '').replace('#', '')
                        if selector_clean in class_names:
                            return True
                except:
                    break
                    
            return False
        except:
            return False
    
    def _is_child_of(self, child_element, parent_element) -> bool:
        """Verifica se um elemento é filho de outro"""
        try:
            return self.driver.execute_script(
                "return arguments[0].contains(arguments[1]);", 
                parent_element, child_element
            )
        except:
            return False
    
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
    
    def extract_product_data(self) -> List[Dict]:
        """
        Extrai dados completos de cada produto de forma estruturada,
        ignorando elementos que correspondem aos seletores configurados
        
        Returns:
            List[Dict]: Lista de dicionários com dados de cada produto
        """
        products = []
        
        if not self.driver:
            return products
        
        try:
            # Procura pelos containers de produtos (suporta layout tradicional e poly-card)
            product_containers = self.driver.find_elements(By.CSS_SELECTOR, 
                "li.ui-search-layout__item, div.ui-search-result, div.poly-card, .ui-search-layout .ui-search-layout__item, .ui-search-results__item")
            
            print(f"🔍 Encontrados {len(product_containers)} containers de produtos")
            
            filtered_containers = []
            ignored_count = 0
            
            # Filtra containers ignorados
            for container in product_containers:
                if self.is_element_ignored(container):
                    ignored_count += 1
                    continue
                filtered_containers.append(container)
            
            print(f"🚫 {ignored_count} containers ignorados (propagandas/banners)")
            print(f"✅ {len(filtered_containers)} containers válidos para processar")
            
            for i, container in enumerate(filtered_containers):
                try:
                    product_data = {
                        'title': '',
                        'price': '',
                        'price_numeric': 0.0,
                        'rating': 0,
                        'review_count': 0,
                        'image_url': '',
                        'product_url': '',
                        'store_name': ''
                    }
                    
                    # 1. TÍTULO
                    title_selectors = [
                        "h3.poly-component__title",
                        "h2.poly-component__title", 
                        "a.poly-component__title",
                        ".ui-search-item__title",
                        "h3", "h2"
                    ]
                    
                    for selector in title_selectors:
                        try:
                            title_elem = container.find_element(By.CSS_SELECTOR, selector)
                            # Verifica se o elemento do título não está em área ignorada
                            if not self.is_element_ignored(title_elem):
                                title_text = title_elem.text.strip()
                                if len(title_text) > 10:  # Título válido
                                    product_data['title'] = title_text
                                    break
                        except:
                            continue
                    
                    # 2. PREÇO
                    price_selectors = [
                        ".andes-money-amount__fraction",
                        ".price-tag-fraction",
                        ".andes-money-amount",
                        "span[class*='price']"
                    ]
                    
                    for selector in price_selectors:
                        try:
                            price_elem = container.find_element(By.CSS_SELECTOR, selector)
                            if not self.is_element_ignored(price_elem):
                                price_text = price_elem.text.strip()
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
                    
                    # 3. IMAGEM (melhorado)
                    image_selectors = [
                        "img.ui-search-result__image__element",
                        ".ui-search-result__image .ui-search-result__image__element",
                        "img.poly-component__picture",
                        "div.poly-card__portada img",
                        "img[src*='mlstatic']",
                        ".ui-search-result__image img",
                        "img"
                    ]
                    image_found = False
                    for selector in image_selectors:
                        try:
                            img_elem = container.find_element(By.CSS_SELECTOR, selector)
                            if not self.is_element_ignored(img_elem):
                                # Busca em vários atributos
                                img_src = (
                                    img_elem.get_attribute('src') or
                                    img_elem.get_attribute('data-src') or
                                    img_elem.get_attribute('data-lazy-src') or
                                    img_elem.get_attribute('data-original') or
                                    img_elem.get_attribute('data-original-src')
                                )
                                if (img_src and 'mlstatic' in img_src and
                                    not img_src.startswith('data:') and
                                    len(img_src) > 20):
                                    product_data['image_url'] = img_src
                                    print(f"[DEBUG ML Imagem] URL da imagem extraída: {img_src}")
                                    image_found = True
                                    break
                        except:
                            continue
                    # Fallback: busca em elementos filhos se não encontrou imagem
                    if not image_found:
                        try:
                            child_imgs = container.find_elements(By.TAG_NAME, "img")
                            for img_elem in child_imgs:
                                if self.is_element_ignored(img_elem):
                                    continue
                                img_src = (
                                    img_elem.get_attribute('src') or
                                    img_elem.get_attribute('data-src') or
                                    img_elem.get_attribute('data-lazy-src') or
                                    img_elem.get_attribute('data-original') or
                                    img_elem.get_attribute('data-original-src')
                                )
                                if (img_src and 'mlstatic' in img_src and
                                    not img_src.startswith('data:') and
                                    len(img_src) > 20):
                                    product_data['image_url'] = img_src
                                    print(f"[DEBUG ML Imagem Fallback] URL da imagem extraída: {img_src}")
                                    image_found = True
                                    break
                        except Exception as e:
                            print(f"[DEBUG ML Imagem Fallback] Erro ao buscar imagens em filhos: {e}")
                    if not image_found:
                        print(f"[DEBUG ML Imagem] Nenhuma imagem encontrada para produto: {product_data['title']}")
                    
                    # 4. LINK DO PRODUTO
                    try:
                        link_elem = container.find_element(By.CSS_SELECTOR, "a[href*='produto'], a[href*='item'], a[href*='MLB']")
                        if not self.is_element_ignored(link_elem):
                            product_url = link_elem.get_attribute('href')
                            if product_url and 'mercadolivre' in product_url:
                                product_data['product_url'] = product_url
                    except:
                        pass
                    
                    # 5. LOJA/VENDEDOR OFICIAL (GANHADOR DA BUYBOX)
                    store_selectors = [
                        "span.poly-component__seller",
                        ".poly-component__seller",
                        ".ui-search-item__group__element--seller",
                        ".ui-search-item__brand-title",
                        ".ui-search-item__group__element--stores__name",
                        "span.ui-search-item__store-name",
                        "span[class*='seller']",
                        "div[class*='seller'] span",
                        ".ui-search-item__store-name a",
                        "a[href*='/loja/']",
                        "span.ui-pdp-seller__link-trigger",
                        ".ui-seller-data-header__title-container",
                        "span.ui-search-color--BLACK"
                    ]
                    
                    for selector in store_selectors:
                        try:
                            store_elem = container.find_element(By.CSS_SELECTOR, selector)
                            if not self.is_element_ignored(store_elem):
                                store_text = store_elem.text.strip()
                                # Remove prefixos comuns como "Vendido por", "Por", "Loja oficial"
                                clean_store = re.sub(r'^(vendido\s+por\s+|por\s+|loja\s+oficial\s+)', '', store_text, flags=re.IGNORECASE).strip()
                                if (clean_store and 
                                    len(clean_store) > 1 and 
                                    len(clean_store) < 100 and
                                    not clean_store.lower().startswith(('r$', 'em ', 'até ', 'de R$')) and
                                    not clean_store.isdigit()):
                                    product_data['store_name'] = clean_store
                                    break
                        except:
                            continue
                    
                    # 6. AVALIAÇÕES (RATING)
                    rating_selectors = [
                        "div.poly-component__reviews",
                        "span[class*='review']", 
                        "div[class*='rating']",
                        ".ui-search-reviews",
                        "span.ui-search-reviews__rating-number"
                    ]
                    
                    for selector in rating_selectors:
                        try:
                            rating_elem = container.find_element(By.CSS_SELECTOR, selector)
                            if not self.is_element_ignored(rating_elem):
                                aria_label = rating_elem.get_attribute('aria-label') or ''
                                text_content = rating_elem.text.strip()
                                
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
                                else:
                                    # Se não encontrar padrão, tenta extrair número direto
                                    number_match = re.search(r'\d+', text_content)
                                    if number_match:
                                        rating_num = int(number_match.group())
                                        product_data['rating'] = min(rating_num, 5)
                                        break
                        except:
                            continue
                    
                    # 7. NÚMERO DE AVALIAÇÕES (REVIEW COUNT)
                    review_count_selectors = [
                        "span.poly-reviews__count",
                        ".ui-search-reviews__amount",
                        "span[class*='review-count']",
                        "span[class*='reviews']"
                    ]
                    
                    for selector in review_count_selectors:
                        try:
                            review_elem = container.find_element(By.CSS_SELECTOR, selector)
                            if not self.is_element_ignored(review_elem):
                                review_text = review_elem.text.strip()
                                # Extrai número de avaliações (ex: "(123)" ou "123 avaliações")
                                number_match = re.search(r'(\d+)', review_text)
                                if number_match:
                                    product_data['review_count'] = int(number_match.group(1))
                                    break
                        except:
                            continue
                    
                    # Se não encontrou contagem específica, procura em qualquer elemento do container
                    if product_data['review_count'] == 0:
                        try:
                            all_elements = container.find_elements(By.TAG_NAME, "span")
                            for elem in all_elements:
                                if not self.is_element_ignored(elem):
                                    text = elem.text.strip()
                                    if ('avaliação' in text.lower() or 'opinião' in text.lower()) and re.search(r'\d+', text):
                                        number_match = re.search(r'(\d+)', text)
                                        if number_match:
                                            product_data['review_count'] = int(number_match.group(1))
                                            break
                        except:
                            pass
                    
                    # 8. DETECÇÃO DE CATÁLOGO / BUYBOX / OPÇÕES DE COMPRA
                    is_catalog = False
                    sellers_count = 1
                    buybox_min_price = 0.0
                    try:
                        # Verifica se a URL do produto já é de catálogo (/p/MLB...)
                        prod_link = product_data.get('product_url', '')
                        if re.search(r'/p/MLB\d+', prod_link):
                            is_catalog = True
                        
                        # Verifica se possui elemento de buybox ou opções de compra de múltiplos sellers
                        buybox_elems = container.find_elements(By.CSS_SELECTOR, 
                            ".poly-component__buybox, .poly-phrase-buybox, a[href*='/s#polycard_client'], a[href*='/s?'], a[href*='/s'], span[class*='buybox'], .ui-search-item__group__element--buybox, .ui-pdp-products, .ui-pdp-products__list, .ui-pdp-products__button"
                        )
                        for b_el in buybox_elems:
                            if b_el.is_displayed() and b_el.text.strip():
                                is_catalog = True
                                b_text = b_el.text.strip()
                                # Extrai quantidade de produtos/sellers (ex: "22 produtos novos a partir de R$ 699")
                                m_count = re.search(r'(\d+)\s+produtos?\s+novos?', b_text, re.IGNORECASE)
                                if m_count:
                                    sellers_count = int(m_count.group(1))
                                m_price = re.search(r'a partir de\s*R\$\s*([\d\.,]+)', b_text, re.IGNORECASE)
                                if m_price:
                                    try:
                                        buybox_min_price = float(m_price.group(1).replace('.', '').replace(',', '.'))
                                    except:
                                        pass
                                break
                        
                        # Verifica textos explícitos de opções de compra no container
                        if not is_catalog or sellers_count == 1:
                            c_text = container.text
                            if 'opções de compra' in c_text.lower() or 'produtos novos a partir de' in c_text.lower():
                                is_catalog = True
                                m_count = re.search(r'(\d+)\s+produtos?\s+novos?', c_text, re.IGNORECASE)
                                if m_count:
                                    sellers_count = int(m_count.group(1))
                                m_price = re.search(r'a partir de\s*R\$\s*([\d\.,]+)', c_text, re.IGNORECASE)
                                if m_price:
                                    try:
                                        buybox_min_price = float(m_price.group(1).replace('.', '').replace(',', '.'))
                                    except:
                                        pass
                    except Exception:
                        pass

                    product_data['is_catalog'] = is_catalog
                    product_data['sellers_count'] = sellers_count
                    product_data['buybox_min_price'] = buybox_min_price

                    # 9. FRETE / LOGÍSTICA (FULL, Flex, Grátis)
                    shipping_type = "Frete Grátis"
                    try:
                        container_text = container.text.lower()
                        if 'full' in container_text or container.find_elements(By.CSS_SELECTOR, "svg[class*='full'], .poly-component__shipping--full, .ui-search-item__fulfillment"):
                            shipping_type = "FULL"
                        elif 'chegará hoje' in container_text or 'flex' in container_text:
                            shipping_type = "Flex"
                    except Exception:
                        pass
                    product_data['shipping_type'] = shipping_type

                    # 10. PARCELAMENTO
                    installments = ""
                    try:
                        inst_elem = container.find_element(By.CSS_SELECTOR, ".poly-price__installments, span[class*='installments']")
                        if inst_elem:
                            installments = inst_elem.text.strip()
                    except Exception:
                        pass
                    product_data['installments'] = installments

                    # 11. PREÇO ANTIGO (RISCADO)
                    old_price = ""
                    try:
                        old_p_elem = container.find_element(By.CSS_SELECTOR, "s.andes-money-amount--previous .andes-money-amount__fraction, s[class*='previous'] .andes-money-amount__fraction")
                        if old_p_elem:
                            old_price = f"R$ {old_p_elem.text.strip()}"
                    except Exception:
                        pass
                    product_data['old_price'] = old_price

                    # Só adiciona se tem dados mínimos (título e preço)
                    if product_data['title'] and product_data['price']:
                        products.append(product_data)
                        review_info = f"{product_data['rating']}⭐ ({product_data['review_count']} reviews)" if product_data['rating'] > 0 or product_data['review_count'] > 0 else "Sem avaliações"
                        cat_tag = "[CATÁLOGO]" if is_catalog else "[INDIVIDUAL]"
                        print(f"✅ Produto {len(products)}: {cat_tag} {product_data['title'][:35]}... | {product_data['store_name'] or 'Loja'} | {product_data['price']} | {review_info}")
                    
                except Exception as e:
                    print(f"❌ Erro ao processar produto {i+1}: {e}")
                    continue
        
        except Exception as e:
            print(f"❌ Erro ao extrair dados dos produtos: {e}")
        
        print(f"🎯 Total de produtos extraídos: {len(products)}")
        return products
    
    def scrape_page(self, url: str) -> Optional[List[Dict]]:
        """
        Faz scraping de uma única página
        
        Args:
            url (str): URL da página
            
        Returns:
            Optional[List[Dict]]: Lista com dados dos produtos ou None
        """
        if not self.driver:
            return None
            
        page_source = self.get_page_with_selenium(url)
        if not page_source:
            return None
        
        return self.extract_product_data()
    
    def scrape_search(self, search_term: str, n_pages: int = 1, delay_range: Tuple[float, float] = (1, 3), user_id: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Faz scraping de múltiplas páginas para um termo de pesquisa com injeção de sessão
        
        Args:
            search_term (str): Termo de pesquisa
            n_pages (int): Número de páginas para processar
            delay_range (Tuple[float, float]): Intervalo de delay entre páginas
            user_id (str, optional): ID do usuário para injeção de sessão do Mercado Livre
            
        Returns:
            Optional[pd.DataFrame]: DataFrame com os dados ou None
        """
        if not search_term or not search_term.strip():
            print("❌ Termo de pesquisa inválido")
            return None
        
        if not self.setup_driver():
            print("❌ Falha ao inicializar o driver")
            return None
        
        try:
            # Injeta cookies de sessão autêntica para evitar bloqueios de WAF/CAPTCHA em VPS
            self.inject_ml_cookies(user_id=user_id)

            all_products = []
            
            # Formata o termo de pesquisa para URL
            formatted_term = search_term.replace(' ', '-').lower()
            search_url = f"{self.base_url}{formatted_term}"
            
            for page in range(1, n_pages + 1):
                try:
                    # Constrói URL da página
                    if page == 1:
                        page_url = search_url
                    else:
                        page_url = f"{search_url}_Desde_{((page-1)*50)+1}"
                    
                    print(f"📄 Processando página {page}/{n_pages}: {page_url}")
                    
                    # Faz scraping da página
                    page_products = self.scrape_page(page_url)
                    
                    if page_products:
                        all_products.extend(page_products)
                        print(f"✅ Página {page}: {len(page_products)} produtos coletados")
                    else:
                        print(f"⚠️ Página {page}: Nenhum produto encontrado")
                    
                    # Delay entre páginas (exceto na última)
                    if page < n_pages:
                        delay = random.uniform(delay_range[0], delay_range[1])
                        print(f"⏳ Aguardando {delay:.1f}s...")
                        time.sleep(delay)
                        
                except Exception as e:
                    print(f"❌ Erro na página {page}: {e}")
                    continue
            
            if not all_products:
                print("❌ Nenhum produto foi encontrado")
                return None
            
            # Converte para DataFrame
            df_data = []
            for product in all_products:
                df_data.append({
                    'TITLE': product['title'],
                    'PRICE': product['price'],
                    'PRICE_NUMERIC': product['price_numeric'],
                    'RATING': product['rating'],
                    'REVIEWS': product['review_count'],
                    'IMAGE_URL': product['image_url'],
                    'PRODUCT_URL': product['product_url'],
                    'STORE_NAME': product['store_name'],
                    'SEARCH_TERM': search_term,
                    'IS_CATALOG': product.get('is_catalog', False),
                    'SELLERS_COUNT': product.get('sellers_count', 1),
                    'BUYBOX_MIN_PRICE': product.get('buybox_min_price', 0.0),
                    'SHIPPING_TYPE': product.get('shipping_type', 'Frete Grátis'),
                    'INSTALLMENTS': product.get('installments', ''),
                    'OLD_PRICE': product.get('old_price', ''),
                    'SCRAPY_DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'MARKETPLACE': 'MercadoLivre'
                })
            
            df = pd.DataFrame(df_data)
            
            print(f"🎉 Scraping concluído! Total: {len(df)} produtos")
            return df
            
        finally:
            if self.driver:
                self.driver.quit()
    
    def save_to_csv(self, df: pd.DataFrame, search_term: str = "mercado_livre", filename: Optional[str] = None) -> str:
        """Salva DataFrame em arquivo CSV"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            search_clean = re.sub(r'[^\w\-_]', '_', search_term)[:30]
            filename = f"ml_{search_clean}_{timestamp}.csv"
        
        os.makedirs('scraped_data', exist_ok=True)
        filepath = os.path.join('scraped_data', filename)
        
        df.to_csv(filepath, index=False, encoding='utf-8')
        print(f"💾 Dados salvos em: {filepath}")
        return filepath

def scrape_mercado_livre(search_term: str, n_pages: int = 1, save_csv: bool = False, ignored_selectors: List[str] = None, user_id: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    Função principal para scraping do Mercado Livre
    
    Args:
        search_term (str): Termo de pesquisa
        n_pages (int): Número de páginas para processar
        save_csv (bool): Se deve salvar em CSV
        ignored_selectors (List[str]): Seletores CSS adicionais para ignorar
        user_id (str, optional): ID do usuário para injeção de sessão
        
    Returns:
        Optional[pd.DataFrame]: DataFrame com os dados ou None
    """
    scraper = MercadoLivreScraper(ignored_selectors)
    
    df = scraper.scrape_search(search_term, n_pages, user_id=user_id)
    
    if df is not None and save_csv:
        scraper.save_to_csv(df, search_term)
        
    return df

def get_mercado_livre_data(search_term: str, pages: int = 1, ignored_selectors: List[str] = None, user_id: Optional[str] = None) -> Optional[pd.DataFrame]:
    """Função simplificada para importação em outros arquivos com suporte a sessão"""
    return scrape_mercado_livre(search_term, pages, save_csv=False, ignored_selectors=ignored_selectors, user_id=user_id)

# Exemplo de uso:
if __name__ == "__main__":
    # Scraping com o seletor ignorado
    df = scrape_mercado_livre("smartphone", n_pages=2, save_csv=True)
    
    # Ou para adicionar mais seletores ignorados:
    custom_ignored = [
        '.brand-wrapper-desktop-new__container-right',
        '.custom-ad-banner',
        '.promotional-content'
    ]
    df = scrape_mercado_livre("notebook", n_pages=1, ignored_selectors=custom_ignored)