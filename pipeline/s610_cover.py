"""STAGE 610 — Cover (Illustration ohne Text, einmal je Werk)
Funktion:     Cover-Illustration (eine Tuschelinie, COVER_BG, 2:3, ohne Text) als Grundlage fuer 615.
Wirkungsweise: Herkunft je Werk:
                epub     Cover aus 150 uebernommen (book.json cover = images/cover_source.*) -> 610 entfaellt
                erbe     Reihenteil >= 2: Illustration von Teil 1 (0 $), Regler --erbe an|aus
                upload   eigenes Bild (--bild DATEI)
                variante gewaehlte Variante aus --varianten N (--waehle I)
                bestand  Gutenberg-Werk mit vorhandenem Bild ohne Manifest -> uebernommen, nur geprueft
                erzeugt  Gemini-Bildmodell (Prompt aus Titel, Autor, Ton/Genre 600, Motiv), bis 4 Anlaeufe
                         bei "nur Text"; Bildpruefung rot -> 1x automatisch neu
Komponenten:  pipeline/s610_cover.py
Eingang:      work/600_klappentext.json (meta ton, genre; Gate 600 frei); book.json (titel_original, cover_motiv,
              cover, reihe/teil, Mandant, cover_regler {modell}); author.json name_display (110) bzw.
              book.json autor_name (150), Pflicht ausser rechte eigene
Ausgabe:      images/cover.png bzw. .jpg; work/610_cover.json Manifest (herkunft, prompt, modell, versuche,
              eingang_hash, bild_hash, pruefung); Regler persistent in work/610_entscheidungen.json
Gate:         je Werk, rein bildtechnisch: Bild lesbar; Breite >= 1000 px; 2:3 +-2 %; Randfarbe dE <= 5 zu
              COVER_BG; kein Text (OCR, 0 Woerter >= 3 Buchstaben); Motivhoehe >= 60 %, Zentrum +-10 %;
              Linienanteil 1-25 %. Rot -> 1x automatisch neu (erzeugt/bestand), danach Mensch.
              Sperre "nur Text" -> Mensch (Motiv vorgeben). Mandant user/verlag mit erzeugtem Cover -> immer
              Mensch. Stopp: Gate 600 nicht frei, Autor fehlt, Mock im Live-Lauf, Erbe ohne Bild Teil 1.
              Mensch-Freigabe gilt bei gleichem bild_hash. Sichtpruefung am fertigen Cover in 615.
Kosten:       usage_log Stage 610 (gemini-2.5-flash-image ~3,7 ct je Bild); unveraenderte Eingaenge -> kein Aufruf.
Abnehmer:     s615 Cover final.
"""
import argparse
import base64
import io
import json
import os
import shutil
import time

from config import config
from pipeline import gate, manifest, mock, status, usage_log

STAGE = "610"
PROMPT_V = 2
IMG_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BG_COLOR = getattr(config, "COVER_BG", "#faf8f4")
COVER_ASPECT = "2:3"
COVER_SIZE = "2K"
VERSUCHE_TEXT = 4
SCHWELLEN = {"breite_min": 1000, "format_tol": 0.02, "delta_e_max": 5.0, "ocr_woerter_max": 0,
             "motiv_hoehe_min": 0.60, "zentrum_tol": 0.10, "linien_min": 0.01, "linien_max": 0.25}
ENDUNGEN = ("png", "jpg")


class NurText(RuntimeError):
    """Bildmodell lieferte nach allen Anlaeufen nur Text (meist Sicherheitssperre)."""


# ------------------------------------------------------------------ Pfade / Ablage
def img_dir(werk):
    return os.path.join(config.book_dir(werk), "images")


def bild_pfad(werk):
    for e in ENDUNGEN:
        p = os.path.join(img_dir(werk), f"cover.{e}")
        if os.path.exists(p):
            return p
    return None


def _bild_schreiben(werk, data, mime):
    os.makedirs(img_dir(werk), exist_ok=True)
    ext = "jpg" if "jpeg" in (mime or "") else "png"
    for e in ENDUNGEN:
        p = os.path.join(img_dir(werk), f"cover.{e}")
        if e != ext and os.path.exists(p):
            os.remove(p)
    p = os.path.join(img_dir(werk), f"cover.{ext}")
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, p)
    return p


