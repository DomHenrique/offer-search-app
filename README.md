# Offer Search App

Uma aplicação web Flask para buscar produtos em múltiplos marketplaces, salvar produtos preferidos e agendar buscas automáticas.

## 🚀 Funcionalidades

- 🔍 Busca de produtos em múltiplos marketplaces (Amazon, Mercado Livre)
- 💾 Aprovação e salvamento de produtos preferidos
- ⏰ Agendamento de buscas automáticas (6h ou 12h)
- 📊 Dashboard com estatísticas e histórico
- 🔐 Sistema de autenticação de usuários
- 📱 Interface responsiva com Bootstrap

## 🏗️ Tecnologias

- **Backend**: Flask (Python)
- **Banco de Dados**: Supabase (PostgreSQL)
- **Frontend**: HTML/CSS/JavaScript com Bootstrap
- **Web Scraping**: Selenium, BeautifulSoup, requests, SerpAPI
- **Autenticação**: Session-based com Werkzeug security

## 📦 Requisitos

- Python 3.8+
- Conta no Supabase
- Chave API SerpAPI (para buscas na Amazon)
- Chrome/Chromium (para web scraping)

## ⚙️ Configuração

1. **Clone o repositório**:
   ```bash
   git clone <url-do-repositorio>
   cd offer-search-app
   ```

2. **Crie um ambiente virtual**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # No Windows: .venv\\Scripts\\activate
   ```

3. **Instale as dependências**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure as variáveis de ambiente**:
   Crie um arquivo `.env` na raiz do projeto:
   ```env
   SECRET_KEY=sua-chave-secreta-aqui
   SUPABASE_URL=url-do-seu-projeto-supabase
   SUPABASE_KEY=chave-do-seu-projeto-supabase
   SERPAPI_KEY=sua-chave-serpapi
   ```

5. **Inicialize as tabelas do banco de dados**:
   A aplicação cria automaticamente as tabelas necessárias na primeira execução.

## ▶️ Execução

```bash
python app.py
```

Acesse `http://localhost:5000` no seu navegador.

## 📁 Estrutura do Projeto

```
offer-search-app/
├── app.py                 # Aplicação principal Flask
├── requirements.txt       # Dependências Python
├── .env                  # Variáveis de ambiente (não versionado)
├── database/             # Gerenciamento do banco de dados
│   ├── db_manager.py     # Gerenciador de operações do banco
│   ├── supabase_client.py # Cliente Supabase
│   └── table_manager.py  # Gerenciador de tabelas
├── routes/               # Rotas da aplicação (blueprints)
│   ├── auth_routes.py    # Autenticação
│   ├── search_routes.py  # Busca de produtos
│   ├── approval_routes.py# Aprovação de produtos
│   ├── schedule_routes.py# Agendamento
│   ├── settings_routes.py# Configurações
│   ├── history_routes.py # Histórico de buscas
│   └── alert_routes.py   # Alertas
├── scraping/             # Web scraping
│   ├── scraper_unificado.py        # Scraper principal
│   ├── serpapi_amazon_func.py     # Busca na Amazon via SerpAPI
│   └── web_scrap_mercado_livre.py # Scraper do Mercado Livre
├── utils/                # Funções utilitárias
│   ├── scheduler.py      # Agendador de tarefas
│   ├── helpers.py       # Funções auxiliares
│   └── decorators.py    # Decoradores personalizados
├── templates/            # Templates HTML
└── static/               # Arquivos estáticos (CSS, JS, imagens)
```

## 🛠️ Desenvolvimento

### Executando testes

```bash
# Testes ainda a serem implementados
```

### Linting

```bash
# Linting ainda a ser configurado
```

## 🤝 Contribuindo

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.

## 📧 Contato

Seu Nome - seu.email@exemplo.com

Link do Projeto: [https://github.com/seu-usuario/offer-search-app](https://github.com/seu-usuario/offer-search-app)