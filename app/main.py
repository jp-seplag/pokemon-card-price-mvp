from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI(title="pokemon-card-min-price", version="0.1.0")

PRICECHARTING_SEARCH = "https://www.pricecharting.com/search-products"
PRICECHARTING_BASE = "https://www.pricecharting.com"


@dataclass
class CardMatch:
    name: str
    number: Optional[str]


def _extract_card_hint(filename: str) -> Optional[CardMatch]:
    """
    Heurística simples via nome do arquivo, ex:
    darkrai-gx-88-147.jpg -> Darkrai GX 88/147
    """
    base = Path(filename).stem.lower()
    base = base.replace("_", "-")
    number_match = re.search(r"(\d{1,3})[-_](\d{1,3})", base)
    number = None
    if number_match:
        number = f"{number_match.group(1)}/{number_match.group(2)}"
        base = base.replace(number_match.group(0), "")

    words = [w for w in re.split(r"[^a-z0-9]+", base) if w and not w.isdigit()]
    if not words:
        return None

    tokens = []
    for w in words:
        if w in {"gx", "ex", "v", "vmx", "vstar"}:
            tokens.append(w.upper())
        else:
            tokens.append(w.capitalize())

    name = " ".join(tokens).strip()
    if not name:
        return None
    return CardMatch(name=name, number=number)


def _extract_card_with_openai(image_bytes: bytes) -> Optional[CardMatch]:
    """
    Opcional: usa OpenAI vision quando OPENAI_API_KEY estiver presente.
    Retorna JSON esperado: {"name":"Darkrai GX","number":"88/147"}
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    import base64

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": [
            {
                "role": "system",
                "content": "Extract Pokemon card name and collector number from image. Respond JSON only with keys name and number.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Return strictly JSON: {\"name\":...,\"number\":...}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ],
        "temperature": 0,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=40) as client:
        resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        if resp.status_code >= 300:
            return None
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    m = re.search(r"\{[\s\S]*\}", content)
    if not m:
        return None

    import json

    try:
        parsed = json.loads(m.group(0))
    except Exception:
        return None

    name = (parsed.get("name") or "").strip()
    number = (parsed.get("number") or "").strip() or None
    if not name:
        return None
    return CardMatch(name=name, number=number)


def _search_pricecharting(card: CardMatch) -> Optional[str]:
    q = card.name
    if card.number:
        q = f"{q} {card.number}"

    with httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = client.get(PRICECHARTING_SEARCH, params={"type": "prices", "q": q})
        if r.status_code >= 300:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # Primeiro resultado que pareça carta Pokémon
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            text = a.get_text(" ", strip=True).lower()
            if "/game/pokemon-" in href and card.name.split()[0].lower() in text:
                return PRICECHARTING_BASE + href

    return None


def _extract_used_price_usd(product_url: str) -> Optional[float]:
    with httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = client.get(product_url)
        if r.status_code >= 300:
            return None

    # Pega <td id="used_price">$5.62</td>
    m = re.search(r'id="used_price"[\s\S]*?\$([0-9]+(?:\.[0-9]{2})?)', r.text)
    if not m:
        return None
    return float(m.group(1))


def _usd_to_brl(usd: float) -> Optional[float]:
    # exchangerate.host normalmente funciona sem chave
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get("https://api.exchangerate.host/convert", params={"from": "USD", "to": "BRL", "amount": usd})
            if r.status_code < 300:
                data = r.json()
                result = data.get("result")
                if result:
                    return float(result)
    except Exception:
        pass

    # fallback estático
    return usd * 5.2


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/estimate")
async def estimate(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="arquivo vazio")

    card = _extract_card_with_openai(content)
    if not card:
        card = _extract_card_hint(file.filename or "")

    if not card:
        raise HTTPException(
            status_code=422,
            detail="Não consegui identificar a carta automaticamente. Renomeie o arquivo como nome-da-carta-88-147.jpg ou configure OPENAI_API_KEY.",
        )

    url = _search_pricecharting(card)
    if not url:
        raise HTTPException(status_code=404, detail="Carta não encontrada na fonte de preços.")

    usd = _extract_used_price_usd(url)
    if usd is None:
        raise HTTPException(status_code=502, detail="Não consegui extrair o menor valor de venda.")

    brl = _usd_to_brl(usd)
    value = round(brl, 2)

    # resposta mínima pedida: valor estimado pelo menor valor de venda
    return {"value": f"R$ {value:.2f}".replace('.', ',')}
