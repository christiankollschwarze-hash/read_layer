"""STAGE 600 — Klappentext
Funktion:     Metadaten und dreiteiliger Klappentext in allen Sprachen.
Wirkungsweise: Textproben (Anfang, Mitte) -> Metadaten; dann Klappentext aus Metadaten und verifizierten Autor-Fakten (DeepSeek Pro).
              Danach Pruefung (klappentext_pruefung): DE-Saetze nachuebersetzen, bei Gutenberg-Text neu erzeugen.
              --pruefen: bestehenden Klappentext nur pruefen/reparieren (Cockpit).
Komponenten:  pipeline/s600_klappentext.py, api_layer
Zulieferer:   s120 Modernisierung (raw_modernized.txt), s110 Wikidata (author.json)
Abnehmer:     s610 Cover, s620/s630 ePub, s640 Teaser (work/600_klappentext.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 09: Klappentext (Schaufenster-Text)
======================================================
Zweistufig in einem Schritt:
  A) Metadaten-Extraktion aus dem Buchtext (weiche Metadaten, ehrlich aus dem Text)
  B) Komposition des dreiteiligen Klappentexts (Koeder / Einordnung / Autor),
     satzparallel ueber ALLE Zielsprachen fuer die "Ups"-Demo.

Fuegt sich in das Pipeline-Muster ein: run(book_id), Pfade ueber config,
Checkpoint = work_path(book_id, "600_klappentext").

Quelle fuer den Text: raw_modernized.txt (Text des EPUBs), sonst raw.txt.
Modelle/Keys aus config (MODELS["profiler"] via api_layer, RUN_MODE). QF-1 18.10.2026: kein Gemini mehr.
"""

import os, json, re, time
from config import config

STAGE = "600_klappentext"

HEAD_CHARS = 12000
MID_CHARS  = 6000

METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "genre":        {"type": "string"},
        "subgenres":    {"type": "array", "items": {"type": "string"}},
        "ton":          {"type": "string"},
        "schauplatz":   {"type": "string"},
        "zeit":         {"type": "string"},
        "hauptfiguren": {"type": "array", "items": {"type": "string"}},
        # 19.10.2026: Klappentext-Erzaehlerstimme (claude/PROZESS_klappentext_erzaehler.md)
        "hauptfigur_geschlecht": {"type": "string", "enum": ["weiblich", "maennlich", "unklar"]},
        "essenz":       {"type": "string"},
        "leseprobe_zitat": {"type": "string"},
        "inhaltshinweise": {"type": "array", "items": {"type": "string"}},
        "sicherheit":   {"type": "string", "enum": ["unkritisch", "pruefen"]},
    },
    "required": ["genre", "ton", "essenz", "leseprobe_zitat", "sicherheit", "hauptfigur_geschlecht"],
}


def _blurb_schema(langs):
    """Dreiteiliger Klappentext, jeder Block Liste von Satz-Objekten mit allen Sprachen."""
    sentence_props = {lang: {"type": "string"} for lang in langs}
    block = {
        "type": "array",
        "items": {"type": "object", "properties": sentence_props, "required": langs},
    }
    return {
        "type": "object",
        "properties": {"koeder": block, "einordnung": block, "autor": block},
        "required": ["koeder", "einordnung", "autor"],
    }


def _llm_json(task, system, prompt, schema):
    """QF-1 (18.10.2026): Vorher direkter Gemini-Aufruf mit MODELS["profiler"/"validator"] --
    seit der DeepSeek-Umstellung (12.10.) passten Endpunkt und Modellname nicht mehr.
    Jetzt ueber api_layer (Retries via _post_robust, Kosten-Log), Schema im Prompt."""
    from pipeline import api_layer
    voll = (f"{system}\n\n{prompt}\n\n"
            f"Antworte AUSSCHLIESSLICH mit einem JSON-Objekt nach diesem Schema "
            f"(keine Erklaerung, kein Markdown):\n{json.dumps(schema, ensure_ascii=False)}")
    roh = api_layer.call_model(task, voll, temperature=0.3, max_tokens=16000)
    if not roh:
        raise RuntimeError(f"Stage 20: leere Antwort von {config.MODELS.get(task)}")
    return api_layer.parse_json(roh)


