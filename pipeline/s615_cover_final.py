"""STAGE 615 — Cover final (je Sprache x Variante)
Funktion:     Fertiges Cover aus der Illustration (610) + Titel je Sprache + Autor + Pflichtvermerke + Imprint
              (+ Sprecherzeile bei der Audio-Variante). Kein EPUB; 620/630/650 uebernehmen die Dateien.
Varianten:    text    jede Sprache der Bestellung (Ausgangssprache + Zielsprachen), 1000x1500
              audio   Sprache mit Hoerbuch/Hoerspiel, Sprecherzeile aus casting.json (Freigabe 410), 1000x1500
              quadrat Sprache mit Kanal extern, 3000x3000 (Illustration mittig, Typo neu gesetzt)
              Cover aus 150 ("uebernehmen", book.json cover = images/cover_source.*) wird nicht ueberzeichnet,
              nur eingepasst und geprueft.
Komponenten:  pipeline/s615_cover_final.py (Komposition, vorher s620 _compose_cover_raster/_gather_meta)
Eingang:      images/cover.* (610, Gate 610 frei) bzw. Cover aus 150; book.json fassungen[].titel/titel_quelle
              (110 bzw. 310 ePub-Weg), titel_original; author.json name_display[_<lg>] (110) bzw. book.json
              autor_name (150), Pflicht ausser rechte eigene; work/600_klappentext.json vermerke (115/195;
              altes Format -> aus Bestellung); casting.json (410); Imprint aus Mandant (080); Fonts assets/fonts
Ausgabe:      fassungen/<lg>/output/cover_final_<lg>.jpg | _audio.jpg | _quadrat.jpg;
              work/615_cover_final.json Manifest je Sprache x Variante (Eingangs-Hash, Ausgabe-Hash, Layout,
              Pruefung); Regler work/615_entscheidungen.json
Gate:         je Sprache x Variante (status teile "<lg>:<variante>"): Titel vorhanden, Titelquelle 110/310
              (Fallback titel_original bzw. titel_pruefen -> Mensch); Autor; Vermerke 100 %; Titel <= 4 Zeilen,
              Schrift >= 48 pt, Titel passt in die Breite; Ueberlappung Titelkasten/Motiv <= 5 %; Masse exakt.
              Stopp: Gate 610 nicht frei, Font fehlt, Autor fehlt, Sprecher fehlt (Audio), Mock im Live-Lauf.
              Sichtfreigabe einmal je Werk (--freigeben); danach Folgevarianten und Aenderungen auto bei gruen;
              Reihenteile >= 2 auto bei gruen. Mensch-Freigabe einer Variante gilt bei gleichem ausgabe_hash.
Kosten:       0 $ (Pillow, CPU).
Abnehmer:     s620/s630 (ePub), s650 (Hoerbuch extern), Cockpit, tools/export_demo.py (= 710 Ziel Lokal).

Aufruf:  py -3.11 -m pipeline.s615_cover_final <werk> [--titel LG=TEXT] [--umbruch LG=A|B] [--schrift PT]
         [--position oben|unten] [--transparenz 0..1] [--sprecher an|aus] [--vermerke an|aus] [--neu]
         [--freigeben] [--trocken]
"""
import argparse
import hashlib
import io
import json
import os
import re

from config import config
from pipeline import bestellung, gate, manifest, mock, status

STAGE = "615"
LAYOUT_V = 1
W, H = 1000, 1500
QUADRAT = 3000
BG_COLOR = getattr(config, "COVER_BG", "#faf8f4")
TITLE_COLOR = "#9e3324"                      # patiniertes Zinnoberrot
FONT_DIR = os.path.join(config.BASE_DIR, "assets", "fonts")
FONTS = {"bold": "DejaVuSerif-Bold.ttf", "reg": "DejaVuSerif.ttf", "ital": "DejaVuSerif-Italic.ttf"}
SCHRIFTEN = (84, 72, 64, 56, 48)
SCHWELLEN = {"zeilen_max": 4, "schrift_min": 48, "ueberlappung_max": 0.05}
VARIANTEN = ("text", "audio", "quadrat")
TINTE = 60                                   # RGB-Abstand zu COVER_BG = Motivpixel (wie 610)
TITEL_FALLBACK = ("", "original")            # titel_quelle, die fuer eine Zielsprache nicht reicht

