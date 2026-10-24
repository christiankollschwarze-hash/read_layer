"""STAGE 610 — Cover
Funktion:     Cover-Illustration (Tuschezeichnung, ohne Text).
Wirkungsweise: Gemini-Bildmodell, Stimmung aus dem Klappentext-Meta, bis 4 Versuche.
Komponenten:  pipeline/s610_cover.py
Zulieferer:   s600 Klappentext (work/600_klappentext.json)
Abnehmer:     s620/s630 ePub, Katalog (images/cover.png bzw. .jpg)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 12: Cover-Illustration (Gemini-Bildmodell)
=============================================================
Erzeugt die Cover-ILLUSTRATION (Tuschezeichnung, SOMNIO-Cremehintergrund,
OHNE Text) ueber das Gemini-Bildmodell. Titel/Autor/Wortmarke legt Stage 11
als Vektor darueber -> scharfe, konsistente Typografie.

Endpunkt:  POST /v1beta/models/<model>:generateContent
Wichtig:   responseModalities MUSS ["TEXT","IMAGE"] sein (nur IMAGE schlaegt fehl).
Antwort:   Bild base64 in candidates[0].content.parts[].inlineData.data

Modelle (config.MODELS["image"]):
  gemini-2.5-flash-image      -> "Nano Banana", guenstig, 1024x1024 (quadratisch)
  gemini-3-pro-image-preview  -> "Nano Banana Pro", hohe Qualitaet, kostet pro Bild

Ausgabe:  books/<book_id>/images/cover.png   (Stage 11 findet es dort automatisch)
Gemini ist aus dem Claude-Container gesperrt -> echter Lauf laeuft lokal bei CK.
"""

import os, json, base64
from config import config

STAGE = "610"
IMG_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# SOMNIO-Hintergrund -- identisch zum Vektor-Cover in Stage 11.
# Hintergrund: warmes Weiss aus der zentralen Source of Truth (config.COVER_BG).
BG_COLOR = getattr(config, "COVER_BG", "#faf8f4")
# Cover-Format (Hochformat) und Aufloesung. 2:3 wird auch von 2.5-flash-image unterstuetzt.
COVER_ASPECT = "2:3"
COVER_SIZE   = "2K"

# Gueltiges 1x1-PNG (transparent) fuer den mock-Modus -- beweist nur den Schreibpfad.
_MOCK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def _mood(book_id: str) -> str:
    """Optionale Stimmungsworte aus 600_klappentext.json (Ton/Genre), falls vorhanden."""
    try:
        sj = json.load(open(config.work_path(book_id, "600_klappentext"), encoding="utf-8"))
        meta = sj.get("meta", {})
        # 18.10.2026: Schauplatz entfernt -- er stammt aus einer Textprobe (Anfang/Mitte) und zieht
        # das Motiv auf Nebenschauplaetze (Frankenstein: "Huette im Wald"). Nur Ton + Genre.
        bits = [meta.get("ton", ""), meta.get("genre", "")]
        return ", ".join(b for b in bits if b)
    except Exception:
        return ""


def _motiv(book_id: str) -> str:
    """Optionales, von CK vorgegebenes Motiv aus book.json ("cover_motiv", englisch)."""
    try:
        bj = json.load(open(os.path.join(config.book_dir(book_id), "book.json"), encoding="utf-8"))
        return (bj.get("cover_motiv") or "").strip()
    except Exception:
        return ""


def _build_prompt(title: str, author: str, mood: str, motiv: str = "") -> str:
    # SOMNIO One-Line-Stil. Englisch fuer hoehere Bildmodell-Zuverlaessigkeit
    # (lange deutsche Prompts kippen oft in Text-Antworten). Bedeutungstreu zur
    # deutschen Quelle im cover_prompt_template.md.
    base = (
        f"\u201c{title}\u201d, a novel by {author}, rendered as a SINGLE, "
        f"unbroken, flawless black ink line (one continuous line drawing). The style is "
        f"extremely minimalist and highly abstracted, using only the absolute essential "
        f"contours of the forms (maximum economy of line). The line must be perfectly "
        f"precise, clean and of constant weight, with no shading, no cross-hatching, no "
        f"sketch lines and no multiple overlaps. The whole work is isolated on a flawless, "
        f"empty background with no texture and no detail. The focus is on pure contour and "
        f"the extreme reduction of detail. NEVER include any text, letters, title or "
        f"signature. A SINGLE moment of the work must capture the essence of the book \u2014 "
        f"one subject, one moment, never a sequence of scenes or a storyboard. If the work "
        f"has no single iconic object, choose one abstract or metaphorical form (a posture, "
        f"a gesture, a shape), never an assembly of plot elements. The line is as finite as "
        f"a single stroke of an ink pen, so choose the core of the motif with care. "
        f"The background is one solid, even, warm off-white fill in the exact colour {BG_COLOR}. "
        f"Vertical book-cover format, portrait orientation, aspect ratio 2:3 (width to height); "
        f"center the motif in the frame, filling most of the height, with balanced, roughly "
        f"equal empty margins above and below. The motif should be large and dominant, not "
        f"a small element floating in the upper part."
    )
    if motiv:
        base += f" The motif is: {motiv}."
    if mood:
        base += f" Mood to evoke: {mood}."
    return base


