from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import pytesseract
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from PIL import Image, ImageEnhance, ImageFilter

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


def _extract_card_with_tesseract(image_bytes: bytes) -> Optional[CardMatch]:
    """
    Extração local via OCR (Tesseract), sem uso de API paga.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
    except Exception:
        return None

    # Pré-processamento simples para melhorar OCR
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)

    try:
        text = pytesseract.image_to_string(img, lang="eng+por")
    except Exception:
        try:
            text = pytesseract.image_to_string(img, lang="eng")
        except Exception:
            return None

    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return None

    # Número de coleção (ex: 88/147)
    n = re.search(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b", clean)
    number = f"{n.group(1)}/{n.group(2)}" if n else None

    # Nome da carta: tenta capturar algo como "Darkrai GX"
    # Heurística: palavra inicial com maiúscula + sufixos comuns
    candidates = re.findall(r"\b([A-Z][a-z]{2,15}(?:\s+(?:GX|EX|V|VMAX|VSTAR))?)\b", clean)
    if not candidates:
        # fallback: primeira palavra plausível
        tokens = re.findall(r"[A-Za-z]{3,15}", clean)
        if not tokens:
            return None
        name = tokens[0].capitalize()
        return CardMatch(name=name, number=number)

    # Escolhe o candidato mais longo (geralmente mais específico)
    name = sorted(candidates, key=len, reverse=True)[0].strip()
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


def _estimate_value_from_image_bytes(image_bytes: bytes, filename: str) -> str:
    card = _extract_card_with_tesseract(image_bytes)
    if not card:
        card = _extract_card_hint(filename or "")

    if not card:
        raise HTTPException(
            status_code=422,
            detail="Não consegui identificar a carta automaticamente. Tente uma foto mais nítida ou renomeie o arquivo como nome-da-carta-88-147.jpg.",
        )

    url = _search_pricecharting(card)
    if not url:
        raise HTTPException(status_code=404, detail="Carta não encontrada na fonte de preços.")

    usd = _extract_used_price_usd(url)
    if usd is None:
        raise HTTPException(status_code=502, detail="Não consegui extrair o menor valor de venda.")

    brl = _usd_to_brl(usd)
    value = round(brl, 2)
    return f"R$ {value:.2f}".replace('.', ',')


def _telegram_api_url(method: str) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado")
    return f"https://api.telegram.org/bot{token}/{method}"


def _telegram_file_url(file_path: str) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado")
    return f"https://api.telegram.org/file/bot{token}/{file_path}"


def _telegram_send_message(chat_id: int, text: str) -> None:
    with httpx.Client(timeout=20) as client:
        client.post(_telegram_api_url("sendMessage"), json={"chat_id": chat_id, "text": text})


def _telegram_download_photo(file_id: str) -> tuple[bytes, str]:
    with httpx.Client(timeout=30) as client:
        file_info = client.get(_telegram_api_url("getFile"), params={"file_id": file_id})
        file_info.raise_for_status()
        data = file_info.json()
        path = data.get("result", {}).get("file_path")
        if not path:
            raise RuntimeError("Não consegui obter file_path do Telegram")

        img = client.get(_telegram_file_url(path))
        img.raise_for_status()

    filename = path.split("/")[-1] if "/" in path else "telegram_photo.jpg"
    return img.content, filename


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/estimate")
async def estimate(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="arquivo vazio")

    value = _estimate_value_from_image_bytes(content, file.filename or "")
    # resposta mínima pedida: valor estimado pelo menor valor de venda
    return {"value": value}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    message = payload.get("message") or payload.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    photos = message.get("photo") or []
    if not chat_id:
        return {"ok": True}

    if not photos:
        _telegram_send_message(chat_id, "Envie uma foto da carta.")
        return {"ok": True}

    # Telegram envia múltiplos tamanhos; o último costuma ser o maior.
    biggest = photos[-1]
    file_id = biggest.get("file_id")
    if not file_id:
        _telegram_send_message(chat_id, "Não consegui ler essa foto. Tente novamente.")
        return {"ok": True}

    try:
        image_bytes, filename = _telegram_download_photo(file_id)
        value = _estimate_value_from_image_bytes(image_bytes, filename)
        # Resposta mínima solicitada: apenas o valor.
        _telegram_send_message(chat_id, value)
    except Exception:
        _telegram_send_message(chat_id, "Não consegui estimar essa carta agora.")

    return {"ok": True}


@app.post("/telegram/set-webhook")
def telegram_set_webhook(webhook_url: str):
    with httpx.Client(timeout=20) as client:
        r = client.post(_telegram_api_url("setWebhook"), json={"url": webhook_url})
        r.raise_for_status()
        return r.json()