LANG_LABEL = {"en": "English Edition", "de": "Deutsche Ausgabe", "fr": "Édition française",
              "es": "Edición española", "it": "Edizione italiana"}
GELESEN = {"de": "Gelesen von", "en": "Read by", "fr": "Lu par", "es": "Leído por", "it": "Letto da"}
KI = {"de": "KI-Stimme", "en": "AI voice", "fr": "voix IA", "es": "voz IA", "it": "voce IA"}


# ------------------------------------------------------------------ Pfade / Ablage
def ausgabe_pfad(werk, lg, variante):
    zus = "" if variante == "text" else f"_{variante}"
    return os.path.join(config.book_dir(werk), "fassungen", lg, "output", f"cover_final_{lg}{zus}.jpg")


def manifest_pfad(werk):
    return config.work_path(werk, "615_cover_final")


def _json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def entscheidungen(werk):
    return _json(config.work_path(werk, "615_entscheidungen")) or {}


def entscheidung_setzen(werk, wer, **kw):
    d = entscheidungen(werk)
    d.setdefault("protokoll", [])
    for k, v in kw.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    d["protokoll"].append({"wer": wer, "wann": manifest.jetzt(), **kw})
    manifest.json_atomar(config.work_path(werk, "615_entscheidungen"), d, indent=2)
    return d


# ------------------------------------------------------------------ Eingaenge
def illustration(werk, roh):
    """(pfad, herkunft): Cover aus 150 ('uebernahme') oder Illustration 610 ('610')."""
    from pipeline import s610_cover
    if s610_cover.uebernahme_150(roh):
        p = os.path.join(config.book_dir(werk), roh["cover"])
        return (p if os.path.exists(p) else None), "uebernahme"
    return s610_cover.bild_pfad(werk), "610"


def titel(roh, lg, quellsprache):
    """-> (titel, quelle, fallback, pruefen). Kein stiller Rueckfall: fallback=True -> Mensch."""
    f = next((x for x in roh.get("fassungen") or [] if isinstance(x, dict) and x.get("sprache") == lg), {})
    t, q = (f.get("titel") or "").strip(), (f.get("titel_quelle") or "").strip()
    orig = (roh.get("titel_original") or "").strip()
    if t:
        fb = lg != quellsprache and q in TITEL_FALLBACK
        return t, q or "?", fb, bool(f.get("titel_pruefen"))
    if lg == quellsprache and orig:
        return orig, "original", False, False
    return orig, "fallback_original", True, False


def autor(werk, roh, lg):
    from pipeline import s610_cover
    try:
        slug = config.author_of(werk)
    except Exception:
        slug = roh.get("author_slug") or ""
    if slug:
        a = _json(os.path.join(config.author_dir(slug), "author.json")) or {}
        n = (a.get(f"name_display_{lg}") or "").strip()
        if n:
            return re.sub(r"\s*\([^)]*\)", "", n).strip()
    n = s610_cover.autor_name(werk, roh)
    return re.sub(r"\s*\([^)]*\)", "", n).strip()


def vermerke(werk, b, lg, an=True):
    """Pflichtvermerke je Sprache: (liste, soll, quelle). Quelle 600 (vermerke), altes Format -> Bestellung."""
    from pipeline.s600_klappentext import VERMERKE
    if not an:
        return [], [], "aus"
    soll = []
    if b.fassung == "modernisiert":
        soll.append("modernisiert")
    teil, ges = b.roh.get("teil"), b.roh.get("teile_gesamt")
    if teil and ges:
        soll.append("teil")
    k = (_json(config.work_path(werk, "600_klappentext")) or {}).get("vermerke")
    out, quelle = [], "600"
    for art in soll:
        t = (((k or {}).get(art) or {}).get(lg) or "").strip()
        if not t:
            quelle = "bestellung"
            t = VERMERKE[art].get(lg, VERMERKE[art]["en"])
            t = t.format(x=teil, y=ges) if art == "teil" else t
        out.append(t)
    return out, soll, quelle if soll else "-"


def sprecher(werk, lg):
    from pipeline import s410_casting
    st = s410_casting.stimme(werk, lg)
    return f"{GELESEN.get(lg, 'Read by')} {st} · {KI.get(lg, 'AI voice')}" if st else ""


