/**
 * Offer Search App - Background Service Worker (Manifest V3)
 * Gerencia a sincronização automática e silenciosa de sessões de marketplaces (ML e Amazon)
 * via Chrome Alarms API, mantendo o backend autenticado sem intervenção manual.
 */

const DEFAULT_API_URL = 'https://offer-search.hnperformancedigital.com.br';
const SYNC_ALARM_NAME = 'offer_search_session_sync_alarm';
const SYNC_PERIOD_MINUTES = 240; // 4 horas

// ─── 1. Inicialização de Alarmes e Ciclo de Vida ───────────────────
chrome.runtime.onInstalled.addListener(async (details) => {
  console.log(`[Offer Search BG] Extensão instalada/atualizada: ${details.reason}`);
  setupPeriodicAlarm();
  // Aguarda 5 segundos antes da primeira sincronização para estabilizar conexões
  setTimeout(() => {
    syncAllSessions('install_or_update');
  }, 5000);
});

chrome.runtime.onStartup.addListener(() => {
  console.log('[Offer Search BG] Navegador inicializado. Verificando alarmes...');
  setupPeriodicAlarm();
  setTimeout(() => {
    syncAllSessions('startup');
  }, 10000);
});

function setupPeriodicAlarm() {
  chrome.alarms.get(SYNC_ALARM_NAME, (alarm) => {
    if (!alarm) {
      chrome.alarms.create(SYNC_ALARM_NAME, {
        periodInMinutes: SYNC_PERIOD_MINUTES,
        delayInMinutes: 2
      });
      console.log(`[Offer Search BG] Alarme periódico '${SYNC_ALARM_NAME}' agendado para cada ${SYNC_PERIOD_MINUTES} minutos.`);
    } else {
      console.log(`[Offer Search BG] Alarme periódico já existente: disparará em ${new Date(alarm.scheduledTime).toLocaleTimeString('pt-BR')}`);
    }
  });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === SYNC_ALARM_NAME) {
    console.log('[Offer Search BG] Disparo de alarme periódico. Iniciando sync de sessões...');
    syncAllSessions('periodic_alarm');
  }
});

// ─── 2. Manipulador de Mensagens (Popup / Content Scripts) ──────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.action) return false;

  if (message.action === 'FORCE_SYNC') {
    syncAllSessions('manual_request').then(result => {
      sendResponse(result);
    }).catch(err => {
      sendResponse({ success: false, error: err.message });
    });
    return true; // Resposta assíncrona
  }

  if (message.action === 'GET_BACKGROUND_STATUS') {
    chrome.storage.local.get(['lastSync', 'lastSyncStatus', 'apiUrl'], (res) => {
      sendResponse({
        apiUrl: res.apiUrl || DEFAULT_API_URL,
        lastSync: res.lastSync || null,
        lastSyncStatus: res.lastSyncStatus || 'idle'
      });
    });
    return true;
  }

  return false;
});

// ─── 3. Motor de Coleta e Sincronização de Cookies ──────────────────
async function getApiUrl() {
  return new Promise(resolve => {
    chrome.storage.local.get(['apiUrl'], res => {
      const url = (res.apiUrl || DEFAULT_API_URL).replace(/\/+$/, '');
      resolve(url);
    });
  });
}

function formatCookies(cookies) {
  return (cookies || []).map(c => ({
    name: c.name,
    value: c.value,
    domain: c.domain,
    path: c.path || '/',
    secure: Boolean(c.secure),
    httpOnly: Boolean(c.httpOnly),
    sameSite: c.sameSite || 'lax'
  }));
}

async function collectMarketplaceCookies(domains) {
  const map = new Map();
  for (const domain of domains) {
    try {
      const cookies = await chrome.cookies.getAll({ domain });
      cookies.forEach(c => map.set(`${c.domain}:${c.name}`, c));
    } catch (err) {
      console.warn(`[Offer Search BG] Falha ao ler cookies para ${domain}:`, err.message);
    }
  }
  return Array.from(map.values());
}

async function syncAllSessions(triggerSource = 'unknown') {
  const apiUrl = await getApiUrl();
  console.log(`[Offer Search BG] Iniciando sincronização [Origem: ${triggerSource}] -> ${apiUrl}`);

  let results = {
    trigger: triggerSource,
    timestamp: new Date().toISOString(),
    ml: { success: false, count: 0, error: null },
    amazon: { success: false, count: 0, error: null }
  };

  // 1. Sincroniza Mercado Livre
  try {
    const mlRawCookies = await collectMarketplaceCookies(['mercadolivre.com.br', 'mercadolivre.com', 'mercadolibre.com']);
    const mlPayload = formatCookies(mlRawCookies);
    results.ml.count = mlPayload.length;

    if (mlPayload.length > 0) {
      const res = await fetch(`${apiUrl}/api/auth/sync-ml-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({
          cookies: mlPayload,
          total_cookies: mlPayload.length,
          synced_from: `chrome-extension-bg (${triggerSource})`,
          timestamp: results.timestamp
        })
      });
      const data = await res.json();
      results.ml.success = res.ok && Boolean(data.success);
      if (!results.ml.success) results.ml.error = data.error || `HTTP ${res.status}`;
    } else {
      results.ml.error = 'Nenhum cookie ML encontrado';
    }
  } catch (err) {
    results.ml.error = err.message;
  }

  // 2. Sincroniza Amazon
  try {
    const amzRawCookies = await collectMarketplaceCookies(['amazon.com.br', 'amazon.com']);
    const amzPayload = formatCookies(amzRawCookies);
    results.amazon.count = amzPayload.length;

    if (amzPayload.length > 0) {
      const res = await fetch(`${apiUrl}/api/auth/sync-amazon-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({
          cookies: amzPayload,
          total_cookies: amzPayload.length,
          synced_from: `chrome-extension-bg (${triggerSource})`,
          timestamp: results.timestamp
        })
      });
      const data = await res.json();
      results.amazon.success = res.ok && Boolean(data.success);
      if (!results.amazon.success) results.amazon.error = data.error || `HTTP ${res.status}`;
    } else {
      results.amazon.error = 'Nenhum cookie Amazon encontrado';
    }
  } catch (err) {
    results.amazon.error = err.message;
  }

  // Atualiza storage local
  const overallSuccess = results.ml.success || results.amazon.success;
  await chrome.storage.local.set({
    lastSync: results.timestamp,
    lastSyncStatus: overallSuccess ? 'success' : 'partial_or_failed',
    lastSyncResults: results
  });

  console.log(`[Offer Search BG] Sync concluído: ML=${results.ml.success} (${results.ml.count} cookies), Amazon=${results.amazon.success} (${results.amazon.count} cookies)`);
  return { success: overallSuccess, results };
}