def _load_source_text(book_id):
    """QF-1 (18.10.2026): bevorzugt raw_modernized.txt -- das Koeder-Zitat muss woertlich
    im ausgelieferten (modernisierten) EPUB-Text stehen. Fallback: raw.txt."""
    mp = os.path.join(config.book_dir(book_id), "raw_modernized.txt")
    if os.path.exists(mp):
        t = open(mp, encoding="utf-8", errors="ignore").read()
        return "\n".join(z for z in t.splitlines() if not z.startswith("###"))
    rp = config.raw_path(book_id)
    if os.path.exists(rp):
        return open(rp, encoding="utf-8", errors="ignore").read()
    raise FileNotFoundError(f"Kein Rohtext: {mp} / {rp}")


def _load_author(book_id):
    """Autor zum Buch ueber den Index aufloesen -> author.json (oder {} wenn nicht da).
    Liefert die VERIFIZIERTEN Fakten fuer den Autor-Block (statt Modell-Vorwissen)."""
    try:
        slug = config.author_of(book_id)
    except KeyError:
        return {}
    ap = os.path.join(config.author_dir(slug), "author.json")
    if os.path.exists(ap):
        try:
            return json.load(open(ap, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _autor_fakten(author):
    """Nur die Felder, die der Autor-Block braucht -- als kompakter Faktenblock."""
    return {
        "name":           author.get("name_display", ""),
        "verified":       author.get("verified", False),
        "geburtsjahr":    author.get("geburtsjahr"),
        "todesjahr":      author.get("todesjahr"),
        "geburtsort":     author.get("geburtsort", ""),
        "notable_works":  author.get("notable_works", []),
        "epoche":         author.get("epoche", ""),
        "stilrichtung":   author.get("stilrichtung", []),
        "bedeutung_kurz": author.get("bedeutung_kurz", ""),
    }


def _strip_boilerplate(t):
    for mk in ("*** START OF THE PROJECT GUTENBERG", "*** START OF THIS PROJECT GUTENBERG"):
        i = t.find(mk)
        if i != -1:
            nl = t.find("\n", i); t = t[nl+1:] if nl != -1 else t; break
    for mk in ("*** END OF THE PROJECT GUTENBERG", "*** END OF THIS PROJECT GUTENBERG"):
        i = t.find(mk)
        if i != -1: t = t[:i]; break
    return t.strip()


def _sample(body):
    head = body[:HEAD_CHARS]
    ms = max(0, len(body)//2 - MID_CHARS//2)
    return f"=== ANFANG ===\n{head}\n\n=== MITTE ===\n{body[ms:ms+MID_CHARS]}"


def _mock(langs):
    s = lambda d: {lang: d for lang in langs}
    return {"meta": {"genre": "Mock", "ton": "neutral", "essenz": "Mock-Essenz.",
            "leseprobe_zitat": "Mock-Zitat.", "sicherheit": "unkritisch"},
            "blurb": {"koeder": [s("Mock Koeder.")],
                      "einordnung": [s("Mock Einordnung.")],
                      "autor": [s("Mock Autor.")]}}


def _erzeuge(book_id):
    """Erzeugt Metadaten + Klappentext neu (ohne Pruefung, ohne Schreiben)."""
    return run(book_id, _nur_erzeugen=True)


def run(book_id, _nur_erzeugen=False):
    langs = config.ALL_LANGUAGES
    out_path = config.work_path(book_id, STAGE)

    # Autor ueber den Index aufloesen (verifizierte Fakten fuer den Autor-Block + Aussprache).
    author = _load_author(book_id)
    autor_name      = author.get("name_display", "") or ""
    wirkungssprache = author.get("wirkungssprache", "") or ""

    if config.RUN_MODE == "mock":
        result = _mock(langs)
        result["meta"]["autor"] = autor_name          # Stage 10 liest meta.autor (Rueckwaerts-Kompat.)
        result["autor"] = autor_name                  # bevorzugte Quelle fuer Stage 10
        result["wirkungssprache"] = wirkungssprache
        json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[600_klappentext] (mock) Klappentext -> {out_path}")
        return result

    # --- A) Metadaten ---
    body = _strip_boilerplate(_load_source_text(book_id))
    sys_a = ("Du bist ein praeziser Literatur-Analyst. Leite ALLE Angaben AUSSCHLIESSLICH "
             "aus dem vorgelegten Ausschnitt ab, nie aus Vorwissen. Nicht Erkennbares -> 'unklar'. "
             "Das Zitat in leseprobe_zitat muss WOERTLICH (2-3 Saetze) im Ausschnitt vorkommen. "
             "hauptfigur_geschlecht = Geschlecht der zentralen Figur, um die die Handlung kreist "
             "(Ich-Erzaehler zaehlt; Tiere nach erzaehltem Geschlecht); ohne klare Hauptfigur 'unklar'.")
    meta = _llm_json("profiler", sys_a, "Analysiere und fuelle das Schema:\n\n" + _sample(body),
                     METADATA_SCHEMA)

    # --- B) Klappentext ---
    lang_list = ", ".join(langs)
    sys_b = (f"Du bist ein Klappentext-Autor fuer eine kultivierte Hoerbuch-Lern-App. "
             f"Werbend, ehrlich, niveauvoll. Erfinde KEINE Handlungsdetails (nur Metadaten nutzen). "
             f"Koeder = die woertliche Leseprobe-Passage, exakt wiedergeben. "
             f"Autor-Block AUSSCHLIESSLICH aus 'autor_fakten' bilden (verifizierte Daten). "
             f"Wenn autor_fakten.verified=false oder Felder leer sind: knapp und neutral bleiben, "
             f"NICHTS erfinden, keine Wertungen aus Vorwissen. "
             f"Liefere jeden Satz in ALLEN Sprachen ({lang_list}), inhaltsgleich, idiomatisch.")
    facts = {"book_id": book_id, "sprachen": langs,
             "metadaten_aus_text": meta,
             "autor_fakten": _autor_fakten(author)}
    blurb = _llm_json("profiler", sys_b, "Komponiere den dreiteiligen Klappentext:\n\n"
                      + json.dumps(facts, ensure_ascii=False, indent=2),
                      _blurb_schema(langs))

    meta["autor"] = autor_name                        # Stage 10 (Rueckwaerts-Kompat.)
    if config.eigene_rechte(book_id):
        blurb = eigenwerk_anpassen(book_id, blurb)
    result = {"autor": autor_name, "wirkungssprache": wirkungssprache,
              "meta": meta, "blurb": blurb}
    if _nur_erzeugen:
        return result
    result = _absichern(book_id, result, body)
    json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[600_klappentext] Klappentext (Meta+Blurb, {len(langs)} Sprachen) -> {out_path}")
    if not author:
        print("[600_klappentext] HINWEIS: kein author.json gefunden -> Autor-Block bleibt neutral.")
    elif not author.get("verified"):
        print("[600_klappentext] HINWEIS: Autor nicht verifiziert (Stage 08b) -> Autor-Block bleibt knapp.")
    if meta.get("sicherheit") == "pruefen":
        print("[600_klappentext] HINWEIS: sicherheit='pruefen' -> heikler Titel, manuell pruefen.")
    return result


def eigenwerk_anpassen(book_id, blurb):
    """22.10.2026: eigenes Werk (rechte=eigene) -> kein Autor-Block (keine Biografie zu "Unbekannt");
    Koeder in den Zielsprachen aus der Werk-Uebersetzung (400_regie) statt freier Neuuebersetzung."""
    blurb["autor"] = []
    src = config.SOURCE_LANGUAGE
    try:
        content = json.load(open(config.work_path(book_id, "400_regie"), encoding="utf-8"))["content"]
    except (OSError, ValueError, KeyError):
        return blurb
    norm = lambda t: " ".join(str(t).split()).strip("\u201e\u201c\"'_ ")
    reihe = [(norm(e.get(src, "")), e) for _, e in sorted(content.items())]
    for k in blurb.get("koeder", []):
        q = norm(k.get(src, ""))
        for i, (t, _) in enumerate(reihe):
            if t and q.startswith(t):
                teile, rest, j = [], q, i
                while rest and j < len(reihe) and rest.startswith(reihe[j][0]):
                    teile.append(reihe[j][1]); rest = rest[len(reihe[j][0]):].strip(); j += 1
                if not rest:
                    for lg in config.TARGET_LANGUAGES:
                        k[lg] = " ".join(norm(e.get(lg, "")) for e in teile)
                break
    return blurb


# ------------------------------------------------------------------ Pruefung + Reparatur (18.10.2026)
def _nachuebersetzen(result, stellen):
    """Uebersetzt nur die beanstandeten Saetze (DE = EN / nicht deutsch) neu ins Deutsche."""
    bl = result["blurb"]
    quellen = [bl[b][i].get("en", "") for b, i in stellen]
    sys_t = ("Du bist literarischer Uebersetzer EN->DE. Uebersetze jeden Satz idiomatisch und "
             "stilsicher ins Deutsche. Zitate sinngetreu und literarisch, nichts weglassen, "
             "nichts hinzufuegen. Eigennamen bleiben.")
    schema = {"type": "object", "properties": {"de": {"type": "array", "items": {"type": "string"}}},
              "required": ["de"]}
    out = _llm_json("profiler", sys_t, "Saetze (JSON-Liste, gleiche Reihenfolge zurueck):\n"
                    + json.dumps(quellen, ensure_ascii=False), schema)
    de = out.get("de") or []
    for (b, i), t in zip(stellen, de):
        if str(t).strip():
            bl[b][i]["de"] = str(t).strip()
    return result


def _absichern(book_id, result, quelltext=None, neu_erlaubt=True):
    """Prueft den Klappentext; repariert DE-Saetze gezielt; erzeugt bei Gutenberg/Lizenz-Text
    oder leeren Bloecken einmal komplett neu. Ergebnis der Pruefung steht in result["pruefung"]."""
    from pipeline.klappentext_pruefung import pruefe
    if quelltext is None:
        try:
            quelltext = _strip_boilerplate(_load_source_text(book_id))
        except Exception:
            quelltext = None
    p = pruefe(result, quelltext)
    if p["neu"] and neu_erlaubt and config.RUN_MODE != "mock":
        print("[600_klappentext] Pruefung: " + "; ".join(p["fehler"][:3]) + " -> Neuerzeugung")
        result = _erzeuge(book_id)
        p = pruefe(result, quelltext)
    if p["nachuebersetzen"] and not p["neu"] and config.RUN_MODE != "mock":
        print(f"[600_klappentext] Pruefung: {len(p['nachuebersetzen'])} DE-Satz/Saetze unuebersetzt -> Nachuebersetzung")
        result = _nachuebersetzen(result, p["nachuebersetzen"])
        p = pruefe(result, quelltext)
    result["pruefung"] = {"ok": p["ok"], "fehler": p["fehler"], "hinweise": p["hinweise"],
                          "zeit": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if p["ok"]:
        print("[600_klappentext] Pruefung bestanden" + (f" (Hinweise: {'; '.join(p['hinweise'])})" if p["hinweise"] else ""))
    else:
        print("[600_klappentext] [FEHLER] Pruefung nicht bestanden: " + "; ".join(p["fehler"]))
    return result


def pruefen(book_id):
    """Nur pruefen/reparieren, ohne Neuerzeugung, wenn der Klappentext reparierbar ist (Cockpit)."""
    out_path = config.work_path(book_id, STAGE)
    result = json.load(open(out_path, encoding="utf-8"))
    result = _absichern(book_id, result)
    json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    bid = args[0] if args else "time_machine"
    if "--pruefen" in sys.argv:
        pruefen(bid)
    else:
        run(bid)
