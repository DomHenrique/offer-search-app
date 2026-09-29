/**
 * Offer Search App - In-Page Stock & Catalog Intel (Content Script)
 * Assistente de Inteligência de Catálogo, BuyBox, Estoque e Fluxo "Vender Igual"
 * direto nas páginas de busca e produto do Mercado Livre e Amazon.
 */

(function () {
  'use strict';

  // Evita múltiplas inicializações
  if (window.__OFFER_SEARCH_INTEL_INITIALIZED__) return;
  window.__OFFER_SEARCH_INTEL_INITIALIZED__ = true;

  const DEFAULT_API_URL = 'https://offer-search.hnperformancedigital.com.br';
  let cachedApiUrl = null;
  let shadowRoot = null;
  let currentIntelData = null;
  let currentProductInfo = null;
  let isCardOpen = false;
  let selectedSkuForLinking = null;
  let simulatedPriceValue = null;
  let isScanningSearchPage = false;
  let isOnlyCatalogsFilterActive = false;

  // ─── 1. Utilitários Gerais ─────────────────────────────────────────
  async function getApiUrl() {
    if (cachedApiUrl) return cachedApiUrl;
    return new Promise(resolve => {
      chrome.storage.local.get(['apiUrl'], res => {
        cachedApiUrl = (res.apiUrl || DEFAULT_API_URL).replace(/\/+$/, '');
        resolve(cachedApiUrl);
      });
    });
  }

  // Requisição segura através do Background Service Worker para contornar CSP da página
  async function requestApi(endpoint, { method = 'GET', body = null, params = null } = {}, maxRetries = 3) {
    if (!chrome?.runtime?.id) {
      console.info('[Offer Search] Contexto da extensão reiniciado. Por favor recarregue a aba do navegador.');
      return null;
    }

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const responseData = await new Promise((resolve, reject) => {
          try {
            chrome.runtime.sendMessage({
              action: 'API_PROXY',
              endpoint,
              method,
              body,
              params
            }, res => {
              if (chrome.runtime.lastError) {
                return reject(new Error(chrome.runtime.lastError.message));
              }
              if (!res) {
                return reject(new Error('Nenhuma resposta do Background Service Worker'));
              }
              if (!res.success) {
                return reject(new Error(res.error || `HTTP ${res.status}`));
              }
              resolve(res.data);
            });
          } catch (sendErr) {
            reject(sendErr);
          }
        });
        return responseData;
      } catch (err) {
        const msg = err.message || '';
        const isContextInvalidated = msg.includes('Extension context invalidated');
        const isConnError = msg.includes('Could not establish connection') ||
                            msg.includes('Receiving end does not exist') ||
                            msg.includes('The message port closed');

        if (isContextInvalidated) {
          console.info('[Offer Search] Extensão recarregada. Recarregue esta página para reativar.');
          return null;
        }

        // Se for erro de conexão/wake-up do Service Worker e ainda houver tentativas
        if (isConnError && attempt < maxRetries) {
          await new Promise(r => setTimeout(r, attempt * 300));
          continue;
        }

        throw err;
      }
    }
  }

  function formatMoney(val) {
    return (parseFloat(val) || 0.0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  function calculateMarginLocal(cost, sellPrice, feePct = 0.16) {
    cost = parseFloat(cost || 0.0);
    sellPrice = parseFloat(sellPrice || 0.0);
    let fixedFee = 0.0;
    if (sellPrice > 0 && sellPrice < 79.0) {
      fixedFee = 6.0;
    }
    if (sellPrice <= 0) {
      return { net_profit: 0.0, margin_pct: 0.0, marketplace_fee: 0.0, status_label: 'Sem Preço', status_color: '#94a3b8' };
    }
    const fee = Math.round(((sellPrice * feePct) + fixedFee) * 100) / 100;
    const profit = Math.round((sellPrice - fee - cost) * 100) / 100;
    const pct = sellPrice > 0 ? Math.round((profit / sellPrice) * 1000) / 10 : 0.0;

    let status_label = '🟢 Lucrativo';
    let status_color = '#22c55e';
    if (cost <= 0) {
      status_label = 'Custo Não Cadastrado';
      status_color = '#64748b';
    } else if (profit > 0 && pct >= 15.0) {
      status_label = '🔥 Alta Margem de Lucro';
      status_color = '#10b981';
    } else if (profit === 0) {
      status_label = '⚪ Empate (Zero Lucro)';
      status_color = '#f59e0b';
    } else if (profit < 0) {
      status_label = '🔴 Abaixo do Custo / Prejuízo';
      status_color = '#ef4444';
    }

    return {
      net_profit: profit,
      margin_pct: pct,
      marketplace_fee: fee,
      status_label,
      status_color
    };
  }

  function buildSellSimilarUrl(catalogId, itemId) {
    const params = [];
    if (itemId) {
      params.push(`itemId=${encodeURIComponent(String(itemId).replace('-', '').trim())}`);
    }
    if (catalogId) {
      params.push(`productId=${encodeURIComponent(String(catalogId).trim())}`);
    }
    if (!params.length) return '';
    return `https://www.mercadolivre.com.br/syi/core/list/equals?${params.join('&')}`;
  }

  // ─── 2. Detecção e Extração de Página de Busca (Listing / Grid) ────
  function isSearchPage() {
    const href = window.location.href;

    // Se for PDP individual com botão de compra evidente, não trata como busca
    const isPdp = Boolean(
      document.querySelector('.ui-pdp-container, #ui-pdp-main-container, .ui-pdp-buybox, button[id*="bid-action-buy"]')
    );
    if (isPdp && !href.includes('/p/MLB') && document.querySelector('.ui-pdp-title')) {
      return false;
    }

    // 1. URLs padrão de busca e listagem
    if (
      href.includes('lista.mercadolivre.com.br') ||
      href.includes('mercadolivre.com.br/c/') ||
      href.includes('/c/') ||
      href.includes('/ofertas') ||
      href.includes('as_word=') ||
      href.includes('_Desde_') ||
      href.includes('_DisplayType_') ||
      href.includes('search_layout=') ||
      href.includes('/search')
    ) {
      return true;
    }

    // 2. Elementos característicos de busca no DOM
    if (
      document.querySelector(
        '.ui-search-layout, .ui-search-results, .ui-search-main, .ui-search-sidebar, .poly-card, .ui-search-sort-filter, .ui-search-search-result, .ui-search-breadcrumb'
      ) ||
      document.querySelectorAll('li.ui-search-layout__item, .poly-card, div.ui-search-result__wrapper, [data-component="poly-card"]').length > 0
    ) {
      return true;
    }

    // 3. Fallback: Se houver input de busca preenchido ou contador de resultados na tela
    const resultCountEl = document.querySelector('.ui-search-search-result__quantity-results, .ui-search-breadcrumb__title');
    if (resultCountEl) {
      return true;
    }

    const priceCount = document.querySelectorAll('.andes-money-amount__fraction, .poly-price__current, .price-tag-fraction').length;
    const mlbLinks = document.querySelectorAll('a[href*="MLB"]').length;
    if (priceCount >= 2 && mlbLinks >= 2 && !isPdp) {
      return true;
    }

    return false;
  }

  function extractSearchCards() {
    const cardSelectors = [
      'li.ui-search-layout__item',
      'div.ui-search-layout__item',
      'div.poly-card',
      'section.poly-card',
      '.poly-card--grid',
      '.poly-card--stack',
      '.poly-component',
      'div.ui-search-result__wrapper',
      'div.ui-search-result',
      '.ui-search-item',
      '[data-component="poly-card"]'
    ];

    const rawElements = [];
    document.querySelectorAll(cardSelectors.join(', ')).forEach(el => {
      if (el.closest('.os-inpage-card-overlay')) return;
      rawElements.push(el);
    });

    // Remove elementos pais se o elemento filho já estiver na lista (ex: li que envolve poly-card)
    const cards = rawElements.filter(el => {
      return !rawElements.some(other => other !== el && el.contains(other));
    });

    const extractedItems = [];

    cards.forEach((card, index) => {
      let cardId = card.getAttribute('data-os-card-id');
      if (!cardId) {
        cardId = `os-card-${index}-${Date.now().toString(36)}`;
        card.setAttribute('data-os-card-id', cardId);
      }

      // Varre links do card para achar /p/MLB ou wid=MLB ou MLB-
      const allLinks = Array.from(card.querySelectorAll('a'));
      if (card.tagName.toLowerCase() === 'a') {
        allLinks.push(card);
      }

      let catalogId = null;
      let itemId = null;
      let productUrl = '';

      allLinks.forEach(a => {
        const href = a.href || a.getAttribute('href') || '';
        if (!href) return;
        const pMatch = href.match(/\/p\/(MLB\d+)/i);
        if (pMatch && !catalogId) {
          catalogId = pMatch[1].toUpperCase();
          productUrl = href;
        }
        const widMatch = href.match(/wid=(MLB\d+)/i);
        if (widMatch && !catalogId) {
          catalogId = widMatch[1].toUpperCase();
          productUrl = `https://www.mercadolivre.com.br/p/${catalogId}`;
        }
        const itMatch = href.match(/(MLB-?\d+)/i);
        if (itMatch && !itemId) {
          itemId = itMatch[1].replace('-', '').toUpperCase();
          if (!productUrl) productUrl = href;
        }
      });

      // Extrai título
      const titleEl = card.querySelector('.poly-component__title, .ui-search-item__title, a.poly-component__title, h2, h3, a[title]');
      const title = titleEl ? (titleEl.textContent || titleEl.getAttribute('title') || '').trim() : '';

      // Extrai preço
      let price = 0.0;
      const priceFraction = card.querySelector('.andes-money-amount__fraction, .poly-price__current .andes-money-amount__fraction, .price-tag-fraction');
      if (priceFraction) {
        const whole = priceFraction.textContent.replace(/\./g, '').trim();
        const centsEl = card.querySelector('.andes-money-amount__cents, .poly-price__current .andes-money-amount__cents, .price-tag-cents');
        const cents = centsEl ? centsEl.textContent.trim() : '00';
        price = parseFloat(`${whole}.${cents}`) || 0.0;
      }

      // Extrai elemento 'Outras opções de compra' e quantidade de vendedores
      let hasOtherSellers = false;
      let sellersCount = 1;

      // 1. Inspeciona texto de todo o card procurando padrões de vendedores / opções
      const cardText = (card.innerText || card.textContent || '').replace(/\s+/g, ' ');
      const optMatch = cardText.match(/(?:ver\s+)?(\d+)\s+opç(?:õ|o)es\s+a\s+partir\s+de/i);
      if (optMatch) {
        hasOtherSellers = true;
        sellersCount = parseInt(optMatch[1], 10);
      } else {
        const vendMatch = cardText.match(/(\d+)\s+vendedores(?:\s+a\s+partir\s+de)?/i) ||
                          cardText.match(/dispon[íi]vel\s+em\s+(\d+)\s+vendedores/i);
        if (vendMatch) {
          hasOtherSellers = true;
          sellersCount = parseInt(vendMatch[1], 10);
        } else if (/outras\s+opç(?:õ|o)es\s+de\s+compra/i.test(cardText)) {
          hasOtherSellers = true;
          const anyOpt = cardText.match(/(\d+)\s+opç(?:õ|o)es/i);
          sellersCount = anyOpt ? parseInt(anyOpt[1], 10) : 2;
        } else {
          const maisOpt = cardText.match(/(?:mais|outras)\s+(\d+)\s+opç(?:õ|o)es/i);
          if (maisOpt) {
            hasOtherSellers = true;
            sellersCount = parseInt(maisOpt[1], 10);
          }
        }
      }

      // 2. Inspeciona links específicos ou seletores do Mercado Livre
      allLinks.forEach(a => {
        const aText = (a.textContent || '').trim().toLowerCase();
        const aOpt = aText.match(/(?:ver\s+)?(\d+)\s+opç(?:õ|o)es/i);
        if (aOpt) {
          hasOtherSellers = true;
          const c = parseInt(aOpt[1], 10);
          if (c > sellersCount) sellersCount = c;
        }
        if (aText.includes('outras opções de compra')) {
          hasOtherSellers = true;
        }
      });

      // 3. Seletores DOM auxiliares do ML para outros vendedores
      if (!hasOtherSellers) {
        const otherEl = card.querySelector(
          '.poly-component__sellers, .ui-search-item__group__element--sellers, .ui-search-item__options, .poly-sellers, .poly-component__other-sellers'
        );
        if (otherEl) {
          hasOtherSellers = true;
          const elText = (otherEl.textContent || '').trim();
          const m = elText.match(/(\d+)/);
          sellersCount = m ? parseInt(m[1], 10) : 2;
        }
      }

      // Regra de negócio estrita: se não tem 'Outras opções de compra' (ou sellers <= 1), não é catálogo para disputa!
      if (!hasOtherSellers || sellersCount <= 1) {
        catalogId = null;
      }

      extractedItems.push({
        id: cardId,
        cardElement: card,
        catalog_id: catalogId,
        item_id: itemId,
        title,
        price,
        url: productUrl,
        has_other_sellers: hasOtherSellers,
        sellers_count: sellersCount
      });
    });

    return extractedItems;
  }

  let searchScanAttempts = 0;
  function triggerSearchScan() {
    if (!isSearchPage()) return;
    if (isScanningSearchPage) return;

    const cardsData = extractSearchCards();
    if (cardsData.length > 0) {
      if (!document.getElementById('os-search-summary-bar')) {
        renderSearchSummaryBar({
          total_scanned: cardsData.length,
          total_catalogs: '...',
          total_in_stock: '...',
          isLoading: true
        });
      }
      scanAndInjectSearchPage();
    } else if (searchScanAttempts < 6) {
      searchScanAttempts++;
      setTimeout(triggerSearchScan, 400);
    }
  }

  async function scanAndInjectSearchPage() {
    if (isScanningSearchPage) return;
    const cardsData = extractSearchCards();
    if (cardsData.length === 0) return;

    isScanningSearchPage = true;

    // Prepara payload compacto para o backend
    const payloadItems = cardsData.map(c => ({
      id: c.id,
      catalog_id: c.catalog_id,
      item_id: c.item_id,
      title: c.title,
      price: c.price,
      url: c.url,
      has_other_sellers: c.has_other_sellers,
      sellers_count: c.sellers_count
    }));

    try {
      const scanResult = await requestApi('/api/extension/scan-search-page', {
        method: 'POST',
        body: { items: payloadItems }
      });

      if (!scanResult || !scanResult.results) {
        isScanningSearchPage = false;
        return;
      }

      // Renderiza barra de resumo no topo da busca
      renderSearchSummaryBar(scanResult);

      // Injeta overlays nos cards
      cardsData.forEach(cardItem => {
        const itemResult = scanResult.results[cardItem.id];
        if (itemResult) {
          injectCardIntelOverlay(cardItem.cardElement, itemResult, cardItem);
        }
      });

    } catch (err) {
      console.warn('[Offer Search] Erro ao escanear página de busca:', err.message);
    } finally {
      isScanningSearchPage = false;
    }
  }

  function injectCardIntelOverlay(cardEl, data, cardInfo) {
    let overlay = cardEl.querySelector('.os-inpage-card-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'os-inpage-card-overlay';

      // Posiciona preferencialmente no conteúdo do card
      const targetContainer = cardEl.querySelector(
        '.poly-card__content, .poly-component__content, .ui-search-result__content, .ui-search-result__content-wrapper'
      ) || cardEl;
      targetContainer.appendChild(overlay);
    }

    // Regra estrita: só é catálogo se possuir o elemento de Outras opções de compra
    const hasOtherSellers = Boolean(
      (data && data.has_other_sellers) ||
      (cardInfo && cardInfo.has_other_sellers) ||
      (data && data.sellers_count > 1) ||
      (cardInfo && cardInfo.sellers_count > 1)
    );
    const sellersCount = (data && data.sellers_count) || (cardInfo && cardInfo.sellers_count) || (hasOtherSellers ? 2 : 1);
    const isCatalog = Boolean(data.is_catalog && data.catalog_id && hasOtherSellers);
    const isLinked = Boolean(data.is_linked);
    const hasStockMatch = Boolean(data.has_stock_match && data.match);
    const match = data.match || (isLinked ? data : null);

    // Ajusta classes do card para destaque e filtros
    if (isCatalog) {
      cardEl.classList.add('os-highlight-catalog-card');
      cardEl.classList.remove('os-card-non-catalog');
      overlay.classList.add('is-catalog');
    } else {
      cardEl.classList.remove('os-highlight-catalog-card');
      cardEl.classList.add('os-card-non-catalog');
      overlay.classList.remove('is-catalog');
    }

    if (match) {
      overlay.classList.add('is-match');
    } else {
      overlay.classList.remove('is-match');
    }

    // Monta conteúdo HTML do overlay
    let html = `
      <div class="os-card-badge-row">
    `;

    if (isCatalog) {
      html += `
        <span class="os-card-badge catalog">
          🏷️ Catálogo: ${data.catalog_id}
        </span>
        <span class="os-card-badge sellers-count" title="${sellersCount} vendedores disputando este catálogo">
          👥 ${sellersCount} vendedores
        </span>
      `;
    } else {
      html += `
        <span class="os-card-badge non-catalog">
          ⚪ Vendedor Único (Sem BuyBox)
        </span>
      `;
    }

    if (match) {
      html += `
        <span class="os-card-badge stock-match">
          ${isLinked ? '🟢 Vinculado' : (match.match_badge || '⭐ Match de Estoque')}
        </span>
      `;
    }

    html += `</div>`;

    if (match) {
      html += `
        <div style="font-weight:800; font-size:11px; color:#0f172a; margin-bottom:4px;">
          SKU: ${match.sku}
        </div>
        <div class="os-card-stock-grid">
          <div>Estoque: <strong>${match.estoque_total} UN</strong></div>
          <div>Custo: <strong>${formatMoney(match.preco_custo)}</strong></div>
          <div>Margem: <strong style="color:${match.margin ? match.margin.status_color : '#10b981'}">${match.margin ? match.margin.margin_pct : 0}%</strong></div>
          <div>Lucro: <strong style="color:${match.margin ? match.margin.status_color : '#10b981'}">${match.margin ? formatMoney(match.margin.net_profit) : 'R$ 0'}</strong></div>
        </div>
      `;
    }

    // Botão Vender Igual: SOMENTE SE FOR CATÁLOGO COM ELEMENTO DE OUTRAS OPÇÕES DE COMPRA
    if (isCatalog) {
      const cardSellSimilarUrl = (data && data.sell_similar_url) || buildSellSimilarUrl(data.catalog_id, cardInfo.item_id);
      if (cardSellSimilarUrl) {
        html += `
          <a href="${cardSellSimilarUrl}" target="_blank" class="os-card-btn-action sell-similar" title="Abrir criação de anúncio no Mercado Livre para este catálogo">
            <span>🚀 Vender Igual</span>
          </a>
        `;
      }
    }

    overlay.innerHTML = html;
  }

  function renderSearchSummaryBar(summaryData) {
    let summaryBar = document.getElementById('os-search-summary-bar');
    if (!summaryBar) {
      summaryBar = document.createElement('div');
      summaryBar.id = 'os-search-summary-bar';
      summaryBar.className = 'os-search-summary-bar';

      // Posiciona preferencialmente antes do #root-app ou logo após o nav-header
      const navHeader = document.querySelector('header.nav-header, .nav-header');
      const rootApp = document.getElementById('root-app') || document.querySelector('main');
      const searchMain = document.querySelector('.ui-search-main, .ui-search-layout, .ui-search');

      if (rootApp && rootApp.parentNode) {
        rootApp.parentNode.insertBefore(summaryBar, rootApp);
      } else if (navHeader && navHeader.parentNode) {
        navHeader.parentNode.insertBefore(summaryBar, navHeader.nextSibling);
      } else if (searchMain && searchMain.parentNode) {
        searchMain.parentNode.insertBefore(summaryBar, searchMain);
      } else {
        document.body.prepend(summaryBar);
      }
    }

    if (summaryData && summaryData.isLoading) {
      summaryBar.innerHTML = `
        <div class="os-summary-left">
          <div class="os-summary-logo">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fde047" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
            </svg>
            <span>Offer Search Intel</span>
          </div>
          <div class="os-summary-metrics">
            <div class="os-summary-pill highlight">
              <span class="os-spinner" style="width:12px; height:12px; border-width:2px; border-color:rgba(255,255,255,0.3); border-top-color:#fde047;"></span>
              <span>Analisando oportunidades de catálogo e estoque na página...</span>
            </div>
          </div>
        </div>
      `;
      return;
    }

    summaryBar.innerHTML = `
      <div class="os-summary-left">
        <div class="os-summary-logo">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fde047" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
          </svg>
          <span>Offer Search Intel</span>
        </div>
        <div class="os-summary-metrics">
          <div class="os-summary-pill">
            <span>📄</span>
            <span><strong>${summaryData.total_scanned}</strong> Anúncios</span>
          </div>
          <div class="os-summary-pill highlight">
            <span>🏷️</span>
            <span><strong>${summaryData.total_catalogs}</strong> em Catálogo</span>
          </div>
          <div class="os-summary-pill success">
            <span>📦</span>
            <span><strong>${summaryData.total_in_stock}</strong> no seu Estoque</span>
          </div>
        </div>
      </div>
      <div class="os-summary-actions">
        <button class="os-filter-toggle-btn ${isOnlyCatalogsFilterActive ? 'active' : ''}" id="osBtnFilterCatalogs">
          <span>${isOnlyCatalogsFilterActive ? '👁️ Mostrar Todos' : '👁️ Apenas Catálogos'}</span>
        </button>
      </div>
    `;

    // Handler do filtro "Apenas Catálogos"
    const filterBtn = summaryBar.querySelector('#osBtnFilterCatalogs');
    if (filterBtn) {
      filterBtn.addEventListener('click', () => {
        isOnlyCatalogsFilterActive = !isOnlyCatalogsFilterActive;
        document.body.classList.toggle('os-only-catalogs-enabled', isOnlyCatalogsFilterActive);
        filterBtn.classList.toggle('active', isOnlyCatalogsFilterActive);
        filterBtn.querySelector('span').textContent = isOnlyCatalogsFilterActive ? '👁️ Mostrar Todos' : '👁️ Apenas Catálogos';
      });
    }
  }

  // ─── 3. Extrator de PDP (Página Individual de Produto) ────────────
  function extractProductInfo() {
    const href = window.location.href;
    const isMeli = href.includes('mercadolivre.com') || href.includes('mercadolibre.com');
    const isAmazon = href.includes('amazon.com');
    const marketplace = isMeli ? 'mercadolivre' : (isAmazon ? 'amazon' : 'outro');

    let catalogId = null;
    let itemId = null;

    // Detecta /p/MLB12345678 (Catálogo Oficial do Mercado Livre)
    const pMatch = href.match(/\/p\/(MLB\d+)/i);
    if (pMatch) {
      catalogId = pMatch[1].toUpperCase();
    }

    // Procura por canonical link caso seja página de variação ou anúncio concorrendo em catálogo
    if (!catalogId) {
      const canonical = document.querySelector('link[rel="canonical"]');
      if (canonical && canonical.href) {
        const canMatch = canonical.href.match(/\/p\/(MLB\d+)/i);
        if (canMatch) catalogId = canMatch[1].toUpperCase();
      }
    }

    // Detecta item MLB / MLB-123456789
    const itemMatch = href.match(/(MLB-?\d+)/i);
    if (itemMatch && !catalogId) {
      itemId = itemMatch[1].replace('-', '').toUpperCase();
    }

    // Detecta Amazon ASIN (/dp/B0... ou /gp/product/B0...)
    const asinMatch = href.match(/\/(?:dp|product)\/([A-Z0-9]{10})/i);
    if (asinMatch) {
      itemId = asinMatch[1].toUpperCase();
    }

    // Detecta se a página possui o elemento 'Outras opções de compra' (Disputa real de BuyBox)
    let hasOtherSellers = false;
    let sellersCount = 1;

    // 1. Procura bloco característico do Mercado Livre (.ui-pdp-other-sellers, etc.)
    const otherSellersContainer = document.querySelector(
      '.ui-pdp-other-sellers, .ui-pdp-buybox__other-sellers, #other-sellers, .ui-pdp-container__other-sellers'
    );
    if (otherSellersContainer) {
      hasOtherSellers = true;
      const text = otherSellersContainer.innerText || otherSellersContainer.textContent || '';
      const m = text.match(/(?:ver\s+)?(\d+)\s+opç(?:õ|o)es/i) || text.match(/(\d+)\s+vendedores/i);
      sellersCount = m ? parseInt(m[1], 10) : 2;
    }

    // 2. Busca por links que contenham "opções a partir de" ou títulos "Outras opções de compra"
    if (!hasOtherSellers) {
      const candidateElements = Array.from(document.querySelectorAll('a, h2, h3, div, span, p'));
      for (const el of candidateElements) {
        const text = (el.textContent || '').trim().replace(/\s+/g, ' ');
        const optMatch = text.match(/(?:ver\s+)?(\d+)\s+opç(?:õ|o)es\s+a\s+partir\s+de/i);
        if (optMatch) {
          hasOtherSellers = true;
          sellersCount = parseInt(optMatch[1], 10);
          break;
        }
        if (/outras\s+opç(?:õ|o)es\s+de\s+compra/i.test(text)) {
          hasOtherSellers = true;
          const anyOpt = text.match(/(\d+)\s+opç/i);
          sellersCount = anyOpt ? parseInt(anyOpt[1], 10) : 2;
          break;
        }
      }
    }

    // 3. Suporte Amazon (Buybox / All offers)
    if (!hasOtherSellers && isAmazon) {
      const amzOther = document.querySelector('#olp_feature_div, #all-offers-display, #dynamic-aod-ingress-box');
      if (amzOther) {
        hasOtherSellers = true;
        const m = (amzOther.textContent || '').match(/(\d+)/);
        sellersCount = m ? parseInt(m[1], 10) : 2;
      }
    }

    // Regra estrita do usuário:
    // "os produtos que não tem esse elemento 'Outras opções de compra' não sao produtos de catalogo, pode retirar o botao de vender igual e numero de catalogo"
    const isCatalog = Boolean(hasOtherSellers && sellersCount > 1);
    if (!isCatalog) {
      catalogId = null;
      nativeSellSimilarUrl = '';
    }

    // Extrai Preço visível na tela
    let price = 0.0;
    const priceEl = document.querySelector('.ui-pdp-price__second-line .andes-money-amount__fraction') ||
                    document.querySelector('.price-tag-fraction') ||
                    document.querySelector('.a-price .a-price-whole');
    if (priceEl) {
      const priceCentsEl = document.querySelector('.ui-pdp-price__second-line .andes-money-amount__cents') ||
                           document.querySelector('.price-tag-cents') ||
                           document.querySelector('.a-price .a-price-fraction');
      const whole = priceEl.textContent.replace(/\./g, '').trim();
      const cents = priceCentsEl ? priceCentsEl.textContent.trim() : '00';
      price = parseFloat(`${whole}.${cents}`) || 0.0;
    }

    // Extrai Título
    const titleEl = document.querySelector('.ui-pdp-title') || document.querySelector('#productTitle') || document.querySelector('h1');
    const title = titleEl ? titleEl.textContent.trim() : document.title;

    // Extrai Imagem Principal
    const imgEl = document.querySelector('.ui-pdp-gallery__figure img') || document.querySelector('#landingImage') || document.querySelector('meta[property="og:image"]');
    const image = imgEl ? (imgEl.src || imgEl.getAttribute('content') || '') : '';

    // Extrai Atributos Técnicos (Marca, Modelo, EAN/GTIN)
    let brand = '';
    let model = '';
    let gtin = '';

    const specRows = document.querySelectorAll('.ui-pdp-specs__table tr, .andes-table__row, #productOverview_feature_div tr, table.a-normal tr');
    specRows.forEach(row => {
      const th = (row.querySelector('th') || {}).textContent || '';
      const td = (row.querySelector('td') || {}).textContent || '';
      const label = th.trim().toLowerCase();
      const val = td.trim();
      if (!brand && (label.includes('marca') || label === 'brand')) brand = val;
      if (!model && (label.includes('modelo') || label.includes('linha') || label === 'model')) model = val;
      if (!gtin && (label.includes('universal') || label.includes('gtin') || label.includes('ean') || label.includes('código'))) gtin = val;
    });

    // Fallback: Busca em scripts JSON-LD estruturados
    try {
      const jsonLds = document.querySelectorAll('script[type="application/ld+json"]');
      for (const s of jsonLds) {
        const parsed = JSON.parse(s.textContent);
        const pObj = Array.isArray(parsed) ? parsed.find(d => d && d['@type'] === 'Product') : (parsed && parsed['@type'] === 'Product' ? parsed : null);
        if (pObj) {
          if (!brand && pObj.brand) brand = typeof pObj.brand === 'string' ? pObj.brand : (pObj.brand.name || '');
          if (!model && pObj.model) model = pObj.model;
          if (!gtin) gtin = pObj.gtin || pObj.gtin13 || pObj.gtin12 || pObj.gtin8 || '';
        }
      }
    } catch (e) {}

    // Extrai Vendedor Vencedor da BuyBox
    let buyboxWinner = '';
    const sellerEl = document.querySelector('.ui-pdp-seller__link-trigger') ||
                     document.querySelector('.ui-seller-info .ui-pdp-color--BLUE') ||
                     document.querySelector('.ui-pdp-seller__header a') ||
                     document.querySelector('#sellerProfileTriggerId');
    if (sellerEl) {
      buyboxWinner = sellerEl.textContent.trim();
    }

    // Extrai Link Nativo 'Vender um igual' diretamente do DOM se existir na página (Prioridade Máxima)
    let nativeSellSimilarUrl = '';
    const syiLinkEl = document.querySelector('a[href*="/syi/core/list/equals"]') ||
                      document.querySelector('.ui-pdp-syi a, a.ui-pdp-syi__link');
    if (syiLinkEl && syiLinkEl.href) {
      nativeSellSimilarUrl = syiLinkEl.href;
    } else {
      // Busca resiliente por qualquer link cujo texto contenha "vender um igual" (conforme orientação do usuário)
      const allCandidateLinks = document.querySelectorAll('a');
      for (const a of allCandidateLinks) {
        const text = (a.textContent || '').trim().toLowerCase();
        if (text.includes('vender um igual') && a.href) {
          nativeSellSimilarUrl = a.href;
          break;
        }
      }
    }

    // Se encontramos o link nativo do SYI, extraímos com precisão itemId e productId
    if (nativeSellSimilarUrl) {
      try {
        const parsedUrl = new URL(nativeSellSimilarUrl);
        const pId = parsedUrl.searchParams.get('productId');
        const iId = parsedUrl.searchParams.get('itemId');
        if (pId && !catalogId && isCatalog) catalogId = pId.toUpperCase();
        if (iId && !itemId) itemId = iId.toUpperCase();
      } catch (e) {}
    }

    return {
      catalogId: isCatalog ? catalogId : null,
      itemId,
      isCatalog,
      hasOtherSellers,
      sellersCount,
      nativeSellSimilarUrl: isCatalog ? nativeSellSimilarUrl : '',
      title,
      brand,
      model,
      gtin,
      price,
      image,
      buyboxWinner,
      marketplace,
      url: href
    };
  }

  async function fetchProductIntel(info) {
    const params = {
      catalog_id: info.catalogId || '',
      item_id: info.itemId || '',
      title: info.title || '',
      brand: info.brand || '',
      model: info.model || '',
      gtin: info.gtin || '',
      current_price: info.price || '',
      marketplace: info.marketplace || 'mercadolivre',
      url: info.url
    };

    try {
      return await requestApi('/api/extension/product-intel', {
        method: 'GET',
        params
      });
    } catch (err) {
      console.warn('[Offer Search Intel] Erro ao consultar backend:', err.message);
      return null;
    }
  }

  async function fetchInventoryList(queryStr = '') {
    try {
      const data = await requestApi('/api/extension/inventory-list', {
        method: 'GET',
        params: { q: queryStr }
      });
      return data.items || [];
    } catch (err) {
      return [];
    }
  }

  async function sendLinkSku(catalogId, sku, productInfo) {
    const payload = {
      catalog_id: catalogId,
      sku: sku,
      catalog_title: productInfo.title,
      catalog_url: productInfo.url,
      catalog_image: productInfo.image,
      buybox_min_price: productInfo.price,
      buybox_winner: productInfo.buyboxWinner
    };

    return await requestApi('/api/extension/link-sku', {
      method: 'POST',
      body: payload
    });
  }

  // ─── 4. Injeção e Construção do Shadow DOM (Widget PDP) ────────────
  function setupShadowRoot() {
    let host = document.getElementById('offer-search-root');
    if (!host) {
      host = document.createElement('div');
      host.id = 'offer-search-root';
      document.body.appendChild(host);
    }

    if (!shadowRoot) {
      shadowRoot = host.attachShadow({ mode: 'open' });
      const cssUrl = chrome.runtime.getURL('content.css');
      shadowRoot.innerHTML = `
        <link rel="stylesheet" href="${cssUrl}">
        <div id="os-widget-wrapper"></div>
      `;
    }
    return shadowRoot.getElementById('os-widget-wrapper');
  }

  function renderWidget(info, intel) {
    const container = setupShadowRoot();
    if (!container) return;

    currentIntelData = intel;
    currentProductInfo = info;

    const isLinked = Boolean(intel && intel.is_linked);
    const sku = isLinked ? intel.sku : null;
    const bestMatch = intel ? intel.best_match : null;

    const baseBuyboxPrice = (intel && intel.buybox_min_price) ? intel.buybox_min_price : (info.price || 0.0);
    if (simulatedPriceValue === null || simulatedPriceValue === undefined) {
      simulatedPriceValue = baseBuyboxPrice;
    }

    const currentCost = isLinked ? intel.preco_custo : (bestMatch ? bestMatch.preco_custo : 0.0);
    const activeMargin = calculateMarginLocal(currentCost, simulatedPriceValue);

    const fallbackSellSimilar = buildSellSimilarUrl(info.catalogId, info.itemId);
    const sellSimilarUrl = (info.isCatalog && (info.hasOtherSellers || info.nativeSellSimilarUrl))
      ? (info.nativeSellSimilarUrl || (intel && intel.sell_similar_url) || fallbackSellSimilar)
      : '';

    let fabBadgeText = 'Vendedor Único';
    let fabBadgeClass = 'unlinked';
    if (isLinked) {
      fabBadgeText = `SKU: ${sku}`;
      fabBadgeClass = 'linked';
    } else if (bestMatch && bestMatch.match_score >= 50) {
      fabBadgeText = `⭐ Match: ${bestMatch.sku}`;
      fabBadgeClass = 'linked';
    } else if (info.isCatalog) {
      fabBadgeText = `Catálogo (${info.sellersCount} vend.)`;
      fabBadgeClass = 'unlinked';
    }

    container.innerHTML = `
      <!-- Trigger Flutuante (FAB) -->
      ${!isCardOpen ? `
        <div class="os-fab-btn" id="osTriggerBtn" title="Abrir Inteligência de Catálogo e Estoque">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
            <line x1="12" y1="22.08" x2="12" y2="12"></line>
          </svg>
          <span>Offer Search Intel</span>
          <span class="os-fab-badge ${fabBadgeClass}">${fabBadgeText}</span>
        </div>
      ` : `
        <!-- Card Completo de Inteligência -->
        <div class="os-card" id="osCard">
          <div class="os-card-header">
            <div class="os-card-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fde047" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
              </svg>
              <span>Inteligência de Catálogo & BuyBox</span>
            </div>
            <div class="os-card-actions">
              <button class="os-icon-btn" id="osBtnMinimize" title="Minimizar">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
          </div>

          <div class="os-card-body">
            ${!intel ? `
              <div style="background:#fee2e2; border:1px solid #fca5a5; color:#991b1b; padding:12px; border-radius:10px; font-size:11px; margin-bottom:12px;">
                <strong>⚠️ Falha de comunicação com o Offer Search App</strong>
                <p style="margin-top:4px; opacity:0.9;">Não foi possível consultar os dados do servidor. Verifique se o servidor está ativo.</p>
                <button class="os-btn-primary" id="osBtnRetry" style="margin-top:10px; background:#ef4444;">
                  <span>🔄 Tentar Novamente</span>
                </button>
              </div>
            ` : `
              <!-- Banner de Tipo de Página (Catálogo vs Anúncio Simples) -->
              <div style="display:flex; justify-content:space-between; align-items:center; background:#f1f5f9; padding:8px 10px; border-radius:8px; font-size:11px; margin-bottom:10px;">
                <span style="display:flex; align-items:center; gap:6px;">
                  <span>${info.isCatalog ? '🏷️' : '📄'}</span>
                  <strong>${info.isCatalog ? 'Anúncio de Catálogo Oficial' : 'Anúncio Convencional (Sem BuyBox)'}</strong>
                  ${info.isCatalog && info.sellersCount > 1 ? `<span class="os-card-badge sellers-count" style="margin-left:4px;">👥 ${info.sellersCount} vendedores</span>` : ''}
                </span>
                <span style="color:#64748b; font-weight:700;">${info.isCatalog && info.catalogId ? `ID: ${info.catalogId}` : (info.itemId ? `Item: ${info.itemId}` : '')}</span>
              </div>

              <!-- Status de Vínculo com Estoque -->
              <div class="os-status-banner ${isLinked ? 'linked' : 'unlinked'}">
                <div>
                  <strong>${isLinked ? `🟢 Vinculado: ${intel.sku}` : (info.isCatalog ? '⚪ Catálogo Não Vinculado ao Estoque' : '⚪ Anúncio de Vendedor Único')}</strong>
                  <div style="font-size:10px; opacity:0.85; margin-top:2px;">
                    ${isLinked ? (intel.descricao || 'Produto Cadastrado') : (info.isCatalog ? 'Dispute a BuyBox ou vincule ao seu SKU' : 'Anúncio exclusivo sem disputa de outros vendedores')}
                  </div>
                </div>
                ${isLinked ? `<button class="os-icon-btn" id="osBtnChangeSku" title="Alterar SKU" style="background:#065f46; color:#fff;">✏️</button>` : ''}
              </div>
            `}

            ${isLinked ? `
              <!-- Métricas Principais de Estoque -->
              <div class="os-grid-metrics">
                <div class="os-metric-box">
                  <div class="os-metric-label">Estoque Próprio</div>
                  <div class="os-metric-value highlight">${intel.estoque_total} UN</div>
                </div>
                <div class="os-metric-box">
                  <div class="os-metric-label">Custo Unitário</div>
                  <div class="os-metric-value">${formatMoney(intel.preco_custo)}</div>
                </div>
                <div class="os-metric-box">
                  <div class="os-metric-label">Preço Loja / PIX</div>
                  <div class="os-metric-value">${formatMoney(intel.preco_venda)}</div>
                </div>
                <div class="os-metric-box">
                  <div class="os-metric-label">Menor Preço BuyBox</div>
                  <div class="os-metric-value warning">${formatMoney(intel.buybox_min_price || info.price)}</div>
                </div>
              </div>

              <!-- Simulador Interativo de BuyBox e Margem -->
              <div class="os-simulator-container">
                <div class="os-simulator-header">
                  <span>🎯 Simulador de Preço BuyBox</span>
                  <span style="font-size:11px; color:#64748b;">Taxa ML: 16%</span>
                </div>
                <div class="os-sim-input-row">
                  <span style="font-weight:700; color:#475569;">R$</span>
                  <input type="number" step="0.10" class="os-sim-input" id="osSimPriceInput" value="${simulatedPriceValue.toFixed(2)}">
                </div>
                <div class="os-sim-chips">
                  <button class="os-chip-btn" id="osChipUndercut" title="Vencer BuyBox dando 1 centavo de desconto">- R$ 0,01 Vencer</button>
                  <button class="os-chip-btn" id="osChipEqual">Igualar BuyBox</button>
                  <button class="os-chip-btn" id="osChipMarkup10">+ 10% Lucro</button>
                </div>

                <!-- Breakdown de Margem Dinâmica -->
                <div class="os-breakdown" style="margin-bottom:0;">
                  <div class="os-breakdown-row">
                    <span style="color:#64748b;">Preço de Venda Simulado:</span>
                    <strong id="osSimDisplayPrice">${formatMoney(simulatedPriceValue)}</strong>
                  </div>
                  <div class="os-breakdown-row">
                    <span style="color:#64748b;">(-) Custo do Produto:</span>
                    <span style="color:#ef4444;">- ${formatMoney(intel.preco_custo)}</span>
                  </div>
                  <div class="os-breakdown-row">
                    <span style="color:#64748b;">(-) Taxa ML Estimada:</span>
                    <span style="color:#ef4444;" id="osSimDisplayFee">- ${formatMoney(activeMargin.marketplace_fee)}</span>
                  </div>
                  <div class="os-breakdown-row total">
                    <span>Margem Líquida:</span>
                    <span id="osSimDisplayProfit" style="color: ${activeMargin.status_color}; font-size:14px;">
                      ${formatMoney(activeMargin.net_profit)} (${activeMargin.margin_pct}%)
                    </span>
                  </div>
                  <div id="osSimDisplayStatus" style="margin-top: 6px; font-size: 11px; font-weight: 700; color: ${activeMargin.status_color}; text-align: right;">
                    ${activeMargin.status_label}
                  </div>
                </div>
              </div>

              <!-- Botão Vender um Igual (Destaque Principal) -->
              ${sellSimilarUrl ? `
                <a href="${sellSimilarUrl}" target="_blank" class="os-btn-sell-similar" id="osBtnSellSimilar">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"></path>
                    <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"></path>
                    <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"></path>
                    <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"></path>
                  </svg>
                  <span>🚀 Vender um Igual no Mercado Livre</span>
                </a>
              ` : ''}

              <!-- Ações Secundárias -->
              <div class="os-action-row">
                <button class="os-btn-secondary" id="osBtnCopyIntel" title="Copiar SKU, Título e EAN">
                  <span>📋 Copiar Dados</span>
                </button>
                <button class="os-btn-secondary" id="osBtnSwitchSku">
                  <span>🔄 Trocar SKU</span>
                </button>
              </div>
            ` : `
              <!-- Seção para Catálogo Não Vinculado -->
              ${bestMatch ? `
                <!-- Sugestão Inteligente do InventoryMatcher -->
                <div class="os-best-match-card">
                  <div class="os-best-match-header">
                    <span style="font-size:11px; font-weight:700; color:#166534;">🏆 Sugestão Inteligente de Estoque</span>
                    <span class="os-badge-tier high">${bestMatch.match_badge || '⚡ Match Identificado'}</span>
                  </div>
                  <div style="font-size:13px; font-weight:800; color:#0f172a; margin-bottom:2px;">
                    ${bestMatch.sku}
                  </div>
                  <div style="font-size:11px; color:#475569; margin-bottom:8px;">
                    ${bestMatch.descricao}
                  </div>
                  <div style="display:flex; justify-content:space-between; font-size:11px; background:#fff; padding:6px 10px; border-radius:6px; border:1px solid #bbf7d0; margin-bottom:8px;">
                    <span>Estoque: <strong>${bestMatch.estoque_total} UN</strong></span>
                    <span>Custo: <strong>${formatMoney(bestMatch.preco_custo)}</strong></span>
                    <span style="color:${bestMatch.margin.status_color}; font-weight:700;">Margem: ${bestMatch.margin.margin_pct}%</span>
                  </div>
                  <button class="os-btn-primary" id="osBtnQuickLinkBestMatch" style="background: linear-gradient(135deg, #15803d, #16a34a);">
                    <span>🔗 Conectar ao SKU ${bestMatch.sku}</span>
                  </button>
                </div>
              ` : ''}

              <!-- Botão Vender um Igual para Catálogo Descoberto -->
              ${sellSimilarUrl ? `
                <a href="${sellSimilarUrl}" target="_blank" class="os-btn-sell-similar" id="osBtnSellSimilar">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"></path>
                    <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"></path>
                  </svg>
                  <span>🚀 Vender um Igual neste Catálogo</span>
                </a>
              ` : ''}

              <!-- Seção de Busca Manual de SKU -->
              <div class="os-link-section">
                <div class="os-link-title">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                  <span>Ou selecione outro SKU do Estoque:</span>
                </div>
                <input type="text" class="os-input" id="osSkuSearchInput" placeholder="Buscar SKU ou descrição...">
                <div class="os-sku-dropdown" id="osSkuList">
                  ${(intel && intel.suggestions && intel.suggestions.length) ? intel.suggestions.map(s => `
                    <div class="os-sku-item ${selectedSkuForLinking === s.sku ? 'selected' : ''}" data-sku="${s.sku}">
                      <div>
                        <div class="os-sku-code">${s.sku} ${s.match_score ? `<span style="font-size:9px; color:#10b981;">(${s.match_score}%)</span>` : ''}</div>
                        <div class="os-sku-desc">${s.descricao || ''}</div>
                      </div>
                      <div style="text-align:right;">
                        <strong>${s.estoque_total} UN</strong>
                        <div style="font-size:10px; color:#64748b;">${formatMoney(s.preco_custo)}</div>
                      </div>
                    </div>
                  `).join('') : '<div style="padding:10px; text-align:center; color:#64748b; font-size:11px;">Carregando SKUs...</div>'}
                </div>
                <button class="os-btn-primary" id="osBtnSubmitLink" disabled>
                  <span>🔗 Conectar ao SKU Selecionado</span>
                </button>
              </div>
            `}
          </div>

          <div class="os-card-footer">
            <a href="${cachedApiUrl}/catalog?sku=${sku || ''}" target="_blank" class="os-app-link">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
              <span>Abrir no Offer Search App</span>
            </a>
            <span style="color:#94a3b8; font-size:10px;">v1.3</span>
          </div>
        </div>
      `}
    `;

    bindEvents(info, intel);
  }

  // ─── 5. Event Listeners no Shadow DOM (Widget PDP) ────────────────
  function bindEvents(info, intel) {
    const triggerBtn = shadowRoot.getElementById('osTriggerBtn');
    if (triggerBtn) {
      triggerBtn.addEventListener('click', () => {
        isCardOpen = true;
        renderWidget(info, intel);
      });
    }

    const minBtn = shadowRoot.getElementById('osBtnMinimize');
    if (minBtn) {
      minBtn.addEventListener('click', () => {
        isCardOpen = false;
        renderWidget(info, intel);
      });
    }

    const retryBtn = shadowRoot.getElementById('osBtnRetry');
    if (retryBtn) {
      retryBtn.addEventListener('click', async () => {
        retryBtn.disabled = true;
        retryBtn.innerHTML = '<span class="os-spinner"></span> <span>Consultando...</span>';
        const newIntel = await fetchProductIntel(info);
        renderWidget(info, newIntel);
      });
    }

    const changeSkuBtn = shadowRoot.getElementById('osBtnChangeSku') || shadowRoot.getElementById('osBtnSwitchSku');
    if (changeSkuBtn) {
      changeSkuBtn.addEventListener('click', () => {
        if (intel) intel.is_linked = false;
        renderWidget(info, intel);
      });
    }

    const copyBtn = shadowRoot.getElementById('osBtnCopyIntel');
    if (copyBtn) {
      copyBtn.addEventListener('click', async () => {
        const textToCopy = `SKU: ${intel.sku || 'N/A'}\nCatálogo: ${info.catalogId || info.itemId}\nTítulo: ${info.title}\nEAN: ${info.gtin || 'N/A'}\nPreço BuyBox: ${formatMoney(info.price)}`;
        try {
          await navigator.clipboard.writeText(textToCopy);
          copyBtn.innerHTML = '<span>✅ Copiado!</span>';
          setTimeout(() => {
            copyBtn.innerHTML = '<span>📋 Copiar Dados</span>';
          }, 2000);
        } catch (e) {
          alert('Dados copiados:\n\n' + textToCopy);
        }
      });
    }

    const simInput = shadowRoot.getElementById('osSimPriceInput');
    const chipUndercut = shadowRoot.getElementById('osChipUndercut');
    const chipEqual = shadowRoot.getElementById('osChipEqual');
    const chipMarkup = shadowRoot.getElementById('osChipMarkup10');

    function updateSimulation(newPrice) {
      simulatedPriceValue = parseFloat(newPrice) || 0.0;
      const currentCost = (intel && intel.preco_custo) || 0.0;
      const m = calculateMarginLocal(currentCost, simulatedPriceValue);

      const dispPrice = shadowRoot.getElementById('osSimDisplayPrice');
      const dispFee = shadowRoot.getElementById('osSimDisplayFee');
      const dispProfit = shadowRoot.getElementById('osSimDisplayProfit');
      const dispStatus = shadowRoot.getElementById('osSimDisplayStatus');

      if (dispPrice) dispPrice.textContent = formatMoney(simulatedPriceValue);
      if (dispFee) dispFee.textContent = `- ${formatMoney(m.marketplace_fee)}`;
      if (dispProfit) {
        dispProfit.style.color = m.status_color;
        dispProfit.textContent = `${formatMoney(m.net_profit)} (${m.margin_pct}%)`;
      }
      if (dispStatus) {
        dispStatus.style.color = m.status_color;
        dispStatus.textContent = m.status_label;
      }
    }

    if (simInput) {
      simInput.addEventListener('input', () => {
        updateSimulation(simInput.value);
      });
    }

    if (chipUndercut) {
      chipUndercut.addEventListener('click', () => {
        const base = (intel && intel.buybox_min_price) ? intel.buybox_min_price : (info.price || 0.0);
        const val = Math.max(1, base - 0.01);
        if (simInput) simInput.value = val.toFixed(2);
        updateSimulation(val);
      });
    }

    if (chipEqual) {
      chipEqual.addEventListener('click', () => {
        const base = (intel && intel.buybox_min_price) ? intel.buybox_min_price : (info.price || 0.0);
        if (simInput) simInput.value = base.toFixed(2);
        updateSimulation(base);
      });
    }

    if (chipMarkup) {
      chipMarkup.addEventListener('click', () => {
        const cost = (intel && intel.preco_custo) || 0.0;
        const val = cost > 0 ? (cost / 0.69) : ((info.price || 100) * 1.10);
        if (simInput) simInput.value = val.toFixed(2);
        updateSimulation(val);
      });
    }

    const quickLinkBestMatchBtn = shadowRoot.getElementById('osBtnQuickLinkBestMatch');
    if (quickLinkBestMatchBtn && intel && intel.best_match) {
      quickLinkBestMatchBtn.addEventListener('click', async () => {
        const skuToLink = intel.best_match.sku;
        quickLinkBestMatchBtn.disabled = true;
        quickLinkBestMatchBtn.innerHTML = '<span class="os-spinner"></span> <span>Vinculando ao estoque...</span>';

        try {
          const res = await sendLinkSku(info.catalogId || info.itemId, skuToLink, info);
          if (res.success && res.product_intel) {
            currentIntelData = res.product_intel;
            renderWidget(info, res.product_intel);
          } else {
            alert('Erro ao vincular: ' + (res.error || 'Falha na requisição'));
            quickLinkBestMatchBtn.disabled = false;
            quickLinkBestMatchBtn.innerHTML = `<span>🔗 Conectar ao SKU ${skuToLink}</span>`;
          }
        } catch (err) {
          alert('Erro de conexão com o Offer Search App.');
          quickLinkBestMatchBtn.disabled = false;
        }
      });
    }

    const searchInput = shadowRoot.getElementById('osSkuSearchInput');
    const skuList = shadowRoot.getElementById('osSkuList');
    const submitBtn = shadowRoot.getElementById('osBtnSubmitLink');

    if (searchInput && skuList) {
      let debounceTimeout = null;
      searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(async () => {
          const q = searchInput.value.trim();
          skuList.innerHTML = '<div style="padding:10px; text-align:center; color:#64748b; font-size:11px;">Buscando...</div>';
          const items = await fetchInventoryList(q);
          if (!items.length) {
            skuList.innerHTML = '<div style="padding:10px; text-align:center; color:#94a3b8; font-size:11px;">Nenhum SKU encontrado</div>';
            return;
          }
          skuList.innerHTML = items.map(s => `
            <div class="os-sku-item ${selectedSkuForLinking === s.sku ? 'selected' : ''}" data-sku="${s.sku}">
              <div>
                <div class="os-sku-code">${s.sku} ${s.match_score ? `<span style="font-size:9px; color:#10b981;">(${s.match_score}%)</span>` : ''}</div>
                <div class="os-sku-desc">${s.descricao || ''}</div>
              </div>
              <div style="text-align:right;">
                <strong>${s.estoque_total} UN</strong>
                <div style="font-size:10px; color:#64748b;">${formatMoney(s.preco_custo)}</div>
              </div>
            </div>
          `).join('');
          attachSkuItemClicks();
        }, 250);
      });

      function attachSkuItemClicks() {
        shadowRoot.querySelectorAll('.os-sku-item').forEach(item => {
          item.addEventListener('click', () => {
            shadowRoot.querySelectorAll('.os-sku-item').forEach(el => el.classList.remove('selected'));
            item.classList.add('selected');
            selectedSkuForLinking = item.getAttribute('data-sku');
            if (submitBtn) {
              submitBtn.disabled = false;
              submitBtn.innerHTML = `<span>🔗 Conectar a <strong>${selectedSkuForLinking}</strong></span>`;
            }
          });
        });
      }
      attachSkuItemClicks();

      if (submitBtn) {
        submitBtn.addEventListener('click', async () => {
          if (!selectedSkuForLinking) return;
          submitBtn.disabled = true;
          submitBtn.innerHTML = `<span class="os-spinner"></span> <span>Vinculando ao estoque...</span>`;

          try {
            const res = await sendLinkSku(info.catalogId || info.itemId, selectedSkuForLinking, info);
            if (res.success && res.product_intel) {
              currentIntelData = res.product_intel;
              renderWidget(info, res.product_intel);
            } else {
              alert('Erro ao vincular: ' + (res.error || 'Falha na requisição'));
              submitBtn.disabled = false;
              submitBtn.innerHTML = `<span>🔗 Tentar Novamente</span>`;
            }
          } catch (err) {
            alert('Erro de conexão com o Offer Search App.');
            submitBtn.disabled = false;
          }
        });
      }
    }
  }

  // ─── 6. Inicialização Unificada e Observador de Rota/SPA ───────────
  async function init() {
    searchScanAttempts = 0;

    // 1. Se estiver em página de busca do ML, executa a varredura com retries
    if (isSearchPage()) {
      triggerSearchScan();
    }

    // 2. Se for uma página de produto (PDP), inicializa também o widget individual
    const info = extractProductInfo();
    if (info && (info.catalogId || info.itemId)) {
      const intel = await fetchProductIntel(info);
      renderWidget(info, intel);
    }
  }

  // Executa na carga inicial
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Monitora submissão da barra de busca do Mercado Livre
  function setupSearchFormListener() {
    const searchForm = document.querySelector('form.nav-search, form[action*="mercadolivre"]');
    if (searchForm) {
      searchForm.addEventListener('submit', () => {
        searchScanAttempts = 0;
        setTimeout(init, 500);
      });
    }
    const searchInput = document.querySelector('input.nav-search-input, input#cb1-edit');
    if (searchInput) {
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          searchScanAttempts = 0;
          setTimeout(init, 500);
        }
      });
    }
  }
  setupSearchFormListener();

  // Observa mudanças de rota em SPAs e inserções dinâmicas de cards (scroll infinito)
  let lastUrl = location.href;
  let scrollScanTimeout = null;

  const observer = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      searchScanAttempts = 0;
      setTimeout(init, 400);
    } else if (isSearchPage()) {
      clearTimeout(scrollScanTimeout);
      scrollScanTimeout = setTimeout(() => {
        // Varre novos cards inseridos por lazy loading ou renderização tardia
        const unscanned = document.querySelectorAll(
          'li.ui-search-layout__item:not([data-os-card-id]), .poly-card:not([data-os-card-id]), div.ui-search-result__wrapper:not([data-os-card-id])'
        );
        if (unscanned.length > 0) {
          triggerSearchScan();
        }
      }, 400);
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });

})();
