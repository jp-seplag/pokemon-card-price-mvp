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

Opcionais:
- `OPENAI_API_KEY` (melhora identificação da carta via visão)
- `OPENAI_MODEL` (default: `gpt-4o-mini`)

## Rodando localmente

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Teste rápido do endpoint de upload

```bash
curl -s -X POST http://localhost:8000/estimate \
  -F "file=@darkrai-gx-88-147.jpg"
```

## Deploy no Render

1. Conecte o repo no Render (Web Service).
2. Configuração:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Em **Environment**, adicione:
   - `TELEGRAM_BOT_TOKEN=...`
   - `OPENAI_API_KEY=...` (opcional)
4. Após deploy, copie a URL pública (ex: `https://pokemon-card-price-mvp.onrender.com`).
5. Configure o webhook:

```bash
curl -X POST "https://pokemon-card-price-mvp.onrender.com/telegram/set-webhook?webhook_url=https://pokemon-card-price-mvp.onrender.com/telegram/webhook"
```

## Deploy no Railway

1. New Project -> Deploy from GitHub.
2. Em Variables, adicione:
   - `TELEGRAM_BOT_TOKEN=...`
   - `OPENAI_API_KEY=...` (opcional)
3. Railway detecta Python automaticamente.
4. Start command:
   - `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Com a URL pública final (ex: `https://seu-app.up.railway.app`), configure webhook:

```bash
curl -X POST "https://seu-app.up.railway.app/telegram/set-webhook?webhook_url=https://seu-app.up.railway.app/telegram/webhook"
```

## Fluxo no Telegram

- Usuário envia foto da carta
- API baixa a imagem via Telegram API
- Detecta carta (OpenAI vision quando disponível; fallback por nome de arquivo)
- Busca menor valor (PriceCharting/used), converte para BRL
- Responde no chat com texto simples: `R$ XX,XX`
