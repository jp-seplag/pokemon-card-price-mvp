# pokemon-card-price-mvp

MVP: recebe foto da carta e retorna **apenas** o menor valor estimado de venda.

## Endpoint

`POST /estimate`
- multipart/form-data com campo `file`
- resposta:

```json
{"value":"R$ 28,55"}
```

## Como roda

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Observações

- Identificação da carta:
  - Preferencial: `OPENAI_API_KEY` configurada (vision)
  - Fallback: nome do arquivo (ex: `darkrai-gx-88-147.jpg`)
- Fonte de preço: PriceCharting (menor valor/"used")
- Conversão USD->BRL com fallback estático

## Exemplo cURL

```bash
curl -s -X POST http://localhost:8000/estimate \
  -F "file=@darkrai-gx-88-147.jpg"
```
