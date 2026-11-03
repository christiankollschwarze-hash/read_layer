"""STAGE 600 — Klappentext (Umbau Phase 2, GATE_KATALOG.md Zeile 600, 03.11.2026)
Funktion:     Metadaten + Klappentext je Ausgangssprache und bestellter Zielsprache, Pflichtvermerke, Gate.
Wirkungsweise: Modus aus Quellprofil: *Uebernehmen* = Klappentext aus 150 (book.json klappentext, HTML gesaeubert,
              woertlich, satzweise, nur in Zielsprachen uebersetzt; Herkunft epub; Mandant verlag nur so);
              *Erzeugen* = Metadaten aus raw_modernized.txt (Anfang + Mitte) und Bloecke Einordnung/Autor in allen
              Sprachen (Autor-Block nur aus author.json). In beiden Modi Metadaten aus dem Text (Genre aus fester
              Liste -> Gruppe fuer 640, Ton, Hauptfiguren, hauptfigur_geschlecht, Essenz, Koeder-Passage).
              Koeder (Erzeugen) = Passage des Werks: Ausgangssprache aus dem Werktext, Zielsprachen = dieselben
              Knoten aus 330 (nie frei uebersetzt). Vermerke "Sanft modernisierte Fassung" (fassung modernisiert)
              und "Teil X von Y" (teil/teile_gesamt) als feste Saetze je Sprache. Markup wird entfernt.
              Eingangs-Hash: unveraenderte Eingaenge -> kein LLM-Aufruf (0 $).
Eingang:      book.json (quellsprache, Bestellung, fassung, teil/teile_gesamt, Mandant, quelle, klappentext aus 150),
              raw_modernized.txt (190), work/330_rueckuebersetzung.json (Gate 330 frei, bei bestellter Uebersetzung),
              author.json (110 bzw. 150), work/600_entscheidungen.json (manuelle Regler).
Ausgabe:      work/600_klappentext.json als einzige Ablage {modus, herkunft, sprachen, autor, wirkungssprache,
              meta {genre, genre_gruppe, ton, hauptfiguren, hauptfigur_geschlecht, essenz, leseprobe_zitat, koeder_ids,
              sicherheit, herkunft, ...}, blurb {koeder, einordnung, autor: [{lg: satz}]}, vermerke {art: {lg: satz}},
              pruefung, roh (LLM-Ergebnis), eingang_hash}.
Gate:         je Sprache Pflicht: Bloecke vollstaendig (Erzeugen 3 Bloecke, Autor-Block entfaellt bei rechte eigene;
              Uebernehmen Block Einordnung), Sprache je Satz = Zielsprache, keine Kopie der Ausgangssprache,
              Lizenztext = 0, Markup = 0, Koeder woertlich im Werktext (190 bzw. 330), Pflichtvermerke.
              Sprache/Kopie -> 1x automatisch nachuebersetzen; Lizenz/leer/Markup/Koeder -> 1x automatisch neu;
              danach Mensch (Koeder in Zielsprache -> 310). Autor-Fakten (Jahreszahlen, Namen/Orte) nicht in
              author.json -> Mensch (110); sicherheit pruefen, Edition-Verdacht -> Mensch; Genre unbekannt
              (Gruppe Sonstiges), hauptfigur_geschlecht unklar, Laenge > 1.200 Zeichen -> Hinweis. Erzeugen bei
              User-ePub -> immer Mensch; Mandant verlag -> immer Mensch, Klappentext fehlt -> Stopp (150).
              Quelltext fehlt, Gate 190 bzw. 330 nicht frei -> Stopp. Mock im Live-Lauf -> Stopp.
              Mensch-Freigabe gilt bei gleichem ausgabe_hash.
Kosten:       usage_log Stage 600 (2 Aufrufe deepseek, ~0,3 ct je Werk).
Regler:       --modus uebernehmen|erzeugen, --modell, --neu, --koeder TEXT (Passage im Werktext waehlen),
              --genre WERT, --geschlecht weiblich|maennlich|unklar, --ersetzen BLOCK:I:LG=TEXT (Satz manuell),
              --block-neu BLOCK (Block neu erzeugen), --laenge-max 1200, --vermerke an|aus (nur Admin),
              --trocken (Probe ohne LLM, nichts schreiben). Persistente Regler in work/600_entscheidungen.json.
Aufruf:       python -m pipeline.s600_klappentext <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, gate, manifest, mock, status, usage_log
from pipeline import klappentext_pruefung as KP

STAGE = "600"
PROMPT_V = 2
HEAD_CHARS = 12000
MID_CHARS = 6000
LAENGE_MAX = 1200
KOEDER_MAX_KNOTEN = 5

VERMERKE = {
    "modernisiert": {"en": "Gently modernized edition.", "de": "Sanft modernisierte Fassung.",
                     "es": "Edición suavemente modernizada.", "fr": "Version légèrement modernisée.",
                     "it": "Edizione delicatamente modernizzata."},
    "teil": {"en": "Part {x} of {y}.", "de": "Teil {x} von {y}.", "es": "Parte {x} de {y}.",
             "fr": "Partie {x} sur {y}.", "it": "Parte {x} di {y}."},
}

# Feste Genre-Liste (claude/PROZESS_klappentext_erzaehler.md, Abschnitt 2) -> Gruppe (fuer 640 Erzaehlerwahl)
GENRES = {
    "Märchen & Fabel": "Märchen, Volksmärchen, Fabeln",
    "Liebe": "Romanze, Romance, Liebesroman, Historische Romanze",
    "Bühne": "Drama, Tragödie, Theaterstück, Komödie",
    "Krimi": "Krimi, Kriminalroman, Kriminalliteratur, Kriminalgeschichte, Thriller, Spionageroman, True Crime",
    "Abenteuer": "Abenteuerroman, Abenteuer, Western",
    "Science-Fiction": "Science-Fiction, Science-Fantasy",
    "Horror": "Horror, Horrorgeschichte, Schauerliteratur, Geistergeschichte",
    "Roman allgemein": "Roman, Belletristik, Klassiker, Literatur",
    "Historisch": "Historischer Roman, Historischer Bericht",
    "Fantastik": "Fantasy, Fantasyliteratur, Phantastik, Phantastische Literatur",
    "Mythos & Epos": "Epos, Epische Sage, Sage, Legenden, Mythologie",
    "Kinder & Jugend": "Jugendliteratur, Kinderbuch, Bilderbuch, Tiergeschichte",
    "Kurzprosa": "Kurzgeschichte, Kurzgeschichten, Erzählung",
    "Sachtext": "Philosophie, Sachbuch, Memoiren, Autobiografie, Reisebericht, Reiseliteratur",
    "Lyrik": "Dichtung, Poesie",
    "Sonstiges": "Satire, Literarische Einleitung",
}
GENRE_WERTE = {w.strip().lower(): gr for gr, ws in GENRES.items() for w in ws.split(",")}
GESCHLECHT = ("weiblich", "maennlich", "unklar")


def genre_gruppe(genre):
    """-> (gruppe, bekannt). Exakter Listenwert, sonst laengster enthaltener Listenwert, sonst Sonstiges."""
    g = (genre or "").strip().lower()
    if g in GENRE_WERTE:
        return GENRE_WERTE[g], True
    treffer = [w for w in GENRE_WERTE if len(w) >= 4 and w in g]
    if treffer:
        return GENRE_WERTE[max(treffer, key=len)], True
    return "Sonstiges", False


# ============================================================
# EINGANG
# ============================================================

def quelltext(werk):
    p = os.path.join(config.book_dir(werk), "raw_modernized.txt")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8", errors="ignore") as f:
        return "\n".join(z for z in f.read().splitlines() if not z.startswith("###")).strip()


def werk330(werk):
    p = config.work_path(werk, "330_rueckuebersetzung")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def knoten(data, src):
    """[(id, {lg: text})] in Textreihenfolge."""
    out = []
    for tid, e in sorted(((data or {}).get("content") or {}).items()):
        if isinstance(e, dict) and str(e.get(src) or "").strip():
            out.append((tid, e))
    return out


def autor_laden(werk):
    try:
        slug = config.author_of(werk)
    except KeyError:
        return {}
    if not slug:
        return {}
    p = os.path.join(config.author_dir(slug), "author.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def autor_fakten(a):
    return {"name": a.get("name_display", ""), "verified": a.get("verified", False),
            "geburtsjahr": a.get("geburtsjahr"), "todesjahr": a.get("todesjahr"),
            "geburtsort": a.get("geburtsort", ""), "sterbeort": a.get("sterbeort", ""),
            "notable_works": a.get("notable_works", []), "epoche": a.get("epoche", ""),
            "stilrichtung": a.get("stilrichtung", []), "bedeutung_kurz": a.get("bedeutung_kurz", "")}


def _sample(body):
    head = body[:HEAD_CHARS]
    ms = max(0, len(body) // 2 - MID_CHARS // 2)
    return f"=== ANFANG ===\n{head}\n\n=== MITTE ===\n{body[ms:ms + MID_CHARS]}"


def epub_klappentext(roh, src):
    kt = roh.get("klappentext")
    if isinstance(kt, str):
        return kt.strip()
    if isinstance(kt, dict):
        return str(kt.get(src) or next((v for v in kt.values() if v), "") or "").strip()
    return ""


def _entsch_pfad(werk):
    return os.path.join(config.work_dir(werk), "600_entscheidungen.json")


def entscheidungen(werk):
    p = _entsch_pfad(werk)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"ersetzt": {}, "protokoll": []}


def entscheidung_setzen(werk, wer, **k):
    e = entscheidungen(werk)
    for key, v in k.items():
        if key == "ersetzt":
            for (blk, i, lg), t in v.items():
                e.setdefault("ersetzt", {}).setdefault(blk, {}).setdefault(str(i), {})[lg] = t
        elif v is None:
            e.pop(key, None)
        else:
            e[key] = v
    e.setdefault("protokoll", []).append({"wer": wer, "wann": manifest.jetzt(),
                                         "was": {kk: (str(vv)[:200]) for kk, vv in k.items()}})
    manifest.json_atomar(_entsch_pfad(werk), e, indent=1)
    return e


# ============================================================
# LLM
# ============================================================

def _llm(werk, system, prompt, schema, modell=None):
    usage_log.set_context(werk, STAGE)
    voll = (f"{system}\n\n{prompt}\n\nAntworte AUSSCHLIESSLICH mit einem JSON-Objekt nach diesem Schema "
            f"(keine Erklaerung, kein Markdown):\n{json.dumps(schema, ensure_ascii=False)}")
    alt = config.MODELS.get("profiler")
    if modell:
        config.MODELS["profiler"] = modell
    try:
        roh = api_layer.call_model("profiler", voll, temperature=0.3, max_tokens=16000)
    finally:
        config.MODELS["profiler"] = alt
    if not roh:
        raise RuntimeError("Stage 600: leere Modellantwort")
    return api_layer.parse_json(roh)


def meta_erzeugen(werk, body, modell=None):
    werte = "; ".join(f"{g}: {w}" for g, w in GENRES.items())
    sys_a = ("Du bist ein praeziser Literatur-Analyst. Leite ALLE Angaben AUSSCHLIESSLICH aus dem vorgelegten "
             "Ausschnitt ab, nie aus Vorwissen. Nicht Erkennbares -> 'unklar'. "
             f"genre = genau EIN Wert aus dieser Liste (Gruppe: Werte): {werte}. "
             "leseprobe_zitat = eine fesselnde Passage von 2-3 aufeinanderfolgenden Saetzen, ZEICHENGENAU aus dem "
             "Ausschnitt kopiert (keine Auslassung, kein Markup). "
             "hauptfigur_geschlecht = Geschlecht der zentralen Figur (Ich-Erzaehler zaehlt; Tiere nach erzaehltem "
             "Geschlecht); ohne klare Hauptfigur 'unklar'. sicherheit = 'pruefen' bei heiklen Inhalten.")
    schema = {"type": "object", "properties": {
        "genre": {"type": "string"}, "subgenres": {"type": "array", "items": {"type": "string"}},
        "ton": {"type": "string"}, "schauplatz": {"type": "string"}, "zeit": {"type": "string"},
        "hauptfiguren": {"type": "array", "items": {"type": "string"}},
        "hauptfigur_geschlecht": {"type": "string", "enum": list(GESCHLECHT)},
        "essenz": {"type": "string"}, "leseprobe_zitat": {"type": "string"},
        "inhaltshinweise": {"type": "array", "items": {"type": "string"}},
        "sicherheit": {"type": "string", "enum": ["unkritisch", "pruefen"]}},
        "required": ["genre", "ton", "essenz", "leseprobe_zitat", "sicherheit", "hauptfigur_geschlecht"]}
    return _llm(werk, sys_a, "Analysiere und fuelle das Schema:\n\n" + _sample(body), schema, modell)


def bloecke_erzeugen(werk, meta, fakten, langs, bloecke=("einordnung", "autor"), modell=None):
    satz = {"type": "object", "properties": {lg: {"type": "string"} for lg in langs}, "required": list(langs)}
    schema = {"type": "object", "properties": {b: {"type": "array", "items": satz} for b in bloecke},
              "required": list(bloecke)}
    sys_b = ("Du bist Klappentext-Autor fuer eine kultivierte Hoerbuch-Lern-App. Werbend, ehrlich, niveauvoll. "
             "Erfinde KEINE Handlungsdetails (nur die Metadaten nutzen). "
             "Block einordnung: 2-3 Saetze zu Werk, Genre und Stimmung. "
             "Block autor: 1-3 Saetze AUSSCHLIESSLICH aus 'autor_fakten'; keine Jahreszahlen, Orte oder Namen, "
             "die dort nicht stehen; bei verified=false oder leeren Feldern knapp und neutral, nichts aus Vorwissen. "
             f"Jeden Satz in ALLEN Sprachen ({', '.join(langs)}), inhaltsgleich, idiomatisch. "
             "Reiner Text: kein Markdown, keine Unterstriche/Sternchen, keine doppelten Bindestriche.")
    facts = {"sprachen": langs, "metadaten_aus_text": {k: meta.get(k) for k in
                                                        ("genre", "ton", "schauplatz", "zeit", "hauptfiguren",
                                                         "essenz")},
             "autor_fakten": fakten}
    out = _llm(werk, sys_b, f"Schreibe die Bloecke {', '.join(bloecke)}:\n\n"
               + json.dumps(facts, ensure_ascii=False, indent=2), schema, modell)
    return {b: [s for s in (out.get(b) or []) if isinstance(s, dict)] for b in bloecke}


def uebersetzen(werk, saetze, src, ziele, modell=None):
    """saetze [str] (Ausgangssprache) -> {lg: [str]} gleiche Reihenfolge."""
    if not saetze or not ziele:
        return {lg: [] for lg in ziele}
    schema = {"type": "object", "properties": {lg: {"type": "array", "items": {"type": "string"}} for lg in ziele},
              "required": list(ziele)}
    sys_t = (f"Du bist literarischer Uebersetzer aus der Sprache '{src}'. Uebersetze jeden Satz idiomatisch und "
             f"stilsicher in jede Zielsprache ({', '.join(ziele)}). Nichts weglassen, nichts hinzufuegen, Eigennamen "
             "bleiben. Gleiche Anzahl und Reihenfolge. Reiner Text ohne Markup.")
    out = _llm(werk, sys_t, "Saetze (JSON-Liste):\n" + json.dumps(saetze, ensure_ascii=False), schema, modell)
    return {lg: [str(t).strip() for t in (out.get(lg) or [])] for lg in ziele}


def _mock_roh(modus, body, langs, epub_kt):
    from tools import satzweise
    erste = " ".join(satzweise.teile_text(body[:2000], langs[0])[:2]) if body else ""
    roh = {"meta": {"genre": "Roman", "ton": "mock-tone", "essenz": "Mock-Essenz.", "leseprobe_zitat": erste,
                    "hauptfiguren": [], "hauptfigur_geschlecht": "unklar", "sicherheit": "unkritisch"},
           "bloecke": {}}
    if modus == "uebernehmen":
        roh["bloecke"]["einordnung"] = [{lg: (s if lg == langs[0] else f"[MOCK:600 {lg}] {s}") for lg in langs}
                                        for s in satzweise.teile_text(epub_kt, langs[0])]
    else:
        roh["bloecke"]["einordnung"] = [{lg: f"[MOCK:600 einordnung {lg}]" for lg in langs}]
        roh["bloecke"]["autor"] = [{lg: f"[MOCK:600 autor {lg}]" for lg in langs}]
    return roh


def erzeugen(werk, modus, body, langs, epub_kt, fakten, modell=None, bloecke_neu=None, alt_roh=None):
    """-> roh {meta, bloecke}. bloecke_neu: nur diese Bloecke neu (Rest aus alt_roh)."""
    src, ziele = langs[0], langs[1:]
    if mock.aktiv():
        return _mock_roh(modus, body, langs, epub_kt)
    if bloecke_neu and alt_roh:
        roh = json.loads(json.dumps(alt_roh))
        neu = [b for b in bloecke_neu if b in ("einordnung", "autor")]
        if neu and modus == "erzeugen":
            roh["bloecke"].update(bloecke_erzeugen(werk, roh["meta"], fakten, langs, tuple(neu), modell))
        if "koeder" in bloecke_neu:
            roh["meta"] = meta_erzeugen(werk, body, modell)
        return roh
    meta = meta_erzeugen(werk, body, modell)
    if modus == "uebernehmen":
        from tools import satzweise
        saetze = satzweise.teile_text(KP.markup_weg(epub_kt), src)
        tr = uebersetzen(werk, saetze, src, ziele, modell)
        einordnung = []
        for i, s in enumerate(saetze):
            e = {src: s}
            for lg in ziele:
                lst = tr.get(lg) or []
                e[lg] = lst[i] if i < len(lst) else ""
            einordnung.append(e)
        return {"meta": meta, "bloecke": {"einordnung": einordnung}}
    return {"meta": meta, "bloecke": bloecke_erzeugen(werk, meta, fakten, langs, modell=modell)}


# ============================================================
# ZUSAMMENSETZEN
# ============================================================

def koeder_aus_knoten(zitat, kn, src, langs):
    """Koeder = die Knoten (330), die die Passage abdecken -> ([{lg: text}], [ids]) oder (None, None)."""
    nz = KP.norm(zitat)
    if len(nz) < 20 or not kn:
        return None, None
    teile, pos = [], 0
    for tid, e in kn:
        n = KP.norm(e.get(src))
        teile.append((pos, pos + len(n), tid, e))
        pos += len(n)
    gesamt = "".join(KP.norm(e.get(src)) for _, e in kn)
    i = gesamt.find(nz)
    if i < 0:
        i = gesamt.find(nz[:60])
        if i < 0:
            return None, None
        ende = i + len(nz[:60])
    else:
        ende = i + len(nz)
    treffer = [(tid, e) for a, b, tid, e in teile if b > i and a < ende][:KOEDER_MAX_KNOTEN]
    if not treffer:
        return None, None
    return ([{lg: " ".join(str(e.get(lg) or "").split()) for lg in langs} for _, e in treffer],
            [tid for tid, _ in treffer])


def zusammensetzen(werk, roh, modus, langs, kn, body, b, ents, autor, vermerke_an=True):
    src = langs[0]
    meta = dict(roh.get("meta") or {})
    if ents.get("genre"):
        meta["genre"] = ents["genre"]
    if ents.get("hauptfigur_geschlecht"):
        meta["hauptfigur_geschlecht"] = ents["hauptfigur_geschlecht"]
    if ents.get("koeder"):
        meta["leseprobe_zitat"] = ents["koeder"]
    meta["genre_gruppe"], meta["genre_bekannt"] = genre_gruppe(meta.get("genre"))
    meta["herkunft"] = "epub" if modus == "uebernehmen" else "erzeugt"
    meta["autor"] = autor.get("name_display", "") or ""
    blurb = {"koeder": [], "einordnung": [], "autor": []}
    for blk, lst in (roh.get("bloecke") or {}).items():
        blurb[blk] = [{lg: KP.markup_weg(str((s or {}).get(lg) or "")) for lg in langs} for s in lst]
    meta["koeder_ids"] = []
    if modus == "erzeugen":
        z = meta.get("leseprobe_zitat") or ""
        k, ids = koeder_aus_knoten(z, kn, src, langs) if kn else (None, None)
        if k:
            blurb["koeder"], meta["koeder_ids"] = k, ids
        elif z:
            blurb["koeder"] = [{lg: (" ".join(z.split()) if lg == src else "") for lg in langs}]
    for blk, je in (ents.get("ersetzt") or {}).items():
        for i, t in je.items():
            i = int(i)
            if blk in blurb and 0 <= i < len(blurb[blk]):
                blurb[blk][i].update(t)
    vermerke = {}
    if vermerke_an and b.fassung == "modernisiert":
        vermerke["modernisiert"] = {lg: VERMERKE["modernisiert"].get(lg, VERMERKE["modernisiert"]["en"])
                                    for lg in langs}
    teil, ges = b.roh.get("teil"), b.roh.get("teile_gesamt")
    if vermerke_an and teil and ges:
        vermerke["teil"] = {lg: VERMERKE["teil"].get(lg, VERMERKE["teil"]["en"]).format(x=teil, y=ges)
                            for lg in langs}
    return meta, blurb, vermerke


# ============================================================
# PRUEFUNG
# ============================================================

def befunde(meta, blurb, vermerke, modus, langs, body, kn, b, autor, autor_pflicht, vermerke_an):
    """-> dict je Art: Liste (block, i, lg, text) bzw. Werte. Reine Regelpruefung."""
    src = langs[0]
    f = {"leer": [], "sprache": [], "kopie": [], "lizenz": [], "markup": [], "koeder": [], "vermerk": [],
         "laenge": {}, "autor_jahre": [], "autor_namen": [], "edition": []}
    pflicht = ("koeder", "einordnung") + (("autor",) if autor_pflicht else ()) if modus == "erzeugen" \
        else ("einordnung",)
    for blk in pflicht:
        if not blurb.get(blk):
            f["leer"].append((blk, None, "*", f"Block {blk} leer"))
    for blk, lst in blurb.items():
        for i, s in enumerate(lst):
            for lg in langs:
                t = s.get(lg) or ""
                if not t.strip():
                    if blk in pflicht or (lst and lg != src):
                        f["leer"].append((blk, i, lg, f"{blk}[{i}].{lg} leer"))
                    continue
                if mock.ist_text(t):
                    continue
                w = KP.boiler(t)
                if w:
                    f["lizenz"].append((blk, i, lg, f"{blk}[{i}].{lg}: Lizenztext '{w}'"))
                m = KP.markup(t)
                if m:
                    f["markup"].append((blk, i, lg, f"{blk}[{i}].{lg}: Markup {m[:2]}"))
                if blk == "koeder":
                    continue
                erk = KP.sprache_falsch(t, lg)
                if erk:
                    f["sprache"].append((blk, i, lg, f"{blk}[{i}].{lg}: Sprache {erk}"))
                elif lg != src and KP.kopie(s.get(src), t, src):
                    f["kopie"].append((blk, i, lg, f"{blk}[{i}].{lg}: Kopie der Ausgangssprache"))
    for fld in ("leseprobe_zitat", "essenz"):
        w = KP.boiler(str(meta.get(fld) or ""))
        if w:
            f["lizenz"].append(("meta", None, src, f"meta.{fld}: Lizenztext '{w}'"))
    # Koeder woertlich: Ausgangssprache im Werktext 190, Zielsprachen im Werktext 330
    if modus == "erzeugen" and blurb.get("koeder"):
        texte = {src: body or ""}
        for lg in langs[1:]:
            texte[lg] = " ".join(str(e.get(lg) or "") for _, e in (kn or []))
        for lg in langs:
            k = " ".join(str(s.get(lg) or "") for s in blurb["koeder"])
            if k.strip() and not mock.ist_text(k) and not KP.enthalten(k, texte.get(lg, "")):
                f["koeder"].append(("koeder", None, lg, f"Koeder {lg} nicht woertlich im Werktext"
                                                        f" ({'190' if lg == src else '330'})"))
    if vermerke_an:
        soll = (["modernisiert"] if b.fassung == "modernisiert" else []) + \
               (["teil"] if b.roh.get("teil") and b.roh.get("teile_gesamt") else [])
        for art in soll:
            for lg in langs:
                if not ((vermerke.get(art) or {}).get(lg) or "").strip():
                    f["vermerk"].append(("vermerk", None, lg, f"Vermerk {art} fehlt ({lg})"))
    for lg in langs:
        f["laenge"][lg] = sum(len(s.get(lg) or "") for lst in blurb.values() for s in lst) + \
            sum(len((v or {}).get(lg) or "") for v in vermerke.values())
    # Autor-Fakten: Jahreszahlen und Namen/Orte muessen in author.json stehen
    ab = [s for s in (blurb.get("autor") or []) if not mock.ist_obj(s)]
    if ab:
        deck = json.dumps(autor, ensure_ascii=False).lower() + " " + str(meta.get("autor") or "").lower() + " " + \
            " ".join(str(x) for x in (b.roh.get("titel_original"), json.dumps(b.roh.get("fassungen") or [],
                                                                                ensure_ascii=False))).lower()
        alle = " ".join(str(s.get(lg) or "") for s in ab for lg in langs)
        f["autor_jahre"] = [j for j in KP.jahre(alle) if j not in deck]
        je_lg = [" ".join(str(s.get(lg) or "") for s in ab) for lg in langs]
        f["autor_namen"] = [n for n in KP.namen(je_lg) if n.lower() not in deck]
    einl = " ".join(str(s.get(lg) or "") for s in blurb.get("einordnung") or [] for lg in langs) + " " + \
        str(meta.get("essenz") or "")
    tr = KP.einleitung(einl)
    if len(tr) >= 2:
        f["edition"] = tr
    return f


def _rep_stellen(f, arten):
    return [x for a in arten for x in f[a]]


def nachuebersetzen(werk, roh, stellen, langs, modell=None):
    """Saetze (block, i, lg) aus der Ausgangssprache neu in lg uebersetzen (nur Bloecke aus roh)."""
    src = langs[0]
    je_lg = {}
    for blk, i, lg, _t in stellen:
        if blk in (roh.get("bloecke") or {}) and i is not None and lg != src:
            je_lg.setdefault(lg, []).append((blk, i))
    for lg, st in je_lg.items():
        q = [roh["bloecke"][blk][i].get(src, "") for blk, i in st]
        tr = uebersetzen(werk, q, src, [lg], modell).get(lg) or []
        for (blk, i), t in zip(st, tr):
            if t.strip():
                roh["bloecke"][blk][i][lg] = t.strip()
    return roh


# ============================================================
# RUN
# ============================================================

def run(werk, wer=None, modus=None, modell=None, neu=False, koeder=None, genre=None, geschlecht=None,
        ersetzen=None, block_neu=None, laenge_max=None, vermerke=None, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="600", wer=wer)
    b = bestellung.lesen(werk)
    roh_b = b.roh
    src = b.quellsprache or config.SOURCE_LANGUAGE
    langs = [src] + [z for z in b.zielsprachen if z != src]
    ziele = langs[1:]
    from pipeline import kette
    quelle = kette.eingangsart(roh_b)
    verlag = b.mandant_art == "verlag"
    epub_kt = epub_klappentext(roh_b, src)
    reg = roh_b.get("klappentext_regler") or {}
    laenge_max = int(laenge_max or reg.get("laenge_max") or LAENGE_MAX)
    modell = modell or reg.get("modell")

    # Manuelle Regler (persistent)
    if not trocken:
        k = {}
        if koeder is not None:
            k["koeder"] = koeder or None
        if genre is not None:
            k["genre"] = genre or None
        if geschlecht is not None:
            if geschlecht not in GESCHLECHT:
                raise ValueError(f"--geschlecht {geschlecht!r} ungueltig")
            k["hauptfigur_geschlecht"] = geschlecht
        if modus is not None:
            k["modus"] = modus
        if vermerke is not None:
            from pipeline import s080_mandant
            s080_mandant.darf(werk, "override", wer)
            k["vermerke"] = vermerke
        if ersetzen:
            k["ersetzt"] = ersetzen
        if k:
            entscheidung_setzen(werk, wer, **k)
    ents = entscheidungen(werk)
    vermerke_an = ents.get("vermerke", "an") != "aus"
    modus_auto = "uebernehmen" if (epub_kt or verlag) else "erzeugen"
    modus = ents.get("modus") or reg.get("modus") or modus_auto
    if verlag and modus != "uebernehmen":
        g.hinweis("modus_verlag", False, text="Mandant verlag: nur Modus Uebernehmen")
        modus = "uebernehmen"
    for k_, v in (("sprachen", langs), ("modus", modus), ("quelle", quelle), ("vermerke", vermerke_an)):
        g.metrik(k_, v)

    # Eingaenge / Vorgaenger
    if modus == "uebernehmen" and not g.pflicht(
            "klappentext_epub", bool(epub_kt), ruecksprung="150",
            text="Klappentext aus 150 vorhanden" + (" (beim Verlag anfordern)" if verlag else "")):
        g.entscheide(schreiben=not trocken)
        return g
    for v in ("190", "330"):
        z = status.zustand(werk, v)
        if trocken:
            g.hinweis(f"gate_{v}", z in status.FREI, text=f"Gate {v}: {z}")
        else:
            g.pflicht(f"gate_{v}", z in status.FREI, wert=z, ruecksprung=v, text=f"Gate {v} frei ({z})")
    body = quelltext(werk)
    g.pflicht("quelltext", bool(body), ruecksprung="190", text="raw_modernized.txt (190) vorhanden")
    data = werk330(werk) if ziele else None
    if ziele:
        g.pflicht("werk330", data is not None, ruecksprung="330", text="330_rueckuebersetzung.json vorhanden")
    if g.fehler():
        g.entscheide(schreiben=not trocken)
        return g
    kn = knoten(data, src) if data else []
    autor = autor_laden(werk)
    fakten = autor_fakten(autor)
    autor_pflicht = (b.rechte or {}).get("art") != "eigene"

    # Eingangs-Hash -> Wiederverwendung ohne LLM
    eingang = manifest.hash_obj({"v": PROMPT_V, "modus": modus, "langs": langs, "modell": modell or
                                 config.MODELS.get("profiler"), "probe": manifest.hash_text(_sample(body)),
                                 "epub": epub_kt, "autor": fakten if autor_pflicht else None,
                                 "lauf": mock.modus()})
    aus_pfad = config.work_path(werk, "600_klappentext")
    alt = None
    if os.path.exists(aus_pfad):
        with open(aus_pfad, encoding="utf-8") as fh:
            alt = json.load(fh)
    roh = (alt or {}).get("roh") if (alt and alt.get("eingang_hash") == eingang and not neu) else None
    if roh and not mock.aktiv() and mock.ist_obj(roh):
        roh = None
    if trocken and not roh:
        if not alt or not alt.get("roh"):
            g.pflicht("bestand", False, text="600_klappentext.json (neues Format) fehlt (Probe ohne LLM)")
            g.entscheide(schreiben=False)
            return g
        roh = alt["roh"]
        g.hinweis("eingang", False, text="Eingaenge geaendert – Probe mit Bestand")
    neu_erzeugt = 0
    if not roh:
        roh = erzeugen(werk, modus, body, langs, epub_kt, fakten, modell)
        neu_erzeugt = 1
    elif block_neu and not trocken:
        roh = erzeugen(werk, modus, body, langs, epub_kt, fakten, modell, bloecke_neu=block_neu, alt_roh=roh)
        neu_erzeugt = 1

    # Zusammensetzen + Pruefung, 1x automatische Reparatur
    reparatur = []
    for runde in (0, 1):
        meta, blurb, verm = zusammensetzen(werk, roh, modus, langs, kn, body, b, ents, autor, vermerke_an)
        f = befunde(meta, blurb, verm, modus, langs, body, kn, b, autor, autor_pflicht, vermerke_an)
        if runde == 1 or trocken or mock.aktiv():
            break
        neu_noetig = _rep_stellen(f, ("lizenz", "markup")) or [x for x in f["leer"] if x[2] in ("*", src)] or \
            (f["koeder"] and not ents.get("koeder") and any(x[2] == src for x in f["koeder"]))
        nach = _rep_stellen(f, ("sprache", "kopie")) + [x for x in f["leer"] if x[2] not in ("*", src)]
        if neu_noetig:
            reparatur.append("neu: " + "; ".join(x[3] for x in (neu_noetig if isinstance(neu_noetig, list)
                                                                 else f["koeder"])[:3]))
            roh = erzeugen(werk, modus, body, langs, epub_kt, fakten, modell)
            neu_erzeugt += 1
        elif nach:
            reparatur.append(f"nachuebersetzt: {len(nach)}")
            roh = nachuebersetzen(werk, roh, nach, langs, modell)
        else:
            break

    # Gate
    for lg in langs:
        def je(art, lg=lg):
            return [x for x in f[art] if x[2] in (lg, "*")]
        g.pflicht(f"bloecke_{lg}", not je("leer"), wert=len(je("leer")), bei_fehler="mensch",
                  text=f"{lg}: Bloecke vollstaendig" + (f" – {[x[3] for x in je('leer')][:3]}" if je("leer") else ""))
        g.pflicht(f"sprache_{lg}", not je("sprache") and not je("kopie"),
                  wert=len(je("sprache")) + len(je("kopie")), bei_fehler="mensch",
                  text=f"{lg}: Sprache je Satz, keine Kopie" +
                       (f" – {[x[3] for x in je('sprache') + je('kopie')][:3]}" if je("sprache") or je("kopie") else ""))
        g.pflicht(f"lizenz_{lg}", not je("lizenz"), wert=len(je("lizenz")), bei_fehler="mensch",
                  text=f"{lg}: Lizenz-/Gutenbergtext = 0" + (f" – {je('lizenz')[0][3]}" if je("lizenz") else ""))
        g.pflicht(f"markup_{lg}", not je("markup"), wert=len(je("markup")), bei_fehler="mensch",
                  text=f"{lg}: Markup-Reste = 0" + (f" – {je('markup')[0][3]}" if je("markup") else ""))
        if modus == "erzeugen":
            g.pflicht(f"koeder_{lg}", not je("koeder"), bei_fehler="mensch", ruecksprung="600" if lg == src else "310",
                      text=f"{lg}: Koeder woertlich im Werktext ({'190' if lg == src else '330'})")
        g.pflicht(f"vermerke_{lg}", not je("vermerk"), bei_fehler="mensch",
                  text=f"{lg}: Pflichtvermerke" + (f" – {[x[3] for x in je('vermerk')]}" if je("vermerk") else ""))
        g.hinweis(f"laenge_{lg}", f["laenge"][lg] <= laenge_max, wert=f["laenge"][lg],
                  text=f"{lg}: Laenge {f['laenge'][lg]} Zeichen (Soll <= {laenge_max})")
    if not vermerke_an:
        g.hinweis("vermerke_aus", False, text="Vermerke abgeschaltet (Admin)")
    g.pruefe("autor_fakten", not f["autor_jahre"] and not f["autor_namen"],
             wert=len(f["autor_jahre"]) + len(f["autor_namen"]), bei_fehler="mensch", ruecksprung="110",
             text="Autor-Block: Jahreszahlen/Namen in author.json gedeckt" +
                  (f" – ungedeckt {(f['autor_jahre'] + f['autor_namen'])[:6]}"
                   if f["autor_jahre"] or f["autor_namen"] else ""))
    if blurb.get("autor") and len(langs) < 2:
        g.hinweis("autor_orte", False, text="Autor-Block: Namen/Orte bei nur einer Sprache nicht pruefbar")
    if not autor_pflicht:
        g.hinweis("autor_block", True, text="Autor-Block entfaellt (rechte eigene)")
    elif not autor:
        g.hinweis("author_json", False, text="author.json fehlt – Autor-Block neutral (110/150)")
    elif not autor.get("verified"):
        g.hinweis("autor_verifiziert", False, text="Autor nicht verifiziert (110)")
    g.pruefe("sicherheit", meta.get("sicherheit") != "pruefen", wert=meta.get("sicherheit"), bei_fehler="mensch",
             text=f"Sicherheit {meta.get('sicherheit')}")
    g.pruefe("edition", not f["edition"], bei_fehler="mensch",
             text="Werk statt Edition beschrieben" + (f" – Verdacht {f['edition'][:4]}" if f["edition"] else ""))
    g.hinweis("genre", meta.get("genre_bekannt"), wert=meta.get("genre"),
              text=f"Genre {meta.get('genre')!r} -> Gruppe {meta.get('genre_gruppe')}"
                   + ("" if meta.get("genre_bekannt") else " (nicht in Liste)"))
    g.hinweis("hauptfigur_geschlecht", meta.get("hauptfigur_geschlecht") in ("weiblich", "maennlich"),
              wert=meta.get("hauptfigur_geschlecht"), text=f"hauptfigur_geschlecht {meta.get('hauptfigur_geschlecht')}")
    if reparatur:
        g.hinweis("reparatur", False, text="automatisch repariert: " + " | ".join(reparatur))
    n_mock = 0 if mock.aktiv() else int(mock.ist_obj({"m": meta, "b": blurb}))
    g.mock(n_mock, ruecksprung="600")
    g.metrik("llm_erzeugt", neu_erzeugt)
    g.metrik("genre_gruppe", meta.get("genre_gruppe"))

    aus = {"schema": 2, "stage": STAGE, "modus": modus, "herkunft": meta["herkunft"], "quellsprache": src,
           "sprachen": langs, "autor": meta["autor"], "wirkungssprache": autor.get("wirkungssprache", "") or "",
           "meta": meta, "blurb": blurb, "vermerke": verm, "eingang_hash": eingang, "roh": roh,
           "modell": modell or config.MODELS.get("profiler"), "prompt_v": PROMPT_V, "erzeugt": manifest.jetzt()}
    aus_hash = manifest.hash_obj({"b": blurb, "v": verm, "m": {k_: meta.get(k_) for k_ in
                                                               ("genre", "hauptfigur_geschlecht", "ton")}})
    g.metrik("ausgabe_hash", aus_hash)
    st = status.laden(werk)["stages"].get(STAGE) or {}
    mensch_gilt = st.get("zustand") == "frei" and (st.get("gate") or {}).get("ergebnis") == "mensch" \
        and (st.get("metriken") or {}).get("ausgabe_hash") == aus_hash
    if mensch_gilt:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Ausgabe unveraendert]"
        immer, grund = False, None
    elif verlag:
        immer, grund = True, "Mandant verlag: Klappentext freigeben"
    elif modus == "erzeugen" and quelle in ("user_epub", "verlag_epub"):
        immer, grund = True, "Erzeugter Klappentext fuer User-ePub: Freigabe durch Mensch"
    else:
        immer, grund = False, None
    e = g.entscheide(mensch_immer=immer, mensch_grund=grund, schreiben=not trocken)
    aus["pruefung"] = {"ergebnis": e, "fehler": g.ergebnis["gruende"], "hinweise": g.ergebnis["hinweise"],
                       "zeit": manifest.jetzt()}
    if not trocken:
        manifest.json_atomar(aus_pfad, aus, indent=2)
    g.aus = aus
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 600 Klappentext")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--modus", choices=["uebernehmen", "erzeugen"])
    ap.add_argument("--modell")
    ap.add_argument("--neu", action="store_true", help="Metadaten und Klappentext neu erzeugen")
    ap.add_argument("--koeder", metavar="TEXT", help="Koeder-Passage im Werktext waehlen ('' = zuruecksetzen)")
    ap.add_argument("--genre", help="Genre manuell ('' = zuruecksetzen)")
    ap.add_argument("--geschlecht", choices=list(GESCHLECHT))
    ap.add_argument("--ersetzen", action="append", metavar="BLOCK:I:LG=TEXT", help="Satz manuell ersetzen")
    ap.add_argument("--block-neu", action="append", choices=["koeder", "einordnung", "autor"])
    ap.add_argument("--laenge-max", type=int)
    ap.add_argument("--vermerke", choices=["an", "aus"], help="nur Admin")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    ers = {}
    for s in a.ersetzen or []:
        try:
            ziel, text = s.split("=", 1)
            blk, i, lg = ziel.split(":")
            ers[(blk, int(i), lg)] = text.strip()
        except ValueError:
            print(f"[600] --ersetzen {s!r}: Format BLOCK:I:LG=TEXT")
            return 1
    try:
        if (ers or a.genre is not None or a.geschlecht or a.koeder is not None or a.modus) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", a.wer or "pipeline")
        g = run(a.werk, a.wer, a.modus, a.modell, a.neu, a.koeder, a.genre, a.geschlecht, ers or None,
                a.block_neu, a.laenge_max, a.vermerke, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[600] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
