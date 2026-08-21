# ⚡ Offer Search - Extensão de Sincronização de Sessão do Mercado Livre

Extensão Manifest V3 para Google Chrome que captura de forma segura e legítima os cookies de sessão da sua conta do Mercado Livre e envia para o backend do **Offer Search App**.

---

## 🚀 Como Instalar no Google Chrome (Modo Desenvolvedor)

1. Abra o Google Chrome e acesse: `chrome://extensions`
2. No canto superior direito, ative a chave **"Modo do desenvolvedor"** (Developer mode).
3. Clique no botão **"Carregar sem compactação"** (Load unpacked).
4. Selecione a pasta `extension/` deste projeto:
   `/home/henrique-carvalho/Documentos/dev/offer-search-app/extension`
5. A extensão **Offer Search - ML Session Sync** aparecerá na sua barra de extensões do Chrome!

---

## 🔄 Como Usar

1. No seu Chrome, acesse [mercadolivre.com.br](https://www.mercadolivre.com.br) e faça login normalmente com sua conta de vendedor.
2. Clique no ícone da extensão **ML Session Sync** no canto superior do Chrome.
3. Verifique se a URL da API está correta (padrão: `http://localhost:5000` para local, ou a URL da sua VPS).
4. Clique no botão **`[ ⚡ Sincronizar Sessão ]`**.
5. Pronto! O robô de busca e raspagem de catálogos navegará como usuário 100% autenticado, sem bloqueios de Captcha ou 2FA.
