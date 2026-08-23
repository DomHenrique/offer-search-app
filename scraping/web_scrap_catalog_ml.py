# scraping/web_scrap_catalog_ml.py
# Scraper de Catálogos do Mercado Livre
# Extrai lista de catálogos por termo e vendedores por catalog_id

import re
import time
import random
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional

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


# ─── Regex para extrair catalog_id de URLs do ML ─────────────────────────────

def extract_catalog_id_from_url(url: str) -> Optional[str]:
    """
    Extrai o catalog_id (ex: MLB45231994) de uma URL do Mercado Livre.
    Retorna None se a URL não for de catálogo.
    
    Padrões aceitos:
      - /p/MLB45231994/
      - /p/MLB45231994?...
      - /p/MLB45231994/s?...
    """
    if not url:
        return None
    match = re.search(r'/p/(MLB\d+)', url)
    return match.group(1) if match else None


# ─── Classe Principal ─────────────────────────────────────────────────────────

class CatalogScraper:
    """
    Scraper de catálogos do Mercado Livre.
    Responsabilidades:
      - scrape_catalog_list(): busca catálogos por termo, retorna lista deduplicada
      - scrape_catalog_sellers(): scraping de sellers de um catálogo específico
    """

    def __init__(self):
        self.driver = None
        self.search_base_url = 'https://lista.mercadolivre.com.br/'
        self.catalog_base_url = 'https://www.mercadolivre.com.br/p/{catalog_id}/s?'
        self.ignored_selectors = [
            '.ui-search-sponsored-disclaimer',
            '.ui-search-advertising',
            '.ui-search-banner',
            '.andes-carousel',
        ]

    def setup_driver(self) -> Optional[object]:
        """Configura o driver Firefox headless (mesmo padrão do MercadoLivreScraper)."""
        if not SELENIUM_AVAILABLE:
            print("❌ Selenium não disponível")
            return None
        try:
            firefox_options = Options()
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
            return self.driver

        except Exception as e:
            print(f"❌ Erro ao configurar Firefox driver: {e}")
            return None

    def close_driver(self):
        """Fecha o driver se estiver aberto."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None

    def _load_page(self, url: str, wait_time: int = 10) -> bool:
        """Carrega uma URL e aguarda o body estar presente. Retorna True se OK."""
        if not self.driver:
            return False
        try:
            self.driver.get(url)
            time.sleep(random.uniform(1.5, 3))
            WebDriverWait(self.driver, wait_time).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Scroll suave para carregar lazy content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(0.8)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
            return True
        except Exception as e:
            print(f"⚠️ Erro ao carregar página {url}: {e}")
            return False

    def _is_login_page(self) -> bool:
        """Detecta se o Selenium foi redirecionado para página de login do ML."""
        try:
            current_url = self.driver.current_url
            page_source = self.driver.page_source
            login_indicators = [
                'login.mercadolivre.com.br',
                'mercadolivre.com.br/jms/mlb/lgz',
                'id="user_id"',
                'id="password"',
                'Entrar no Mercado Livre',
                'Faça login no Mercado Livre',
            ]
            for indicator in login_indicators:
                if indicator in current_url or indicator in page_source:
                    return True
            return False
        except Exception:
            return False

    def inject_ml_cookies(self, user_id: Optional[str] = None) -> bool:
        """
        Carrega os cookies salvos no Supabase e injeta no WebDriver
        para navegar autenticado no Mercado Livre.
        """
        if not self.driver:
            return False
        try:
            from database.db_manager import DatabaseManager
            db = DatabaseManager()
            session_data = db.get_ml_session(user_id=user_id)
            if not session_data or not session_data.get('cookies'):
                print("ℹ️ Nenhum cookie de sessão do ML encontrado no banco.")
                return False

            cookies = session_data.get('cookies', [])
            print(f"🍪 Injetando {len(cookies)} cookies de sessão no Selenium...")

            # Para injetar cookies no Selenium, é obrigatório primeiro estar no domínio
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
                        # Remove leading dot if any issue
                        cookie_dict['domain'] = domain.lstrip('.')
                    if c.get('secure'):
                        cookie_dict['secure'] = True
                    if c.get('httpOnly'):
                        cookie_dict['httpOnly'] = True

                    self.driver.add_cookie(cookie_dict)
                    injected += 1
                except Exception:
                    pass

            print(f"✅ {injected} cookies do Mercado Livre injetados com sucesso!")
            return True
        except Exception as e:
            print(f"⚠️ Erro ao injetar cookies no Selenium: {e}")
            return False

    # ─── Scraping de lista de catálogos ──────────────────────────────────────

    def scrape_catalog_list(self, search_term: str, n_pages: int = 1) -> Dict:
        """
        Busca catálogos por termo de pesquisa.
        
        Fluxo:
        1. Abre a lista de resultados do ML para o termo
        2. Extrai URLs de todos os produtos
        3. Filtra apenas os que têm catalog_id (/p/MLBxxxxxx)
        4. Deduplica por catalog_id
        5. Retorna lista de catálogos com nome, imagem e catalog_id
        
        Returns:
            {
                'success': bool,
                'catalogs': [{'catalog_id', 'nome', 'imagem', 'produto_url'}],
                'error': str | None
            }
        """
        print(f"🔍 Buscando catálogos para: '{search_term}' ({n_pages} página(s))")

        if not self.setup_driver():
            return {'success': False, 'catalogs': [], 'error': 'Falha ao inicializar o driver'}

        try:
            all_products = []
            
            # Higieniza o termo de busca removendo ruídos de notas fiscais/pedidos
            clean_term = re.sub(r'\(.*?\)', ' ', search_term)
            clean_term = re.sub(r'\+.*$', ' ', clean_term)
            clean_term = re.sub(r'\b(NexGen|XT60|127V|220V|BR|EU)\b', ' ', clean_term, flags=re.IGNORECASE)
            clean_term = re.sub(r'[^a-zA-Z0-9\sáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ-]', ' ', clean_term)
            clean_term = ' '.join(clean_term.split())
            if not clean_term:
                clean_term = search_term

            formatted_term = clean_term.replace(' ', '-').lower()

            for page in range(1, n_pages + 1):
                if page == 1:
                    url = f"{self.search_base_url}{formatted_term}"
                else:
                    url = f"{self.search_base_url}{formatted_term}_Desde_{((page - 1) * 50) + 1}"

                print(f"📄 Página {page}: {url}")
                if not self._load_page(url):
                    print(f"⚠️ Falha ao carregar página {page}")
                    continue

                containers = self.driver.find_elements(By.CSS_SELECTOR, "li.ui-search-layout__item")
                print(f"   Encontrados {len(containers)} produtos")

                for container in containers:
                    try:
                        # Título
                        title = ''
                        for sel in ["h3.poly-component__title", "h2.poly-component__title",
                                    "a.poly-component__title", ".ui-search-item__title", "h3", "h2"]:
                            try:
                                el = container.find_element(By.CSS_SELECTOR, sel)
                                t = el.text.strip()
                                if len(t) > 5:
                                    title = t
                                    break
                            except Exception:
                                continue

                        # URL do produto
                        product_url = ''
                        try:
                            link = container.find_element(
                                By.CSS_SELECTOR,
                                "a[href*='mercadolivre'], a[href*='mercadolibre']"
                            )
                            product_url = link.get_attribute('href') or ''
                        except Exception:
                            pass

                        # Imagem
                        image_url = ''
                        for img_sel in [
                            "img.poly-component__picture",
                            "div.poly-card__portada img",
                            "img[src*='mlstatic']",
                            "img"
                        ]:
                            try:
                                img = container.find_element(By.CSS_SELECTOR, img_sel)
                                src = (img.get_attribute('src') or
                                       img.get_attribute('data-src') or
                                       img.get_attribute('data-lazy-src') or '')
                                if src and 'mlstatic' in src and not src.startswith('data:'):
                                    image_url = src
                                    break
                            except Exception:
                                continue

                        # Preço de mercado
                        price_val = 0.0
                        for p_sel in [
                            ".poly-price__current .andes-money-amount__fraction",
                            ".ui-search-price__second-line .andes-money-amount__fraction",
                            ".andes-money-amount__fraction",
                            "span.price-tag-fraction"
                        ]:
                            try:
                                p_elem = container.find_element(By.CSS_SELECTOR, p_sel)
                                p_text = (p_elem.text or '').replace('.', '').replace(',', '.').strip()
                                if p_text:
                                    price_val = float(p_text)
                                    break
                            except Exception:
                                continue

                        if title and product_url:
                            all_products.append({
                                'titulo': title,
                                'produto_url': product_url,
                                'imagem': image_url,
                                'preco': price_val,
                            })
                    except Exception as e:
                        print(f"   ⚠️ Erro ao processar produto: {e}")
                        continue

                # Delay entre páginas
                if page < n_pages:
                    time.sleep(random.uniform(1.5, 3))

            # Filtra e deduplica por catalog_id
            seen_ids = set()
            catalogs = []

            for product in all_products:
                catalog_id = extract_catalog_id_from_url(product['produto_url'])
                if catalog_id and catalog_id not in seen_ids:
                    seen_ids.add(catalog_id)
                    catalogs.append({
                        'catalog_id': catalog_id,
                        'nome': product['titulo'],
                        'imagem': product['imagem'],
                        'produto_url': product['produto_url'],
                        'buybox_min_price': float(product.get('preco') or 0.0),
                    })

            print(f"✅ {len(catalogs)} catálogos únicos encontrados de {len(all_products)} produtos")
            return {'success': True, 'catalogs': catalogs, 'error': None}

        except Exception as e:
            print(f"❌ Erro no scraping de lista: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'catalogs': [], 'error': str(e)}

        finally:
            self.close_driver()

    # ─── Scraping de sellers de um catálogo ──────────────────────────────────

    def scrape_catalog_sellers(self, catalog_id: str, user_id: Optional[str] = None) -> Dict:
        """
        Faz scraping dos vendedores de um catálogo específico.
        
        Acessa: https://www.mercadolivre.com.br/p/<catalog_id>/s?
        
        Returns:
            {
                'success': bool,
                'sellers': [{
                    'seller_name', 'preco', 'preco_str', 'frete_gratis',
                    'frete_full', 'reputacao', 'condicao', 'is_best_offer', 'posicao'
                }],
                'error': str | None,
                'login_required': bool
            }
        """
        print(f"🏪 Buscando sellers do catálogo: {catalog_id}")

        if not self.setup_driver():
            return {
                'success': False, 'sellers': [],
                'error': 'Falha ao inicializar o driver', 'login_required': False
            }

        # Injeta cookies de sessão ativa do Mercado Livre do usuário se existirem
        self.inject_ml_cookies(user_id=user_id)

        url = f"https://www.mercadolivre.com.br/p/{catalog_id}/s?"

        try:
            if not self._load_page(url, wait_time=15):
                return {
                    'success': False, 'sellers': [],
                    'error': f'Falha ao carregar página do catálogo {catalog_id}',
                    'login_required': False
                }

            # Verifica redirecionamento de login
            if self._is_login_page():
                print("⚠️ Sessão do ML não autenticada ou expirada — redirecionado para login")
                return {
                    'success': False, 'sellers': [],
                    'error': 'Sessão do Mercado Livre expirada ou não sincronizada. Abra a extensão ML Session Sync no Chrome e clique em "Sincronizar Sessão".',
                    'login_required': True
                }

            # Aguarda sellers carregarem
            time.sleep(2)

            # Tenta múltiplos seletores para a tabela de sellers (baseado no DOM atual do ML)
            seller_rows = []
            seller_selectors = [
                "form.ui-pdp-buybox.ui-pdp-table__row",
                "form.ui-pdp-s-table__row",
                "form[id*='buybox-form']",
                ".ui-pdp-table__row",
                ".ui-pdp-s-table__row",
                "div.ui-pdp-buybox__offers__item",
                ".andes-table__row--body",
                "tr.andes-table__row",
                "[class*='seller-list'] [class*='row']",
                "[class*='offers'] [class*='item']",
                "li[class*='seller']",
                ".ui-pdp-media",
            ]

            for sel in seller_selectors:
                try:
                    rows = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if rows:
                        seller_rows = rows
                        print(f"   Seletor de sellers: '{sel}' → {len(rows)} itens")
                        break
                except Exception:
                    continue

            if not seller_rows:
                # Fallback: tenta extrair dados do page source com BeautifulSoup
                print("   Tentando fallback com BeautifulSoup...")
                sellers = self._extract_sellers_from_source()
            else:
                sellers = self._extract_sellers_from_elements(seller_rows)

            print(f"✅ {len(sellers)} sellers encontrados")
            return {'success': True, 'sellers': sellers, 'error': None, 'login_required': False}

        except Exception as e:
            print(f"❌ Erro no scraping de sellers: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False, 'sellers': [],
                'error': str(e), 'login_required': False
            }

        finally:
            self.close_driver()

    def _extract_sellers_from_elements(self, seller_rows: list) -> List[Dict]:
        """Extrai dados detalhados de sellers a partir dos elementos da tabela de opções do ML."""
        sellers = []

        for i, row in enumerate(seller_rows):
            try:
                seller = {
                    'seller_name': '',
                    'seller_id_ml': '',
                    'preco': 0.0,
                    'preco_str': '',
                    'parcelamento': '',
                    'frete_gratis': False,
                    'frete_full': False,
                    'entrega_texto': '',
                    'retirada_texto': '',
                    'reputacao': '',
                    'condicao': 'Novo',
                    'is_best_offer': i == 0,
                    'posicao': i + 1,
                    'buy_url': ''
                }

                row_text = row.text
                row_text_lower = row_text.lower()

                # ── 1. Extração do Vendedor e Reputação ────────────────────────
                seller_found = False
                for sel in [
                    ".ui-seller-data-header__title span",
                    ".ui-seller-data-header__title",
                    ".ui-seller-data-header__title-container h2 span",
                    ".ui-seller-data a[href*='/loja/']",
                    "div.ui-seller-data a.ui-seller-data-header__main-info",
                    "a[href*='/loja/']",
                    "a.ui-pdp-seller__link span",
                    "a.ui-pdp-seller__link",
                    ".ui-pdp-seller__header_title a span",
                    ".ui-pdp-seller__header_title",
                    ".ui-pdp-s-table__seller a",
                    ".ui-pdp-seller__link-trigger-button",
                    "span.ui-pdp-seller__link-trigger",
                    "a[href*='/perfil/']",
                    "a[href*='seller']",
                    ".ui-pdp-action-modal__link",
                    ".ui-seller-info__title",
                    "span[class*='seller']",
                    "[class*='seller-name']",
                    "[class*='seller__name']",
                    "button[class*='seller']",
                    "td:nth-child(4)",
                    "td:nth-child(3)",
                ]:
                    try:
                        el = row.find_element(By.CSS_SELECTOR, sel)
                        text_val = el.text.strip()
                        if text_val and len(text_val) > 1 and not re.match(r'^(comprar|adicionar|novo|r\$|\d)', text_val.lower()):
                            lines = [l.strip() for l in text_val.split('\n') if l.strip()]
                            seller['seller_name'] = lines[0]
                            if len(lines) > 1:
                                seller['reputacao'] = ' | '.join(lines[1:])
                            seller_found = True
                            break
                    except Exception:
                        continue

                # Reputação complementar
                for rep_sel in [".ui-pdp-seller__header_info", ".ui-pdp-seller__header", ".ui-pdp-s-table__seller"]:
                    try:
                        rep_el = row.find_element(By.CSS_SELECTOR, rep_sel)
                        rep_txt = rep_el.text.strip()
                        if ('vendas' in rep_txt.lower() or 'mercadolíder' in rep_txt.lower()) and not seller['reputacao']:
                            rep_lines = [l.strip() for l in rep_txt.split('\n') if 'venda' in l.lower() or 'líder' in l.lower() or 'lider' in l.lower()]
                            if rep_lines:
                                seller['reputacao'] = ' | '.join(rep_lines)
                    except Exception:
                        pass

                # Se não encontrou pelo seletor específico, busca no texto da linha
                if not seller_found:
                    rep_match = re.search(r'([+\d\s]+(?:mil)?\s*vendas|MercadoLíder[^\n]*)', row_text, re.IGNORECASE)
                    if rep_match:
                        seller['reputacao'] = rep_match.group(1).strip()

                    for line in row_text.split('\n'):
                        l = line.strip()
                        if l and len(l) > 2 and not re.search(r'(r\$|chegará|retire|comprar|adicionar|novo|usado|10x|12x|\d+x)', l, re.IGNORECASE):
                            seller['seller_name'] = l
                            break

                if not seller['seller_name']:
                    seller['seller_name'] = f"Vendedor Oficial #{i + 1}"

                # ── 2. Extração de Preço Total e Parcelamento ──────────────────
                # Tenta extrair primeiro do container de preço da BuyBox
                price_extracted = False
                try:
                    price_container = row.find_element(By.CSS_SELECTOR, ".ui-pdp-price__main-container, .ui-pdp-price")
                    frac_el = price_container.find_element(By.CSS_SELECTOR, ".andes-money-amount__fraction")
                    cents_txt = "00"
                    try:
                        cents_el = price_container.find_element(By.CSS_SELECTOR, ".andes-money-amount__cents")
                        cents_txt = cents_el.text.strip() or "00"
                    except Exception:
                        pass

                    frac_txt = frac_el.text.strip().replace('.', '')
                    full_price_str = f"{frac_txt}.{cents_txt}"
                    val = float(full_price_str)
                    if val > 0:
                        seller['preco'] = val
                        seller['preco_str'] = f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                        price_extracted = True
                except Exception:
                    pass

                if not price_extracted:
                    money_amounts = re.findall(r'R\$\s*([\d.]+,\d{2}|[\d.]+)', row_text)
                    prices_floats = []
                    for m in money_amounts:
                        try:
                            clean_p = m.replace('.', '').replace(',', '.')
                            val = float(clean_p)
                            if val > 0:
                                prices_floats.append((val, m))
                        except Exception:
                            pass

                    if prices_floats:
                        main_price_val, main_price_str = max(prices_floats, key=lambda x: x[0])
                        seller['preco'] = main_price_val
                        seller['preco_str'] = f"R$ {main_price_val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

                # Parcelamento
                install_match = re.search(r'(\d+x\s*R?\$?\s*[\d.,]+(?:\s*sem\s*juros)?)', row_text, re.IGNORECASE)
                if install_match:
                    seller['parcelamento'] = install_match.group(1).strip()
                else:
                    try:
                        inst_el = row.find_element(By.CSS_SELECTOR, ".ui-pdp-media__body p, p.ui-pdp-media_title")
                        if inst_el and inst_el.text.strip():
                            seller['parcelamento'] = inst_el.text.strip()
                    except Exception:
                        pass

                # ── 3. Forma de Entrega e Retirada ────────────────────────────
                if 'chegará grátis' in row_text_lower or 'chegara gratis' in row_text_lower or 'grátis' in row_text_lower:
                    seller['frete_gratis'] = True

                if 'full' in row_text_lower:
                    seller['frete_full'] = True

                chegara_match = re.search(r'(Chegará\s+(?:grátis\s+)?entre[^\n]+|Chegará\s+[^\n]+)', row_text, re.IGNORECASE)
                if chegara_match:
                    seller['entrega_texto'] = chegara_match.group(1).strip()
                elif seller['frete_gratis']:
                    seller['entrega_texto'] = "Chegará grátis com envio rápido"

                retire_match = re.search(r'(Retire\s+(?:grátis\s+)?[^\n]+)', row_text, re.IGNORECASE)
                if retire_match:
                    seller['retirada_texto'] = retire_match.group(1).strip()

                # ── 4. Condição ───────────────────────────────────────────────
                if 'usado' in row_text_lower:
                    seller['condicao'] = 'Usado'
                elif 'recondicionado' in row_text_lower:
                    seller['condicao'] = 'Recondicionado'
                else:
                    seller['condicao'] = 'Novo'

                # ── 5. Link de Compra ─────────────────────────────────────────
                try:
                    buy_btn = row.find_element(By.CSS_SELECTOR, "a[href*='checkout'], a[href*='comprar'], a[href*='cart'], a.andes-button, button[type='submit']")
                    seller['buy_url'] = buy_btn.get_attribute('href') or ''
                except Exception:
                    pass

                sellers.append(seller)

            except Exception as e:
                print(f"   ⚠️ Erro ao processar seller {i + 1}: {e}")
                continue

        # Ordena por preço crescente
        sellers.sort(key=lambda s: s['preco'] if s['preco'] > 0 else 999999)
        for idx, s in enumerate(sellers):
            s['posicao'] = idx + 1
            s['is_best_offer'] = (idx == 0)

        return sellers

    def _extract_sellers_from_source(self) -> List[Dict]:
        """Fallback: extrai sellers do page source usando BeautifulSoup com parsing inteligente."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            sellers = []
            rows = (
                soup.select('form.ui-pdp-buybox.ui-pdp-table__row') or
                soup.select('form.ui-pdp-s-table__row') or
                soup.select('.ui-pdp-table__row') or
                soup.select('tr.andes-table__row') or
                soup.select('.andes-table__row--body') or
                soup.select('[class*="buybox__offers"] [class*="item"]') or
                soup.select('[class*="offers"] [class*="item"]') or
                soup.select('tr')
            )

            for i, row in enumerate(rows[:30]):
                text = row.get_text(separator='\n', strip=True)
                if not text or len(text) < 10:
                    continue

                lines = [l.strip() for l in text.split('\n') if l.strip()]
                text_full = ' '.join(lines)
                text_lower = text_full.lower()

                # Preço
                money_amounts = re.findall(r'R\$\s*([\d.]+,\d{2}|[\d.]+)', text_full)
                if not money_amounts:
                    continue

                prices_floats = []
                for m in money_amounts:
                    try:
                        clean_p = m.replace('.', '').replace(',', '.')
                        val = float(clean_p)
                        if val > 0:
                            prices_floats.append((val, m))
                    except Exception:
                        pass

                if not prices_floats:
                    continue

                main_price_val, main_price_str = max(prices_floats, key=lambda x: x[0])

                # Vendedor
                seller_name = ''
                seller_tag = row.select_one('a.ui-pdp-seller__link span, a.ui-pdp-seller__link, .ui-pdp-s-table__seller a, .ui-pdp-seller__header_title')
                if seller_tag:
                    seller_name = seller_tag.get_text(strip=True)
                else:
                    for l in lines:
                        if len(l) > 2 and not re.search(r'(r\$|chegará|retire|comprar|adicionar|novo|usado|10x|12x|\d+x|\d+ unidades)', l, re.IGNORECASE):
                            seller_name = l
                            break

                sellers.append({
                    'seller_name': seller_name or f"Vendedor #{i + 1}",
                    'seller_id_ml': '',
                    'preco': main_price_val,
                    'preco_str': f"R$ {main_price_val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
                    'parcelamento': (re.search(r'(\d+x\s*R?\$?\s*[\d.,]+(?:\s*sem\s*juros)?)', text_full, re.I) or [''])[0],
                    'frete_gratis': 'grátis' in text_lower or 'gratis' in text_lower,
                    'frete_full': 'full' in text_lower,
                    'entrega_texto': (re.search(r'(Chegará\s+[^\n]+)', text_full, re.I) or [''])[0] or ('Chegará grátis' if 'grátis' in text_lower else ''),
                    'retirada_texto': (re.search(r'(Retire\s+[^\n]+)', text_full, re.I) or [''])[0],
                    'reputacao': (re.search(r'([+\d\s]+(?:mil)?\s*vendas|MercadoLíder[^\n]*)', text_full, re.I) or [''])[0],
                    'condicao': 'Usado' if 'usado' in text_lower else 'Novo',
                    'is_best_offer': i == 0,
                    'posicao': i + 1,
                    'buy_url': ''
                })

            sellers.sort(key=lambda s: s['preco'] if s['preco'] > 0 else 999999)
            for idx, s in enumerate(sellers):
                s['posicao'] = idx + 1
                s['is_best_offer'] = (idx == 0)

            return sellers
        except Exception as e:
            print(f"❌ Erro no fallback BeautifulSoup: {e}")
            return []