def _bild_kopieren(werk, quelle):
    ext = os.path.splitext(quelle)[1].lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    with open(quelle, "rb") as f:
        data = f.read()
    if mime == "image/png" and not data.startswith(b"\x89PNG"):
        from PIL import Image
        buf = io.BytesIO()
        Image.open(io.BytesIO(data)).convert("RGB").save(buf, "PNG")
        data = buf.getvalue()
    return _bild_schreiben(werk, data, mime)


def manifest_pfad(werk):
    return config.work_path(werk, "610_cover")


def _json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def entscheidungen(werk):
    return _json(config.work_path(werk, "610_entscheidungen")) or {}


def entscheidung_setzen(werk, wer, **kw):
    d = entscheidungen(werk)
    d.setdefault("protokoll", [])
    for k, v in kw.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    d["protokoll"].append({"wer": wer, "wann": manifest.jetzt(), **{k: v for k, v in kw.items()}})
    manifest.json_atomar(config.work_path(werk, "610_entscheidungen"), d, indent=2)
    return d


# ------------------------------------------------------------------ Eingaenge
def _book(werk):
    return _json(os.path.join(config.book_dir(werk), "book.json")) or {}


def stimmung(werk):
    """Ton + Genre aus 600 (meta). Schauplatz bewusst nicht (zieht das Motiv auf Nebenschauplaetze)."""
    meta = (_json(config.work_path(werk, "600_klappentext")) or {}).get("meta") or {}
    bits = [meta.get("ton") or "", meta.get("genre") or ""]
    return ", ".join(b.strip() for b in bits if b and not mock.ist_text(b))


def autor_name(werk, roh):
    """name_display aus author.json (110), sonst autor_name aus book.json (150). '' = fehlt."""
    try:
        slug = config.author_of(werk)
    except Exception:
        slug = roh.get("author_slug") or ""
    if slug:
        a = _json(os.path.join(config.author_dir(slug), "author.json")) or {}
        if (a.get("name_display") or "").strip():
            return a["name_display"].strip()
    n = (roh.get("autor_name") or "").strip()
    return "" if n.lower() in ("", "unbekannt", "unknown") else n