def varianten(b):
    """[(lg, variante)] laut Bestellung."""
    audio = set(b.audiosprachen())
    out = []
    for lg in b.sprachen:
        out.append((lg, "text"))
        if lg in audio:
            out.append((lg, "audio"))
        if b.hat(sprache=lg, kanal="extern"):
            out.append((lg, "quadrat"))
    return out


# ------------------------------------------------------------------ Komposition
def fonts_fehlen():
    return [n for n in FONTS.values() if not os.path.exists(os.path.join(FONT_DIR, n))]


def _font(stil, groesse):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(FONT_DIR, FONTS[stil]), int(groesse))


def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _breite(d, s, f):
    bb = d.textbbox((0, 0), s, font=f)
    return bb[2] - bb[0]


def umbrechen(d, text, f, breite):
    zeilen, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if not cur or _breite(d, t, f) <= breite:
            cur = t
        else:
            zeilen.append(cur)
            cur = w
    if cur:
        zeilen.append(cur)
    return zeilen


def titel_setzen(d, text, breite, k=1, schrift=None, umbruch=None, zeilen_max=4):
    """-> (zeilen, schrift_pt, passt). Groesste Schrift mit <= zeilen_max Zeilen, die in die Breite passt."""
    groessen = [schrift] if schrift else list(SCHRIFTEN)
    zeilen = None
    for pt in groessen:
        f = _font("bold", pt * k)
        zeilen = [z.strip() for z in umbruch.split("|") if z.strip()] if umbruch else umbrechen(d, text, f, breite)
        passt = all(_breite(d, z, f) <= breite for z in zeilen)
        if passt and len(zeilen) <= zeilen_max:
            return zeilen, pt, True
    return zeilen, groessen[-1], all(_breite(d, z, _font("bold", groessen[-1] * k)) <= breite for z in zeilen)


def _grundbild(ill, w, h):
    from PIL import Image
    bg = _rgb(BG_COLOR)
    if not ill:
        return Image.new("RGBA", (w, h), (*bg, 255))
    with Image.open(ill) as im:
        base = im.convert("RGBA")
    s = max(w / base.width, h / base.height)                       # cover/slice auf 2:3
    base = base.resize((max(w, round(base.width * s)), max(h, round(base.height * s))))
    l, t = (base.width - w) // 2, (base.height - h) // 2
    return base.crop((l, t, l + w, t + h))


def _tinte(base):
    import numpy as np
    a = np.asarray(base.convert("RGB"), dtype=float)
    return np.sqrt(((a - np.array(_rgb(BG_COLOR), dtype=float)) ** 2).sum(axis=2)) > TINTE