# ─── Funções de conveniência ──────────────────────────────────────────────────

def get_catalog_list(search_term: str, n_pages: int = 1) -> Dict:
    """Função simplificada para buscar lista de catálogos."""
    scraper = CatalogScraper()
    return scraper.scrape_catalog_list(search_term, n_pages)


def get_catalog_sellers(catalog_id: str, user_id: Optional[str] = None) -> Dict:
    """Função simplificada para buscar sellers de um catálogo com sessão do usuário."""
    scraper = CatalogScraper()
    return scraper.scrape_catalog_sellers(catalog_id, user_id=user_id)


# ─── Teste standalone ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("TESTE 1: Busca de catálogos por termo")
    print("=" * 60)
    result = get_catalog_list("ecoflow river", n_pages=1)
    print(f"Sucesso: {result['success']}")
    if result['error']:
        print(f"Erro: {result['error']}")
    print(f"Catálogos encontrados: {len(result['catalogs'])}")
    for cat in result['catalogs'][:5]:
        print(f"  [{cat['catalog_id']}] {cat['nome'][:60]}")

    if result['catalogs']:
        print("\n" + "=" * 60)
        print(f"TESTE 2: Sellers do catálogo {result['catalogs'][0]['catalog_id']}")
        print("=" * 60)
        sellers_result = get_catalog_sellers(result['catalogs'][0]['catalog_id'])
        print(f"Sucesso: {sellers_result['success']}")
        if sellers_result['error']:
            print(f"Erro: {sellers_result['error']}")
        print(f"Sellers encontrados: {len(sellers_result['sellers'])}")
        for s in sellers_result['sellers']:
            print(f"  #{s['posicao']} {s['seller_name']} | R${s['preco']:.2f} | "
                  f"Frete: {'Grátis' if s['frete_gratis'] else 'Pago'} | "
                  f"Rep: {s['reputacao']}")