def prompt_bauen(title, author, mood, motiv=""):
    # SOMNIO One-Line-Stil, englisch (lange deutsche Prompts kippen oft in Text-Antworten).
    von = f", a novel by {author}," if author else ", a novel,"
    base = (
        f"“{title}”{von} rendered as a SINGLE, "
        f"unbroken, flawless black ink line (one continuous line drawing). The style is "
        f"extremely minimalist and highly abstracted, using only the absolute essential "
        f"contours of the forms (maximum economy of line). The line must be perfectly "
        f"precise, clean and of constant weight, with no shading, no cross-hatching, no "
        f"sketch lines and no multiple overlaps. The whole work is isolated on a flawless, "
        f"empty background with no texture and no detail. The focus is on pure contour and "
        f"the extreme reduction of detail. NEVER include any text, letters, title or "
        f"signature. A SINGLE moment of the work must capture the essence of the book — "
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


# ------------------------------------------------------------------ Bildmodell
def _api(prompt, model, api_key):
    """Ein Aufruf. -> (bytes|None, mime, text, usage)"""
    import requests
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                                    "imageConfig": {"aspectRatio": COVER_ASPECT, "imageSize": COVER_SIZE}}}
    r = requests.post(IMG_ENDPOINT.format(model=model),
                      headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                      json=payload, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"Bild-API {r.status_code}: {r.text[:300]}")
    js = r.json()
    parts = ((js.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"]), inline.get("mimeType", "image/png"), "", js.get("usageMetadata")
    text = " ".join(p.get("text", "") for p in parts if p.get("text")).strip()
    return None, None, text, js.get("usageMetadata")


def mock_bild():
    """Strukturtreues Mock-Cover (1024x1536, eine Linie, COVER_BG) mit Kennung READLAYER-MOCK."""
    from PIL import Image, ImageDraw, PngImagePlugin
    w, h = 1024, 1536
    im = Image.new("RGB", (w, h), BG_COLOR)
    d = ImageDraw.Draw(im)
    d.ellipse((w * 0.32, h * 0.16, w * 0.68, h * 0.42), outline="black", width=8)
    d.line((w * 0.5, h * 0.42, w * 0.5, h * 0.84), fill="black", width=8)
    d.arc((w * 0.30, h * 0.50, w * 0.70, h * 0.84), 200, 340, fill="black", width=8)
    info = PngImagePlugin.PngInfo()
    info.add_text("Software", mock.MARKER.decode())
    buf = io.BytesIO()
    im.save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


def ist_mock(pfad):
    if not pfad or not os.path.exists(pfad):
        return False
    if mock.ist_datei(pfad):
        return True
    try:
        from PIL import Image
        with Image.open(pfad) as im:
            return im.size == (1, 1) or im.info.get("Software") == mock.MARKER.decode()
    except Exception:
        return False


def generieren(prompt, model, versuche):
    """Bis VERSUCHE_TEXT Anlaeufe gegen 'nur Text'. -> (bytes, mime). versuche: Liste wird ergaenzt."""
    if mock.aktiv():
        versuche.append({"nr": len(versuche) + 1, "ergebnis": "bild", "mock": True, "zeit": manifest.jetzt()})
        return mock_bild(), "image/png"
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY fehlt (live-Modus)")
    last = ""
    for i in range(1, VERSUCHE_TEXT + 1):
        try:
            data, mime, text, usage = _api(prompt, model, api_key)
        except RuntimeError as e:
            versuche.append({"nr": len(versuche) + 1, "ergebnis": "fehler", "text": str(e)[:300],
                             "zeit": manifest.jetzt()})
            if i == VERSUCHE_TEXT:
                raise
            time.sleep(i * 2)
            continue
        usage_log.log(model, "gemini", usage, {"task": "cover", "versuch": len(versuche) + 1})
        if data:
            versuche.append({"nr": len(versuche) + 1, "ergebnis": "bild", "mime": mime, "bytes": len(data),
                             "zeit": manifest.jetzt()})
            return data, mime
        last = text
        versuche.append({"nr": len(versuche) + 1, "ergebnis": "nur_text", "text": text[:300],
                         "zeit": manifest.jetzt()})
        time.sleep(i * 2)
    raise NurText(last[:500] or "(leer)")


# ------------------------------------------------------------------ Bildpruefung
def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lab(rgb):
    import numpy as np
    c = np.asarray(rgb, dtype=float) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = (m @ c) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def delta_e(a, b):
    import numpy as np
    return float(np.linalg.norm(_lab(a) - _lab(b)))


def ocr_woerter(im):
    """Woerter >= 3 Buchstaben mit Konfidenz >= 70. None = OCR nicht verfuegbar."""
    try:
        import pytesseract
        d = pytesseract.image_to_data(im.convert("L"), config="--psm 11", output_type=pytesseract.Output.DICT)
    except Exception:
        return None
    out = []
    for t, c in zip(d.get("text", []), d.get("conf", [])):
        t = (t or "").strip()
        try:
            c = float(c)
        except (TypeError, ValueError):
            c = -1
        if len(t) >= 3 and t.isalpha() and c >= 70:
            out.append(t)
    return out


def pruefen(pfad, bg=BG_COLOR):
    """Bildmetriken. -> dict (lesbar False, wenn nicht zu oeffnen)."""
    import numpy as np
    from PIL import Image
    try:
        im = Image.open(pfad)
        im.load()
        im = im.convert("RGB")
    except Exception as e:
        return {"lesbar": False, "fehler": str(e)[:200]}
    w, h = im.size
    m = {"lesbar": True, "breite": w, "hoehe": h, "format": round((w / h) / (2 / 3) - 1, 4) if h else None}
    sw = 500
    klein = im.resize((sw, max(1, round(h * sw / w))), Image.BILINEAR) if w > sw else im
    a = np.asarray(klein, dtype=float)
    kh, kw = a.shape[:2]
    rb, rh = max(1, round(kw * 0.02)), max(1, round(kh * 0.02))
    rand = np.concatenate([a[:rh].reshape(-1, 3), a[-rh:].reshape(-1, 3),
                           a[:, :rb].reshape(-1, 3), a[:, -rb:].reshape(-1, 3)])
    med = np.median(rand, axis=0)
    m["rand_rgb"] = [int(x) for x in med]
    m["delta_e"] = round(delta_e(med, _hex_rgb(bg)), 2)
    tinte = np.linalg.norm(a - med, axis=2) > 60
    anteil = float(tinte.mean())
    m["linien"] = round(anteil, 4)
    if tinte.any():
        ys, xs = np.nonzero(tinte)
        y0, y1 = np.quantile(ys, [0.005, 0.995])
        x0, x1 = np.quantile(xs, [0.005, 0.995])
        m["motiv_hoehe"] = round(float((y1 - y0 + 1) / kh), 3)
        m["zentrum"] = round(float(((x0 + x1) / 2) / kw - 0.5), 3)
    else:
        m["motiv_hoehe"], m["zentrum"] = 0.0, None
    woerter = ocr_woerter(im)
    m["ocr"] = None if woerter is None else len(woerter)
    if woerter:
        m["ocr_beispiele"] = woerter[:5]
    return m


def rot_liste(m, s=SCHWELLEN):
    """Liste der verletzten Bildmetriken (leer = gruen). OCR None zaehlt nicht."""
    if not m.get("lesbar"):
        return ["lesbar"]
    f = []
    if m["breite"] < s["breite_min"]:
        f.append("breite")
    if m["format"] is None or abs(m["format"]) > s["format_tol"]:
        f.append("format")
    if m["delta_e"] > s["delta_e_max"]:
        f.append("randfarbe")
    if m.get("ocr") is not None and m["ocr"] > s["ocr_woerter_max"]:
        f.append("text_im_bild")
    if m["motiv_hoehe"] < s["motiv_hoehe_min"]:
        f.append("motiv_hoehe")
    if m["zentrum"] is None or abs(m["zentrum"]) > s["zentrum_tol"]:
        f.append("zentrum")
    if not (s["linien_min"] <= m["linien"] <= s["linien_max"]):
        f.append("linien")
    return f


def gate_bild(g, m, s, bei_fehler="mensch"):
    rs = "610"
    if not g.pflicht("lesbar", m.get("lesbar"), bei_fehler=bei_fehler, ruecksprung=rs,
                     text="Bild lesbar" + (f" ({m.get('fehler')})" if m.get("fehler") else "")):
        return
    g.min("breite", m["breite"], s["breite_min"], bei_fehler, rs)
    g.max("format_abw", abs(m["format"]), s["format_tol"], bei_fehler, rs)
    g.max("delta_e", m["delta_e"], s["delta_e_max"], bei_fehler, rs)
    if m.get("ocr") is None:
        g.hinweis("ocr", False, text="OCR nicht verfuegbar (tesseract) – Text im Bild in 615 sichten")
    else:
        g.pruefe("ocr", m["ocr"] <= s["ocr_woerter_max"], m["ocr"], f"<= {s['ocr_woerter_max']}", bei_fehler, rs,
                 text=f"Text im Bild: {m['ocr']} Woerter" + (f" ({', '.join(m.get('ocr_beispiele', []))})"
                                                              if m["ocr"] else ""))
    g.min("motiv_hoehe", m["motiv_hoehe"], s["motiv_hoehe_min"], bei_fehler, rs)
    g.pruefe("zentrum", m["zentrum"] is not None and abs(m["zentrum"]) <= s["zentrum_tol"], m["zentrum"],
             f"+-{s['zentrum_tol']}", bei_fehler, rs)
    g.bereich("linien", m["linien"], s["linien_min"], s["linien_max"], bei_fehler, rs)
    for k in ("hoehe", "rand_rgb"):
        g.metrik(k, m.get(k))


# ------------------------------------------------------------------ Lauf
def _reihe_teil1(roh):
    reihe, teil = roh.get("reihe"), roh.get("teil")
    try:
        teil = int(teil)
    except (TypeError, ValueError):
        return None
    return f"{reihe}-1" if reihe and teil >= 2 else None


def uebernahme_150(roh):
    return str(roh.get("cover") or "").startswith("images/cover_source")


def run(werk, wer=None, modell=None, neu=False, motiv=None, bild=None, varianten=None, waehle=None,
        erbe=None, schwellen=None, trocken=False):
    wer = wer or "pipeline"
    from pipeline import bestellung, kette
    g = gate.Gate(werk, STAGE, ruecksprung="610", wer=wer)
    b = bestellung.lesen(werk)
    roh = b.roh
    usage_log.set_context(werk, STAGE)

    # Regler (persistent)
    if not trocken:
        k = {}
        if motiv is not None:
            k["motiv"] = motiv or None
        if erbe is not None:
            k["reihen_erbe"] = erbe
        if schwellen:
            k["schwellen"] = {**entscheidungen(werk).get("schwellen", {}), **schwellen}
        if k:
            entscheidung_setzen(werk, wer, **k)
    ents = entscheidungen(werk)
    s = {**SCHWELLEN, **(ents.get("schwellen") or {})}
    reg = roh.get("cover_regler") or {}
    modell = modell or reg.get("modell") or config.MODELS.get("image", "gemini-2.5-flash-image")
    quelle = kette.eingangsart(roh)
    mandant = b.mandant_art
    g.metrik("quelle", quelle)
    man = _json(manifest_pfad(werk)) or {}

    # 150 "Cover uebernehmen" -> 610 entfaellt
    if uebernahme_150(roh) and not bild and waehle is None:
        g.metrik("herkunft", "epub")
        if not trocken:
            status.entfaellt(werk, STAGE, "Cover aus 150 uebernommen (pruefen in 615)", wer=wer)
            manifest.json_atomar(manifest_pfad(werk), {"schema": 1, "stage": STAGE, "herkunft": "epub",
                                                       "datei": roh.get("cover"), "zeit": manifest.jetzt()},
                                 indent=2)
        g.ergebnis = {"ergebnis": "entfaellt", "gruende": [], "hinweise": [], "ruecksprung": None}
        return g

    # Vorgaenger + Autor
    z = status.zustand(werk, "600")
    if trocken:
        g.hinweis("gate_600", z in status.FREI, text=f"Gate 600: {z}")
    else:
        g.pflicht("gate_600", z in status.FREI, wert=z, ruecksprung="600", text=f"Gate 600 frei ({z})")
    autor = autor_name(werk, roh)
    eigene = (b.rechte or {}).get("art") == "eigene"
    if eigene and not autor:
        g.hinweis("autor", False, text="Autor unbekannt (rechte eigene) – Prompt ohne Autor")
    else:
        g.pflicht("autor", bool(autor), ruecksprung="150" if quelle not in ("gutenberg", "user_txt") else "110",
                  text="Autor (author.json name_display bzw. book.json autor_name) vorhanden")
    if g.fehler():
        g.entscheide(schreiben=not trocken)
        return g

    title = roh.get("titel_original") or werk
    motiv_txt = ents.get("motiv") or (roh.get("cover_motiv") or "").strip()
    prompt = prompt_bauen(title, autor, stimmung(werk), motiv_txt)
    eingang = manifest.hash_obj({"v": PROMPT_V, "prompt": prompt, "modell": modell, "aspect": COVER_ASPECT,
                                 "size": COVER_SIZE, "lauf": mock.modus()})
    pfad = bild_pfad(werk)
    bild_hash = manifest.hash_datei(pfad) if pfad else None
    versuche = []
    neu_erzeugt = 0
    herkunft = None
    rep = 0

    if trocken:
        if not pfad:
            g.pflicht("bild", False, text="Cover-Bild fehlt (Probe ohne Erzeugung)")
            g.entscheide(schreiben=False)
            return g
        herkunft = man.get("herkunft") or "bestand"
    elif varianten:
        vdir = os.path.join(img_dir(werk), "610_varianten")
        os.makedirs(vdir, exist_ok=True)
        liste = []
        for i in range(1, int(varianten) + 1):
            try:
                data, mime = generieren(prompt, modell, versuche)
            except NurText as e:
                liste.append({"nr": i, "datei": None, "nur_text": str(e)[:200]})
                continue
            vp = os.path.join(vdir, f"v{i}.{'jpg' if 'jpeg' in mime else 'png'}")
            with open(vp, "wb") as f:
                f.write(data)
            m = pruefen(vp)
            liste.append({"nr": i, "datei": os.path.relpath(vp, config.book_dir(werk)), "pruefung": m,
                          "rot": rot_liste(m, s)})
        man = {**man, "varianten": {"prompt": prompt, "modell": modell, "liste": liste, "versuche": versuche,
                                    "zeit": manifest.jetzt()}}
        manifest.json_atomar(manifest_pfad(werk), man, indent=2)
        g.metrik("varianten", len(liste))
        gruene = [v["nr"] for v in liste if v.get("datei") and not v["rot"]]
        g.pruefe("variante_waehlen", False, len(liste), None, "mensch", "610",
                 text=f"{len(liste)} Varianten erzeugt (gruen: {gruene or '-'}) – waehlen mit --waehle I")
        g.entscheide()
        g.aus = man
        return g
    elif waehle is not None:
        liste = ((man.get("varianten") or {}).get("liste")) or []
        v = next((x for x in liste if x["nr"] == int(waehle) and x.get("datei")), None)
        if not v:
            raise ValueError(f"--waehle {waehle}: Variante nicht vorhanden")
        pfad = _bild_kopieren(werk, os.path.join(config.book_dir(werk), v["datei"]))
        herkunft = "variante"
        entscheidung_setzen(werk, wer, variante=int(waehle))
    elif bild:
        if not os.path.exists(bild):
            raise ValueError(f"--bild {bild}: Datei fehlt")
        pfad = _bild_kopieren(werk, bild)
        herkunft = "upload"
        entscheidung_setzen(werk, wer, upload=os.path.basename(bild))
    else:
        teil1 = _reihe_teil1(roh)
        erbe_an = teil1 and ents.get("reihen_erbe", "an") != "aus"
        if erbe_an and not neu:
            q = bild_pfad(teil1)
            if not g.pflicht("erbe_teil1", bool(q), ruecksprung="610",
                             text=f"Illustration von Teil 1 ({teil1}) vorhanden"):
                g.entscheide()
                return g
            if not pfad or manifest.hash_datei(q) != bild_hash:
                pfad = _bild_kopieren(werk, q)
            herkunft = "erbe"
            g.metrik("erbe_von", teil1)
        elif (not neu and pfad and man.get("bild_hash") == bild_hash
              and (man.get("herkunft") in ("upload", "variante", "bestand", "erbe")
                   or (man.get("herkunft") == "erzeugt" and man.get("eingang_hash") == eingang))):
            herkunft = man["herkunft"]
        elif (not neu and pfad and not man.get("herkunft") and quelle == "gutenberg"
              and not ist_mock(pfad)):
            herkunft = "bestand"
            g.hinweis("bestand", False, text="Bestandsbild ohne Manifest uebernommen (Pruefung, kein Aufruf)")
        else:
            herkunft = "erzeugt"

        # Erzeugen bzw. Bestand rot -> 1x automatisch neu
        runden = 0
        while True:
            if herkunft == "erzeugt" and (runden or neu or not pfad or man.get("eingang_hash") != eingang
                                          or man.get("bild_hash") != bild_hash or man.get("herkunft") != "erzeugt"):
                try:
                    data, mime = generieren(prompt, modell, versuche)
                except NurText as e:
                    g.pflicht("bild", False, bei_fehler="mensch", ruecksprung="610",
                              text=f"Sperre 'nur Text' nach {VERSUCHE_TEXT} Anlaeufen – Motiv vorgeben "
                                   f"(--motiv) oder Bild hochladen: {str(e)[:160]}")
                    _manifest(werk, man, "erzeugt", prompt, modell, versuche, eingang, None, None, g)
                    g.entscheide()
                    return g
                pfad = _bild_schreiben(werk, data, mime)
                neu_erzeugt += 1
            m = pruefen(pfad)
            rot = rot_liste(m, s)
            if rot and herkunft in ("erzeugt", "bestand") and runden == 0:
                print(f"[610] Bildpruefung rot ({', '.join(rot)}) -> 1x automatisch neu")
                herkunft, runden, rep = "erzeugt", 1, 1
                continue
            break

    m = pruefen(pfad)
    bild_hash = manifest.hash_datei(pfad)
    g.metrik("herkunft", herkunft)
    g.metrik("modell", modell if herkunft == "erzeugt" else None)
    g.metrik("bild_erzeugt", neu_erzeugt)
    g.metrik("reparatur", rep)
    g.metrik("bild_hash", bild_hash)
    gate_bild(g, m, s)
    g.mock(1 if ist_mock(pfad) else 0, [os.path.basename(pfad)], ruecksprung="610")

    st = status.laden(werk)["stages"].get(STAGE) or {}
    mensch_gilt = st.get("zustand") == "frei" and (st.get("gate") or {}).get("ergebnis") == "mensch" \
        and (st.get("metriken") or {}).get("bild_hash") == bild_hash
    erzeugt_fuer_kunde = mandant in ("user", "verlag") and herkunft in ("erzeugt", "variante", "bestand")
    if mensch_gilt:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Bild unveraendert]"
        immer, grund = False, None
    elif erzeugt_fuer_kunde:
        immer, grund = True, f"Mandant {mandant}: erzeugtes Cover freigeben"
    else:
        immer, grund = False, None
    e = g.entscheide(mensch_immer=immer, mensch_grund=grund, schreiben=not trocken)
    if not trocken:
        _manifest(werk, man, herkunft, prompt if herkunft == "erzeugt" else man.get("prompt"),
                  modell if herkunft == "erzeugt" else man.get("modell"), versuche,
                  eingang if herkunft == "erzeugt" else man.get("eingang_hash"), pfad, bild_hash, g, m)
    return g


def _manifest(werk, alt, herkunft, prompt, modell, versuche, eingang, pfad, bild_hash, g, m=None):
    aus = {"schema": 1, "stage": STAGE, "herkunft": herkunft,
           "datei": os.path.relpath(pfad, config.book_dir(werk)) if pfad else None,
           "prompt": prompt, "modell": modell, "aspect": COVER_ASPECT, "size": COVER_SIZE,
           "prompt_v": PROMPT_V, "versuche": (alt.get("versuche") or [])[-20:] + versuche if versuche
           else alt.get("versuche") or [], "eingang_hash": eingang, "bild_hash": bild_hash,
           "pruefung": {"metriken": m, "ergebnis": (g.ergebnis or {}).get("ergebnis"),
                        "fehler": (g.ergebnis or {}).get("gruende"), "hinweise": (g.ergebnis or {}).get("hinweise"),
                        "zeit": manifest.jetzt()}}
    if alt.get("varianten"):
        aus["varianten"] = alt["varianten"]
    manifest.json_atomar(manifest_pfad(werk), aus, indent=2)
    g.aus = aus


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 610 Cover (Illustration)")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--modell")
    ap.add_argument("--neu", action="store_true", help="Illustration neu erzeugen (Kosten!)")
    ap.add_argument("--force", action="store_true", help=argparse.SUPPRESS)      # Alt-Aufruf Cockpit = --neu
    ap.add_argument("--motiv", metavar="TEXT", help="Motiv vorgeben, englisch ('' = zuruecksetzen)")
    ap.add_argument("--bild", metavar="DATEI", help="eigenes Bild als Illustration")
    ap.add_argument("--varianten", type=int, metavar="N", help="N Varianten zur Auswahl erzeugen (Kosten!)")
    ap.add_argument("--waehle", type=int, metavar="I", help="Variante I uebernehmen")
    ap.add_argument("--erbe", choices=["an", "aus"], help="Reihen-Erbe (Bild von Teil 1)")
    ap.add_argument("--schwelle", action="append", metavar="NAME=WERT", help=f"Schwellen: {', '.join(SCHWELLEN)}")
    ap.add_argument("--trocken", action="store_true", help="vorhandenes Bild nur pruefen, nichts schreiben")
    a = ap.parse_args(argv)
    schw = {}
    for x in a.schwelle or []:
        try:
            n, v = x.split("=", 1)
            if n not in SCHWELLEN:
                raise ValueError
            schw[n] = float(v)
        except ValueError:
            print(f"[610] --schwelle {x!r}: Format NAME=WERT, Namen {', '.join(SCHWELLEN)}")
            return 1
    try:
        if (a.motiv is not None or a.bild or a.waehle is not None or a.erbe or schw) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "override" if schw else "entscheiden", a.wer or "pipeline")
        g = run(a.werk, a.wer, a.modell, a.neu or a.force, a.motiv, a.bild, a.varianten, a.waehle, a.erbe,
                schw or None, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[610] Fehler: {e}")
        return 1
    if g.ergebnis.get("ergebnis") == "entfaellt":
        print("[610] entfaellt: Cover aus 150 uebernommen")
        return 0
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    raise SystemExit(main())