def _generate(prompt: str, model: str, api_key: str, retries: int = 4):
    """Live-Aufruf mit Wiederholung. Liefert (bytes, mime). Bildmodelle geben
    gelegentlich nur Text zurueck -> erneut versuchen; bei endgueltigem Scheitern
    den Text zur Diagnose zeigen (Sicherheitssperre vs. Format-Eigenheit)."""
    import requests, time
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": COVER_ASPECT, "imageSize": COVER_SIZE},
        },
    }
    last_text = ""
    for attempt in range(1, retries + 1):
        r = requests.post(IMG_ENDPOINT.format(model=model),
                          headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                          json=payload, timeout=180)
        if r.status_code != 200:
            if attempt < retries:
                print(f"  [{attempt}/{retries}] Bild-API {r.status_code} -> erneut ...")
                time.sleep(attempt * 2); continue
            raise RuntimeError(f"Bild-API {r.status_code}: {r.text[:400]}")
        js = r.json()
        from pipeline import usage_log
        usage_log.log(model, "gemini", js.get("usageMetadata"), {"task": "cover", "versuch": attempt})
        parts = js["candidates"][0]["content"]["parts"]
        for p in parts:
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"]), inline.get("mimeType", "image/png")
        last_text = " ".join(p.get("text", "") for p in parts if p.get("text")).strip()
        print(f"  [{attempt}/{retries}] nur Text zurueck -> erneut ...")
        time.sleep(attempt * 2)
    raise RuntimeError("Kein Bild nach mehreren Versuchen. Modell-Text war:\n  "
                       + (last_text[:500] or "(leer)"))


def _meta(book_id: str):
    bdir = config.book_dir(book_id)
    bj = json.load(open(os.path.join(bdir, "book.json"), encoding="utf-8"))
    title = bj.get("titel_original") or book_id
    author = bj.get("author_slug", "")
    ap = os.path.join(config.author_dir(config.author_of(book_id)), "author.json")
    if os.path.exists(ap):
        author = json.load(open(ap, encoding="utf-8")).get("name_display", author)
    return title, author


def run(book_id: str, force: bool = False):
    img_dir = os.path.join(config.book_dir(book_id), "images")
    os.makedirs(img_dir, exist_ok=True)
    out_png = os.path.join(img_dir, "cover.png")

    if os.path.exists(out_png) and not force:
        print(f"[stage12] Cover existiert -> ueberspringe ({out_png}). --force zum Neugenerieren.")
        return out_png

    title, author = _meta(book_id)
    prompt = _build_prompt(title, author, _mood(book_id), _motiv(book_id))
    print(f"[stage12] Cover-Prompt:\n  {prompt}\n")

    if config.RUN_MODE == "mock":
        open(out_png, "wb").write(_MOCK_PNG)
        print(f"[stage12] (mock) Platzhalter-Cover -> {out_png}")
        return out_png

    api_key = config.GEMINI_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY fehlt (live-Modus).")
    model = config.MODELS.get("image", "gemini-2.5-flash-image")

    data, mime = _generate(prompt, model, api_key)
    # Wir speichern einheitlich als cover.png (Stage 11 erwartet das); bei JPEG umbenennen.
    ext = "jpg" if "jpeg" in mime else "png"
    out = os.path.join(img_dir, f"cover.{ext}")
    open(out, "wb").write(data)
    print(f"[stage12] Cover ({model}, {mime}, {len(data)} Bytes) -> {out}")
    return out


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run(args[0] if args else "jekyll-and-hyde", force="--force" in sys.argv)