def komponieren(ill, text, autor_, lg, vermerke_, sprecher_, imprint, lay=None, k=1):
    """Cover 1000k x 1500k. -> (PIL.Image RGB, layout-dict)."""
    from PIL import Image, ImageDraw
    lay = lay or {}
    w, h = W * k, H * k
    C, bg = _rgb(TITLE_COLOR), _rgb(BG_COLOR)
    base = _grundbild(ill, w, h)
    tinte = _tinte(base)
    d = ImageDraw.Draw(base)
    alpha = float(lay.get("transparenz", 0.55))

    def scrim(box):
        x0, y0, x1, y1 = (int(v) for v in box)
        ov = Image.new("RGBA", (max(1, x1 - x0), max(1, y1 - y0)), (*bg, int(255 * alpha)))
        base.alpha_composite(ov, (x0, max(0, y0)))

    def mitte(y, s, f):
        d.text((w / 2 - _breite(d, s, f) / 2, y), s, font=f, fill=C)

    breite = w - 140 * k
    zeilen, pt, passt = titel_setzen(d, text, breite, k, lay.get("schrift"), lay.get("umbruch"))
    fb = _font("bold", pt * k)
    lh = int(pt * k * 1.12)
    fv = _font("ital", 30 * k)
    vz = [z for v in vermerke_ for z in umbrechen(d, v, fv, breite)]
    vh = int(30 * k * 1.3)
    kasten_h = len(zeilen) * lh + (len(vz) * vh + 12 * k if vz else 0) + 40 * k
    top = 70 * k if lay.get("position", "oben") == "oben" else 1130 * k - kasten_h + 10 * k
    kasten = (40 * k, top - 10 * k, w - 40 * k, top - 10 * k + kasten_h)
    fuss = (40 * k, 1150 * k, w - 40 * k, 1430 * k)
    gesamt = int(tinte.sum()) or 1

    def anteil(box):
        x0, y0, x1, y1 = (max(0, int(v)) for v in box)
        return round(float(tinte[y0:y1, x0:x1].sum()) / gesamt, 4)

    scrim(kasten)
    for i, z in enumerate(zeilen):
        d.text((70 * k, top + i * lh), z, font=fb, fill=C)
    y = top + len(zeilen) * lh + 12 * k
    for z in vz:
        d.text((70 * k, y), z, font=fv, fill=C)
        y += vh

    scrim(fuss)
    if autor_:
        mitte(1170 * k, autor_, _font("reg", 44 * k))
    label = LANG_LABEL.get(lg)
    if label:
        mitte(1236 * k, label, _font("ital", 28 * k))
    if sprecher_:
        sf = 28
        while _breite(d, sprecher_, _font("ital", sf * k)) > w - 140 * k and sf > 18:
            sf -= 2
        mitte(1278 * k, sprecher_, _font("ital", sf * k))
    if imprint:
        mitte(1340 * k, imprint, _font("reg", 32 * k))
    return base.convert("RGB"), {"zeilen": len(zeilen), "titel_zeilen": zeilen, "schrift": pt, "passt": passt,
                                 "ueberlappung": anteil(kasten), "ueberlappung_fuss": anteil(fuss),
                                 "vermerke": list(vermerke_), "sprecher": sprecher_, "position":
                                     lay.get("position", "oben"), "transparenz": alpha}


def quadrat(bild_2x):
    """2000x3000-Komposition mittig auf 3000x3000 COVER_BG."""
    from PIL import Image
    q = Image.new("RGB", (QUADRAT, QUADRAT), _rgb(BG_COLOR))
    q.paste(bild_2x, ((QUADRAT - bild_2x.width) // 2, (QUADRAT - bild_2x.height) // 2))
    return q


def einpassen(pfad, w, h):
    """Cover aus 150 ohne Ueberzeichnen auf w x h (contain, Rand COVER_BG)."""
    from PIL import Image
    with Image.open(pfad) as im:
        im = im.convert("RGB")
        s = min(w / im.width, h / im.height)
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))))
        out = Image.new("RGB", (w, h), _rgb(BG_COLOR))
        out.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
        return out, {"quelle_px": None}


def _h(data):
    return hashlib.sha256(data).hexdigest()


def _jpeg(im):
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


# ------------------------------------------------------------------ Lauf
def _ruecksprung_titel(quelle, lg, b):
    if lg == b.quellsprache:
        return "110" if quelle == "gutenberg" else "150"
    return "110" if quelle == "gutenberg" else "310"


