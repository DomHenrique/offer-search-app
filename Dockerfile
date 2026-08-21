# Dockerfile para Offer Search App
FROM python:3.11-slim

WORKDIR /app

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    PORT=5000 \
    GECKODRIVER_VERSION=v0.34.0

# Instala dependências do sistema, Firefox e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    firefox-esr \
    wget \
    curl \
    tar \
    bzip2 \
    ca-certificates \
    libgtk-3-0 \
    libasound2 \
    libdbus-glib-1-2 \
    libx11-xcb1 \
    libxtst6 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Baixa e instala o geckodriver para o Selenium
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then GECKO_ARCH="linux64"; \
    elif [ "$ARCH" = "arm64" ]; then GECKO_ARCH="linux-aarch64"; \
    else GECKO_ARCH="linux64"; fi && \
    wget -q https://github.com/mozilla/geckodriver/releases/download/${GECKODRIVER_VERSION}/geckodriver-${GECKODRIVER_VERSION}-${GECKO_ARCH}.tar.gz -O /tmp/geckodriver.tar.gz && \
    tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/geckodriver && \
    rm -f /tmp/geckodriver.tar.gz

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Copia o código da aplicação
COPY . .

# Expor porta
EXPOSE 5000

# Executar aplicação
CMD ["python", "app.py"]