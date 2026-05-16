# pokemon-card-price-mvp

MVP: recebe foto da carta Pokémon e retorna **somente** o menor valor estimado de venda (ex: `R$ 28,55`).

## Endpoints

- `POST /estimate`
  - `multipart/form-data` com campo `file`
  - resposta:

```json
{"value":"R$ 28,55"}
```

- `POST /telegram/webhook`
  - endpoint para updates do Telegram (foto recebida no bot)
  - o bot responde no chat com **apenas o valor**

- `POST /telegram/set-webhook?webhook_url=https://seu-app/telegram/webhook`
  - helper para configurar webhook no Telegram

## Variáveis de ambiente

Obrigatórias:
- `TELEGRAM_BOT_TOKEN` (para integração Telegram)

## OCR local (sem tokens)

A identificação da carta usa **Tesseract OCR local** (sem OpenAI, sem custos por token).

Dependências de sistema:
- `tesseract-ocr`
- `tesseract-ocr-eng`
- `tesseract-ocr-por`

## Rodando localmente

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-por

pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Teste rápido do endpoint de upload

```bash
curl -s -X POST http://localhost:8000/estimate \
  -F "file=@darkrai-gx-88-147.jpg"
```

## Deploy no Render (com Dockerfile)

1. Conecte o repo no Render (Web Service).
2. Escolha **Environment: Docker**.
3. Em **Environment Variables**, adicione:
   - `TELEGRAM_BOT_TOKEN=...`
4. Deploy.
5. Copie a URL pública (ex: `https://pokemon-card-price-mvp.onrender.com`).
6. Configure o webhook:

```bash
curl -X POST "https://pokemon-card-price-mvp.onrender.com/telegram/set-webhook?webhook_url=https://pokemon-card-price-mvp.onrender.com/telegram/webhook"
```

## Deploy no Railway (com Dockerfile)

1. New Project -> Deploy from GitHub.
2. Railway detecta o `Dockerfile` automaticamente.
3. Em Variables, adicione:
   - `TELEGRAM_BOT_TOKEN=...`
4. Após URL pública final (ex: `https://seu-app.up.railway.app`), configure webhook:

```bash
curl -X POST "https://seu-app.up.railway.app/telegram/set-webhook?webhook_url=https://seu-app.up.railway.app/telegram/webhook"
```

## Fluxo no Telegram

- Usuário envia foto da carta
- API baixa a imagem via Telegram API
- Detecta texto da carta com Tesseract OCR
- Busca menor valor (PriceCharting/used), converte para BRL
- Responde no chat com texto simples: `R$ XX,XX`