def run(werk, wer=None, neu=False, titel_neu=None, umbruch=None, schrift=None, position=None,
        transparenz=None, sprecher_an=None, vermerke_an=None, freigeben=False, trocken=False, nur=None):
    """titel_neu/umbruch: {lg: text}. -> Liste der Gates (je Sprache x Variante)."""
    from pipeline import kette, s610_cover
    wer = wer or "pipeline"
    b = bestellung.lesen(werk)
    roh = b.roh

    # Regler (persistent); Titel manuell -> book.json zurueck
    if not trocken:
        if titel_neu:
            fass = [dict(f) for f in roh.get("fassungen") or [] if isinstance(f, dict)]
            for lg, t in titel_neu.items():
                e = next((f for f in fass if f.get("sprache") == lg), None)
                if not e:
                    e = {"sprache": lg}
                    fass.append(e)
                e.update(titel=t.strip(), titel_quelle="manuell", titel_pruefen=False)
            bestellung.feld_setzen(werk, fassungen=fass)
            b = bestellung.lesen(werk)
            roh = b.roh
        k = {}
        if umbruch:
            k["umbruch"] = {**entscheidungen(werk).get("umbruch", {}), **umbruch}
        for n, v in (("schrift", schrift), ("position", position), ("transparenz", transparenz),
                     ("sprecher", sprecher_an), ("vermerke", vermerke_an)):
            if v is not None:
                k[n] = v
        if k:
            entscheidung_setzen(werk, wer, **k)
    ents = entscheidungen(werk)
    if freigeben and not trocken:
        return _freigeben(werk, wer)

    quelle = kette.eingangsart(roh)
    ill, herkunft = illustration(werk, roh)
    z610 = status.zustand(werk, "610")
    teil = roh.get("teil")
    try:
        reihe_folge = bool(roh.get("reihe")) and int(teil) >= 2
    except (TypeError, ValueError):
        reihe_folge = False
    eigene = (b.rechte or {}).get("art") == "eigene"
    from pipeline import s080_mandant
    imprint = s080_mandant.imprint(werk, b)
    man = _json(manifest_pfad(werk)) or {}
    eintraege = dict(man.get("varianten") or {})
    d = status.laden(werk)
    st = d["stages"].get(STAGE) or {}
    werk_frei = bool(ents.get("sichtfreigabe")) or any(
        t.get("zustand") == "frei" and (t.get("gate") or {}).get("ergebnis") == "mensch"
        for t in (st.get("teile") or {}).values())
    lay_basis = {n: ents[n] for n in ("schrift", "position", "transparenz") if n in ents}
    gates = []

    for lg, var in varianten(b):
        if nur and lg not in nur:
            continue
        scope = f"{lg}:{var}"
        g = gate.Gate(werk, STAGE, scope=scope, ruecksprung="615", wer=wer)
        g.metrik("herkunft", herkunft)
        g.metrik("variante", var)

        # Vorgaenger / Eingaenge (Stopp)
        if herkunft == "610":
            ok610 = z610 in status.FREI
            if trocken:
                g.hinweis("gate_610", ok610, z610, text=f"Gate 610: {z610}")
            else:
                g.pflicht("gate_610", ok610, z610, ruecksprung="610", text=f"Gate 610 frei ({z610})")
        g.pflicht("illustration", bool(ill), ruecksprung="610" if herkunft == "610" else "150",
                  text=f"Illustration vorhanden ({herkunft})")
        if herkunft == "610":
            fe = fonts_fehlen()
            g.pflicht("fonts", not fe, fe or None, text=f"Fonts assets/fonts mitgeliefert ({', '.join(fe) or 'ok'})")
        sp = ""
        if var == "audio" and ents.get("sprecher", "an") != "aus":
            sp = sprecher(werk, lg)
            if not sp and status.zustand(werk, "410") not in status.FREI:
                print(f"[615] {scope}: wartet auf Freigabe 410 (Sprecher) – uebersprungen")
                continue
            g.pflicht("sprecher", bool(sp), ruecksprung="410", text="Sprecher aus casting.json (Freigabe 410)")
        elif var == "audio":
            g.hinweis("sprecher", False, text="Sprecherzeile aus (Regler)")
        t, tq, t_fb, t_pr = titel(roh, lg, b.quellsprache)
        rs_t = _ruecksprung_titel(quelle, lg, b)
        g.pflicht("titel", bool(t), ruecksprung=rs_t, text=f"Titel {lg} vorhanden")
        au = autor(werk, roh, lg)
        if eigene and not au:
            g.hinweis("autor", False, text="Autor unbekannt (rechte eigene) – Cover ohne Autorzeile")
        else:
            g.pflicht("autor", bool(au), ruecksprung="110" if quelle == "gutenberg" else "150",
                      text="Autor (author.json bzw. book.json autor_name) vorhanden")
        if g.fehler():
            g.entscheide(schreiben=not trocken)
            gates.append(g)
            continue

        g.metrik("titel", t)
        g.metrik("titel_quelle", tq)
        g.pruefe("titel_quelle", not t_fb, tq, "110/310", "mensch", rs_t,
                 text=f"Titelquelle {lg}: {tq}" + (" (Rueckfall titel_original)" if t_fb else ""))
        g.pruefe("titel_pruefen", not t_pr, None, None, "mensch", rs_t,
                 text=f"Titel {lg} '{t}' zur Pruefung markiert ({tq})")
        vm, soll, vq = vermerke(werk, b, lg, ents.get("vermerke", "an") != "aus")
        if vq == "bestellung":
            g.hinweis("vermerke_600", False, text="Vermerke aus 600 fehlen (altes Format) – aus Bestellung gesetzt")
        if vq == "aus":
            g.hinweis("vermerke", False, text="Vermerke aus (Admin)")

        # Komposition
        lay = {**lay_basis, "umbruch": (ents.get("umbruch") or {}).get(lg)}
        if herkunft == "uebernahme":
            im, L = einpassen(ill, *((QUADRAT, QUADRAT) if var == "quadrat" else (W, H)))
            L = {"uebernahme": True}
        elif var == "quadrat":
            im2, L = komponieren(ill, t, au, lg, vm, sp, imprint, lay, k=2)
            im = quadrat(im2)
        else:
            im, L = komponieren(ill, t, au, lg, vm, sp, imprint, lay)
        soll_px = (QUADRAT, QUADRAT) if var == "quadrat" else (W, H)
        data = _jpeg(im)
        ausgabe_hash = _h(data)
        eingang = manifest.hash_obj({"v": LAYOUT_V, "ill": manifest.hash_datei(ill), "titel": t, "autor": au,
                                     "vermerke": vm, "sprecher": sp, "imprint": imprint, "lay": lay, "var": var})

        # Gate
        g.gleich("masse", list(im.size), list(soll_px))
        if herkunft == "uebernahme":
            from PIL import Image
            with Image.open(ill) as q:
                qw, qh = q.size
            g.hinweis("uebernahme_format", abs(qw / qh - 2 / 3) <= 0.02 * 2 / 3, round(qw / qh, 3),
                      text=f"Cover aus 150: Format {qw}x{qh} (2:3 +-2 %)")
            g.hinweis("uebernahme_breite", qw >= 1000, qw, text=f"Cover aus 150: Breite {qw} px (>= 1000)")
        else:
            g.max("titel_zeilen", L["zeilen"], SCHWELLEN["zeilen_max"], ruecksprung="615")
            g.min("titel_schrift", L["schrift"], SCHWELLEN["schrift_min"], ruecksprung="615")
            g.pruefe("titel_breite", L["passt"], None, None, "mensch", "615",
                     text="Titel passt in die Breite (sonst Umbruch manuell: --umbruch LG=A|B)")
            g.max("ueberlappung", L["ueberlappung"], SCHWELLEN["ueberlappung_max"], ruecksprung="610")
            g.metrik("ueberlappung_fuss", L["ueberlappung_fuss"])
            g.pruefe("vermerke", len(L["vermerke"]) == len(soll) or vq == "aus", len(L["vermerke"]),
                     len(soll), "mensch", "115", text=f"Pflichtvermerke {len(L['vermerke'])}/{len(soll)}")
        g.mock(1 if s610_cover.ist_mock(ill) else 0, [os.path.basename(ill)], ruecksprung="610")
        g.metrik("ausgabe_hash", ausgabe_hash)
        g.metrik("eingang_hash", eingang)

        # Entscheidung: Sichtfreigabe einmal je Werk
        alt = (st.get("teile") or {}).get(scope) or {}
        mensch_gilt = alt.get("zustand") == "frei" and (alt.get("gate") or {}).get("ergebnis") == "mensch" \
            and (alt.get("metriken") or {}).get("ausgabe_hash") == ausgabe_hash
        if mensch_gilt:
            for p in g.pruefungen:
                if not p["ok"] and p["bei_fehler"] == "mensch":
                    p["bei_fehler"] = "hinweis"
                    p["text"] += " [Mensch-Freigabe gilt, Cover unveraendert]"
            immer, grund = False, None
        elif werk_frei or reihe_folge:
            immer, grund = False, None
        else:
            immer, grund = True, "Sichtfreigabe Cover (einmal je Werk, alle Sprachen): --freigeben"
        e = g.entscheide(mensch_immer=immer, mensch_grund=grund, schreiben=not trocken)
        pfad = ausgabe_pfad(werk, lg, var)
        if not trocken and e != "stopp":
            alt_hash = None
            if os.path.exists(pfad):
                with open(pfad, "rb") as f:
                    alt_hash = _h(f.read())
            if neu or alt_hash != ausgabe_hash:
                os.makedirs(os.path.dirname(pfad), exist_ok=True)
                tmp = pfad + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, pfad)
            eintraege[scope] = {"datei": os.path.relpath(pfad, config.book_dir(werk)), "sprache": lg,
                                "variante": var, "eingang_hash": eingang, "ausgabe_hash": ausgabe_hash,
                                "titel": t, "titel_quelle": tq, "autor": au, "vermerke": vm, "sprecher": sp,
                                "imprint": imprint, "layout": dict(L),
                                "pruefung": {"ergebnis": e, "gruende": g.ergebnis["gruende"],
                                             "hinweise": g.ergebnis["hinweise"], "zeit": manifest.jetzt()}}
        g.aus = {"datei": pfad, "layout": L, "bild": im}
        gates.append(g)

    if not trocken:
        manifest.json_atomar(manifest_pfad(werk), {"schema": 1, "stage": STAGE, "layout_v": LAYOUT_V,
                                                   "herkunft": herkunft, "varianten": eintraege,
                                                   "zeit": manifest.jetzt()}, indent=2)
    return gates


def _freigeben(werk, wer):
    """Sichtfreigabe einmal je Werk: alle Varianten im Zustand mensch -> frei."""
    d = status.laden(werk)
    teile = ((d["stages"].get(STAGE) or {}).get("teile") or {})
    offen = [s for s, t in teile.items() if t.get("zustand") == "mensch"]
    for s in offen:
        status.entscheiden(werk, STAGE, "frei", wer=wer, grund="Sichtfreigabe Cover 615", scope=s)
    entscheidung_setzen(werk, wer, sichtfreigabe={"wer": wer, "wann": manifest.jetzt(), "teile": offen})
    print(f"[615] Sichtfreigabe: {', '.join(offen) or 'nichts offen'}")
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 615 Cover final")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--titel", action="append", metavar="LG=TEXT", help="Titel je Sprache manuell (book.json)")
    ap.add_argument("--umbruch", action="append", metavar="LG=A|B", help="Titel-Umbruch manuell ('' = auto)")
    ap.add_argument("--schrift", type=int, metavar="PT", help="Titel-Schriftgroesse fest")
    ap.add_argument("--position", choices=["oben", "unten"])
    ap.add_argument("--transparenz", type=float, metavar="0..1", help="Deckkraft Titelkasten")
    ap.add_argument("--sprecher", choices=["an", "aus"])
    ap.add_argument("--vermerke", choices=["an", "aus"], help="nur Admin")
    ap.add_argument("--sprache", action="append", metavar="LG", help="nur diese Sprache(n)")
    ap.add_argument("--neu", action="store_true", help="Varianten neu schreiben")
    ap.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--freigeben", action="store_true", help="Sichtfreigabe (einmal je Werk)")
    ap.add_argument("--trocken", action="store_true", help="nur pruefen, nichts schreiben")
    ap.add_argument("--lang", help=argparse.SUPPRESS)                       # Alt-Aufruf
    a = ap.parse_args(argv)

    def paare(xs, name):
        out = {}
        for x in xs or []:
            if "=" not in x:
                raise ValueError(f"--{name} {x!r}: Format LG=TEXT")
            lg, v = x.split("=", 1)
            out[lg.strip().lower()] = v
        return out

    try:
        titel_neu, umb = paare(a.titel, "titel"), paare(a.umbruch, "umbruch")
        umb = {k: (v or None) for k, v in umb.items()}
        if a.transparenz is not None and not 0 <= a.transparenz <= 1:
            raise ValueError("--transparenz 0..1")
        if not a.trocken and (titel_neu or umb or a.schrift or a.position or a.transparenz is not None
                              or a.sprecher or a.vermerke or a.freigeben):
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "override" if a.vermerke else "entscheiden", a.wer or "pipeline")
        nur = a.sprache or (a.lang.split(",") if a.lang else None)
        gates = run(a.werk, a.wer, a.neu or a.force, titel_neu or None, umb or None, a.schrift, a.position,
                    a.transparenz, a.sprecher, a.vermerke, a.freigeben, a.trocken, nur)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[615] Fehler: {e}")
        return 1
    if a.freigeben:
        return 0
    for g in gates:
        print(f"--- {g.scope}")
        print(g.bericht())
    return gate.EXIT[gate.gesamt([g.ergebnis["ergebnis"] for g in gates])] if gates else 0


if __name__ == "__main__":
    raise SystemExit(main())
