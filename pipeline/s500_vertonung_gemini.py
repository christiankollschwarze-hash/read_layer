"""STAGE 500 — Vertonung (Gemini-Gleis)
Funktion:     Satz-WAVs per Gemini-TTS.
Wirkungsweise: Bloecke aus 15-25 Saetzen je Aufruf, MMS_FA-Schnitt am Energietal, Solo-Fallback; Manifest work/500_vertonung.json.
Komponenten:  pipeline/s500_vertonung_gemini.py, block_planner, audio_fa, tts_client. Standard-Gleis Chatterbox: gpu_tts/tts_modal_opt.py
Zulieferer:   s400 Regie (work/400_regie.json), s410 Casting (book.json)
Abnehmer:     s520 Wortzeiten, s530 Pruefungen, s710 Cloud-Export (fassungen/<lang>/audio/<tag>.wav)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 58 (Cloud-TTS, BLOCK-Vertonung mit FA-Schnitt)
=================================================================
Input:  authors/<a>/books/<b>/work/400_regie.json   (Tags, Text je Sprache, production.direction)
        authors/<a>/books/<b>/book.json            (audio_voice, audio_regler -- optional)
Output: authors/<a>/books/<b>/fassungen/<lang>/audio/<tag_id>.wav   (UNVERAENDERTER Vertrag)
        + work/500_vertonung.json (Manifest: welche Schnipsel je Sprache + QA-Flags)

NEU (Block-Architektur, ersetzt 1-Satz-pro-Call):
  Erst Vortrag, dann Satzgrenze. Aufeinanderfolgende s/dl-Saetze werden je
  Kapitel zu BLOECKEN (6-10, absatzrespektierend, nie >10) gruppiert
  (block_planner) und in EINEM TTS-Call als durchgehender Absatz vertont
  -> Kontext + Prosodie bleiben erhalten, Kurzsatz-Dopplung verschwindet.
  Danach wird der Block per Forced Alignment (audio_fa.fa_cut) an den
  Satzgrenzen geschnitten und positionell den tag_ids zugeordnet
  -> exakt dieselben Pro-Tag-WAVs wie bisher.

BULLET-PROOF-LEITER (Resilienz):
  1) Block-TTS mit Retry. Scheitert er endgueltig -> Solo-Fallback.
  2) FA-Netz pro Block: Mengenpruefung + jede Grenze OK/FLAG. Stimmt die
     Schnittzahl NICHT exakt (N-1 saubere Schnitte) ODER flaggt eine Grenze
     -> der GANZE Block faellt in den Solo-Fallback (alter 1-Satz-Pfad,
     _build_prompt + _synthesize). Garantiert N WAVs, Tag-Zuordnung heil.
  3) Resume zaehlt echte Pro-Tag-WAVs. Solo-Tags (h/Titelei/Kurzzeilen)
     laufen ohnehin einzeln + schlicht wie bisher.

Interpunktion (AUDIO-ONLY): fehlt einem Satz das Satzende, wird fuer die
Vertonung ein Punkt ergaenzt (klares Pausen-/FA-Signal). 400_regie/EPUB bleiben
unangetastet -- der Punkt existiert nur im vertonten Text.

WAV/LINEAR16 (24 kHz). Retry gegen "nur Text statt Audio".

UMBAU 08.10.2026 -- Gemini 3.8 TTS (config.TTS_BACKEND = "gemini_api"):
  Synthese laeuft ueber pipeline/tts_client.py (Gemini-API, Interactions).
  Steuerung wie von Google fuer 3.8 vorgegeben: Text = wortgetreues Transkript,
  Regie = KURZER style aus Stage 56. Die frueheren Meta-Anweisungen
  (BLOCK_INSTRUCTION, "Read ONLY...", OPENING/CLOSING-Kontext) entfallen bei 3.8,
  weil sie laut Doku das Abdriften der Stimme verstaerken. Der Sentinel-Satz bleibt
  (deterministischer Schutz des Blockendes, unabhaengig vom Modell).
  Bei TTS_BACKEND = "cloud_tts" laeuft alles exakt wie vorher.

CLI:
  python -m pipeline.s500_vertonung_gemini <book> [--chapter c001] [--lang de]
       [--force] [--limit N] [--voice Orus] [--valley-ratio 0.45] [--fa-pre 0.02]
       [--cut-guard 0.10]    # Schnitt knapp vor dem Folgewort (s) -> Auslaut bleibt ganz
       [--reuse-blocks]   # vorhandene Block-WAVs wiederverwenden (KEIN TTS) -> Schnitt-Tuning gratis
       [--keep-blocks]    # Block-WAVs nach dem Schnitt behalten (zum spaeteren Wiederverwenden)
"""

import sys, os, json, time, wave, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import block_planner       # Pipeline-Bibliothek (eine Quelle der Block-Logik)
from pipeline import audio_fa             # FA-Schnitt (eine Quelle der Schnitt-Logik)
from pipeline import tts_client           # TTS-Calls (eine Quelle, Backend aus config)

LANG_CODE = {"en": "en-US", "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "it": "it-IT"}
RETRIES = 4
PAUSE_SECONDS = getattr(config, "TTS_DELAY_SECONDS", 4)

BLOCK_INSTRUCTION = ("Read the following passage aloud once, as a calm, natural "
                     "audiobook narrator, in a single continuous flow. Speak only "
                     "this passage, and do not repeat any part of it. "
                     "Finish the final sentence completely, pronouncing its last "
                     "word in full, then add a brief natural pause.")

_TERMINAL = ".?!…:;"          # Satzende-Zeichen (vor evtl. schliessendem Quote)

# Sentinel: kurzer Wegwerf-Satz ANS BLOCKENDE. Gibt dem echten Schlusswort ein
# Folgewort -> es wird zum inneren Satz und faellt unter die saubere Schnittregel.
# Nach dem Schnitt wird das Sentinel-Segment verworfen. Deterministischer Schutz
# des Blockendes (statt nur per Koeder-Prompt zu hoffen). Sprachabhaengig, damit
# das Modell nicht mitten im Block die Sprache wechselt; Fallback Englisch.
SENTINEL = {"de": "So weit, so gut.",
            "en": "So far, so good.",
            "fr": "Jusqu'ici, tout va bien.",
            "es": "Hasta aquí, todo bien.",
            "it": "Fin qui, tutto bene."}
SENTINEL_ID = "__sentinel__"

# Dauer-Plausibilitaet (Netz gegen TTS-Totalausfall): Ein Block hat eine erwartbare
# Audiolaenge aus Wortzahl / Sprechrate. Kollabiert ein Pro-TTS-Call mitten im Block
# (minutenlanges Rauschen/Halluzination), wird das Block-WAV VIEL laenger als erwartet.
# Das Mengen-Netz sieht das NICHT (Rauschen = keine zaehlbaren Woerter), die Dauer schon.
# Kalibriert an echtem Fall: kaputt 194 s vs. gesund 54 s (8 Saetze) -> Faktor ~3,6.
# Schwelle 2.5x faengt den Ausfall sicher und laesst gesunde (auch laengere) Bloecke in Ruhe.
BLOCK_WPS = 2.5               # Woerter/Sekunde (Despina ~2,4 gemessen)
BLOCK_MAX_DUR_FACTOR = 2.5    # actual > erwartet * Faktor -> Rauschen-Verdacht -> Fallback


def _wav_duration(path):
    """Audiolaenge eines WAV in Sekunden (0.0 wenn nicht lesbar)."""
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def _wav_md5(path):
    """Inhalts-Hash eines WAV (fuer inkrementelles Alignment: gleicher Hash =
    unveraenderter Schnipsel -> FA ueberspringen). '' wenn nicht lesbar."""
    import hashlib
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""


# ============================================================
# AUDIO-TAGS + KAPITEL
# ============================================================
def _audio_tags(data: dict, chapter):
    """Geordnete Liste (tag_id, entry) ALLER Tags (inkl. p/skip!), optional auf
    ein Kapitel gefiltert. p wird fuer die Absatzerkennung im Planer gebraucht,
    deshalb hier NICHT herausgefiltert -- der Planer verwirft p/skip selbst."""
    out = []
    for tag_id, entry in data["content"].items():
        if chapter and not tag_id.startswith(chapter):
            continue
        out.append((tag_id, entry))
    return out


def _chapter_of(tag_id: str) -> str:
    return tag_id.split("_")[0]


# ============================================================
# STIMME (Speaker-Definer) -- Werk-Parameter mit Fallback
# ============================================================
def _load_voice(book_id: str, override: str = None) -> str:
    if override:
        return override
    path = os.path.join(config.book_dir(book_id), "book.json")
    try:
        bj = json.load(open(path, encoding="utf-8"))
        v = (bj.get("audio_voice") or "").strip()
        if v:
            return v
    except Exception:
        pass
    return config.TTS_VOICE


def _load_block_regie(book_id: str) -> str:
    """Erzaehler-Regie (Typ 's') aus den book.json-Reglern via Stage 56.
    Diese gilt fuer den ganzen Block (eine durchgehende Erzaehlstimme)."""
    try:
        from pipeline.s400_regie import directions_from_reglers, _load_reglers
        return directions_from_reglers(_load_reglers(book_id)).get("s", "")
    except Exception as e:
        print(f"[stage58] WARN: Block-Regie nicht ladbar ({type(e).__name__}) -> leer")
        return ""


# ============================================================
# REGIE + KONTEXT -> prompt-Feld  (Solo/Fallback-Einzelsatz, wie bisher)
# ============================================================
def _build_prompt(direction: str, prev_txt: str, target: str, next_txt: str,
                  is_first: bool, is_last: bool, typ: str = "s") -> str:
    if tts_client.is_gemini_api():
        # 3.8: nur der kurze Stil aus Stage 56 -- keine Meta-Anweisungen, kein Kontext.
        return direction
    if typ == "h":
        extra = ("This is a heading. Read ONLY this short heading exactly as written, "
                 "clearly and plainly. Do NOT add, invent, repeat or read anything else.")
        return f"{direction}\n\n{extra}"

    SHORT_WORDS = 6
    if len(str(target).split()) < SHORT_WORDS:
        extra = ("Read ONLY this short line exactly as written, clearly and plainly. "
                 "Do NOT add, invent, repeat or read anything else.")
        return f"{direction}\n\n{extra}"

    if is_first and is_last:
        extra = ("This chapter stands on a single line — give it appropriate "
                 "weight. Speak it once, naturally.")
    elif is_first:
        extra = ("This is the OPENING line of a chapter — set the scene and give "
                 "it the right weight. For context, the next sentence is:\n"
                 f"(next) {next_txt}\n"
                 "Speak ONLY the opening line itself, once, not the context.")
    elif is_last:
        extra = ("This is the CLOSING line of a chapter — let it land. For "
                 "context, the sentence before it is:\n"
                 f"(prev) {prev_txt}\n"
                 "Speak ONLY the closing line itself, once, not the context.")
    else:
        extra = ("Read this sentence aloud once, as a calm, natural audiobook "
                 "narrator. Speak only this sentence, and do not repeat any part "
                 "of it.")
    return f"{direction}\n\n{extra}"


# ============================================================
# TTS-CLIENT + SYNTHESE
# ============================================================
def _get_client():
    """Platzhalter (Signatur bleibt): der eigentliche Client lebt in tts_client."""
    return tts_client.backend()


def _synthesize(client, text, prompt, lang_code, out_path, voice_name=None):
    # prompt = Regie/Stil. Bei 3.8 -> speech_metadata.style, sonst SynthesisInput.prompt.
    tts_client.synthesize_wav(text, prompt, out_path, voice_name or config.TTS_VOICE, lang_code)


def _synthesize_retry(client, text, prompt, lang_code, out_path, voice_name, label):
    """Synthese mit Retry gegen 'nur Text statt Audio'. Gibt True/False zurueck."""
    for attempt in range(1, RETRIES + 1):
        try:
            _synthesize(client, text, prompt, lang_code, out_path, voice_name)
            return True
        except tts_client.QuotaError as e:
            # Kontingent leer: ganzen Lauf sauber abbrechen (Resume holt spaeter nach).
            print(f"    {label}: ABBRUCH - {e}")
            raise
        except Exception as e:
            if attempt < RETRIES:
                wait = attempt * 3
                print(f"    {label}: Fehler ({type(e).__name__}), warte {wait}s ...")
                time.sleep(wait)
            else:
                print(f"    {label}: ENDGUELTIG fehlgeschlagen: {e}")
    return False


_LEGACY_WARNED = []
_REGIE_38 = {}


def _style_guard(direction: str, typ: str) -> str:
    """3.8-Schutz: 400_regie aus einem ALTEN Stage-56-Lauf enthaelt lange Regie-Saetze
    ("Read this as a calm audiobook narrator. ..."). Die waeren bei 3.8 genau das,
    was Google abraet. -> durch den kurzen 3.8-Stil ersetzen (Aussprache-Teil bleibt).
    Sauberer: Stage 56 neu laufen lassen (kostenlos, deterministisch)."""
    if not tts_client.is_gemini_api() or not direction.startswith("Read "):
        return direction
    if not _LEGACY_WARNED:
        print("[stage58] WARN: 400_regie enthaelt alte Regie-Saetze -> fuer 3.8 gekuerzt. "
              "Empfehlung: Stage 56 neu laufen lassen.")
        _LEGACY_WARNED.append(1)
    base = _REGIE_38.get(typ) or _REGIE_38.get("s") or "calm audiobook narration"
    pron = ""
    i = direction.find(" Pronounce the proper noun")
    if i >= 0:
        pron = direction[i:].strip()
        pron = pron.replace("Pronounce the proper nouns ", "").replace("Pronounce the proper noun ", "")
        pron = "; " + pron.rstrip(".").replace(" in ", " pronounced as in ", 1)
    return base + pron


def _write_mock_wav(out_path: str):
    """Mock: kurze Stille als gueltige WAV -> beweist Pfad + Manifest."""
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 2400)


# ============================================================
# INTERPUNKTION (audio-only)
# ============================================================
_LEX = {}   # 22.10.2026: freigegebenes Aussprache-Lexikon je Sprache (work/aussprache_<lg>.json), wie Chatterbox


def _spr(text, lg, typ):
    from pipeline.sprechtext import sprechtext      # 18.10.2026
    t = sprechtext(text, lg, typ)
    if _LEX.get(lg):
        from tools.tts_paket import lex_text
        t = lex_text(t, _LEX[lg])
    return t


def _ensure_terminal(text: str) -> str:
    """Ergaenzt ein Satzende, falls keins da ist (nur fuer die Vertonung).
    Ein schliessendes Anfuehrungszeichen nach Satzzeichen gilt als Ende."""
    t = text.rstrip()
    if not t:
        return t
    tail = t.rstrip("\"”»’'）)]")          # schliessende Klammern/Quotes ignorieren
    if tail and tail[-1] in _TERMINAL:
        return t
    return t + "."


# ============================================================
# EINZELSATZ vertonen (Solo-Tags UND Fallback) -- alter, bewaehrter Pfad
# ============================================================
def _voice_single(client, tag_id, entry, lg, lang_code, audio_dir, voice_name,
                  direction_layer, all_tags, idx_in_all, is_mock, force) -> str:
    """Vertont GENAU einen Tag (Solo oder Fallback). Gibt den rel. Pfad zurueck,
    oder '' bei Misserfolg/leer. Resume-aware."""
    target = str(entry.get(lg, "")).strip()
    from pipeline.sprechtext import sprechtext      # 18.10.2026: Sprechtext-Regeln (roemische Kapitelnummern)
    target = sprechtext(target, lg, entry.get("type"))
    out_path = os.path.join(audio_dir, f"{tag_id}.wav")
    if not target:
        return ""
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0 and not force:
        return out_path

    # Nachbarn nur im selben Kapitel (fuer Randfall-Regie)
    ch = _chapter_of(tag_id)
    prev_txt = next_txt = ""
    is_first = (idx_in_all == 0) or (_chapter_of(all_tags[idx_in_all-1][0]) != ch)
    is_last = (idx_in_all == len(all_tags)-1) or (_chapter_of(all_tags[idx_in_all+1][0]) != ch)
    if not is_first:
        prev_txt = str(all_tags[idx_in_all-1][1].get(lg, "")).strip()
    if not is_last:
        next_txt = str(all_tags[idx_in_all+1][1].get(lg, "")).strip()

    direction = _style_guard(direction_layer.get(tag_id, {}).get(lg, ""), entry.get("type", "s"))
    prompt = _build_prompt(direction, prev_txt, _ensure_terminal(target), next_txt,
                           is_first, is_last, entry.get("type", "s"))

    if is_mock:
        _write_mock_wav(out_path)
        return out_path
    if _synthesize_retry(client, _ensure_terminal(target), prompt, lang_code,
                         out_path, voice_name, f"{tag_id}"):
        time.sleep(PAUSE_SECONDS)
        return out_path
    return ""


# ============================================================
# HAUPTPROZESS
# ============================================================
def run(book_id: str, chapter: str = None, lang: str = None, force: bool = False,
        limit: int = None, voice: str = None,
        valley_ratio: float = 0.45, fa_pre: float = 0.02,
        cut_guard: float = 0.10,
        keep_blocks: bool = False, reuse_blocks: bool = False) -> dict:
    in_path = config.work_path(book_id, "400_regie")
    print(f"[stage58] Lese: {in_path}")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Vorigen 500_vertonung laden (falls vorhanden) -> vorhandenes Alignment + Hashes
    # fuer INKREMENTELLES Alignment: unveraenderte Schnipsel werden nicht neu
    # ausgerichtet (FA ist die Bremse, besonders bei Reuse-/Reparatur-Laeufen).
    _prev_prod = {}
    _prev_p = config.work_path(book_id, "500_vertonung")
    if os.path.exists(_prev_p):
        try:
            with open(_prev_p, "r", encoding="utf-8") as f:
                _prev_prod = json.load(f).get("production", {})
        except Exception:
            _prev_prod = {}
    prev_align_all = _prev_prod.get("alignment", {})
    prev_hash_all = _prev_prod.get("alignment_hash", {})

    # Modell kommt AUSSCHLIESSLICH aus config (eine Quelle der Wahrheit); hier nur Anzeige.
    print(f"[stage58] TTS-Modell (aus config): {config.MODELS.get('tts', 'gemini-3.8-flash-tts')}")

    direction_layer = data.get("production", {}).get("direction", {})
    langs = [lang] if lang else list(config.ALL_LANGUAGES)
    is_mock = (config.RUN_MODE == "mock")

    voice_name = _load_voice(book_id, voice)
    from tools.tts_paket import lexikon as _lexikon
    for _lg in langs:
        _LEX[_lg] = _lexikon(config.book_dir(book_id), _lg)
        if _LEX[_lg]:
            print(f"[stage58] Aussprache-Lexikon {_lg}: {len(_LEX[_lg])} Eintraege")
    regie_s = _load_block_regie(book_id)
    if tts_client.is_gemini_api():
        try:
            from pipeline.s400_regie import directions_from_reglers, _load_reglers
            _REGIE_38.update(directions_from_reglers(_load_reglers(book_id)))
        except Exception:
            pass
        print(f"[stage58] Backend: Gemini-API (3.8-Steuerung) | Block-Stil: '{regie_s}'")
    print(f"[stage58] Stimme: {voice_name}"
          f"{' (CLI)' if voice else ' (book.json/Fallback)'}  |  Modus: {'mock' if is_mock else 'live'}")

    # Block-Planer auf config-Typen ausrichten (p = Absatzgrenze; p/skip = kein Audio)
    block_planner.BLOCKABLE = {"s", "dl"}
    block_planner.PARA_BREAK = {"p"}
    block_planner.NO_AUDIO = set(getattr(config, "NO_AUDIO_TYPES", ["p", "skip"])) | {"p"}
    block_planner.BLOCK_MIN = getattr(config, "TTS_BLOCK_MIN", block_planner.BLOCK_MIN)
    block_planner.BLOCK_IDEAL = getattr(config, "TTS_BLOCK_IDEAL", block_planner.BLOCK_IDEAL)
    block_planner.BLOCK_MAX = getattr(config, "TTS_BLOCK_MAX", block_planner.BLOCK_MAX)

    all_tags = _audio_tags(data, chapter)                  # inkl. p (fuer Planer)
    tag_entry = {tid: e for tid, e in all_tags}
    # Index in der vollen (audio-relevanten) Reihenfolge fuer Randfall-Regie:
    audio_seq = [(tid, e) for tid, e in all_tags
                 if e.get("type") not in block_planner.NO_AUDIO]
    audio_pos = {tid: i for i, (tid, _e) in enumerate(audio_seq)}

    plan = block_planner.plan_tag_blocks([(tid, e.get("type", "s")) for tid, e in all_tags])

    client = None if is_mock else _get_client()
    keep = keep_blocks or reuse_blocks      # Block-WAVs fuer Schnitt-Wiederholung behalten
    if reuse_blocks:
        print("[stage58] reuse-blocks: vorhandene Block-WAVs werden wiederverwendet (kein TTS).")
    manifest = {}
    total_done = 0
    qa = {}                # je Sprache: geflaggte Bloecke (Solo-Fallback genutzt)
    fa_report = {}         # je Sprache: FA-Grenzreport (valley_depth etc.) fuer QA/Tuning
    alignment = {}         # je Sprache: schnipsel-relative Wortzeiten fuer UI-Highlighting
    alignment_hash = {}    # je Sprache: tag_id -> WAV-Hash (fuer inkrementelles Alignment)

    for lg in langs:
        lang_code = LANG_CODE.get(lg, lg)
        audio_dir = os.path.join(config.book_dir(book_id), "fassungen", lg, "audio")
        os.makedirs(audio_dir, exist_ok=True)
        manifest[lg] = {}
        qa[lg] = {"blocks": 0, "block_clean": 0, "fallback_blocks": [], "solo": 0}
        fa_report[lg] = []

        seg_list = plan[:limit] if limit else plan
        print(f"[stage58] {lg} ({lang_code}): {len(seg_list)} Segmente"
              f"{' | Kapitel '+chapter if chapter else ''}"
              f"{' | LIMIT '+str(limit) if limit else ''}")

        for si, seg in enumerate(seg_list):
            kind = seg["kind"]
            tag_ids = seg["tag_ids"]

            # ---------------- SOLO (h / Titelei / Kurzzeilen) ----------------
            if kind == "solo":
                qa[lg]["solo"] += 1
                tid = tag_ids[0]
                rel = _voice_single(client, tid, tag_entry[tid], lg, lang_code, audio_dir,
                                    voice_name, direction_layer, audio_seq,
                                    audio_pos.get(tid, 0), is_mock, force)
                if rel:
                    manifest[lg][tid] = os.path.relpath(rel, config.book_dir(book_id))
                    total_done += 1
                continue

            # ---------------- BLOCK ----------------
            qa[lg]["blocks"] += 1
            # Zieltext je Satz (audio-only Satzende), leere Saetze ausschliessen
            sentences = [{"id": tid, "text": _ensure_terminal(_spr(str(tag_entry[tid].get(lg, "")).strip(), lg, tag_entry[tid].get("type")))}
                         for tid in tag_ids if str(tag_entry[tid].get(lg, "")).strip()]
            out_paths = [os.path.join(audio_dir, f"{s['id']}.wav") for s in sentences]

            if len(sentences) < 2:
                # Nichts zu schneiden -> als Einzelsatz behandeln
                for s in sentences:
                    rel = _voice_single(client, s["id"], tag_entry[s["id"]], lg, lang_code,
                                        audio_dir, voice_name, direction_layer, audio_seq,
                                        audio_pos.get(s["id"], 0), is_mock, force)
                    if rel:
                        manifest[lg][s["id"]] = os.path.relpath(rel, config.book_dir(book_id))
                        total_done += 1
                continue

            # Resume: ganzer Block schon vorhanden?
            if not force and all(os.path.exists(p) and os.path.getsize(p) > 0 for p in out_paths):
                for s in sentences:
                    manifest[lg][s["id"]] = os.path.relpath(
                        os.path.join(audio_dir, f"{s['id']}.wav"), config.book_dir(book_id))
                total_done += len(sentences)
                qa[lg]["block_clean"] += 1
                continue

            label = f"[{si+1}/{len(seg_list)}] Block {sentences[0]['id']}..{sentences[-1]['id']} ({len(sentences)}S{'!' if seg['forced_internal'] else ''})"

            def _fallback_block(reason):
                """Solo-Fallback: jeden Satz des Blocks einzeln vertonen."""
                print(f"  {label}: FALLBACK ({reason}) -> {len(sentences)} Einzelsaetze")
                qa[lg]["fallback_blocks"].append(
                    {"from": sentences[0]["id"], "to": sentences[-1]["id"],
                     "n": len(sentences), "reason": reason,
                     "forced_internal": seg["forced_internal"]})
                done = 0
                for s in sentences:
                    rel = _voice_single(client, s["id"], tag_entry[s["id"]], lg, lang_code,
                                        audio_dir, voice_name, direction_layer, audio_seq,
                                        audio_pos.get(s["id"], 0), is_mock, force)
                    if rel:
                        manifest[lg][s["id"]] = os.path.relpath(rel, config.book_dir(book_id))
                        done += 1
                return done

            # ----- MOCK: kein TTS/FA -> Pro-Tag-Mock direkt (Orchestrierung testbar) -----
            if is_mock:
                for s in sentences:
                    _write_mock_wav(os.path.join(audio_dir, f"{s['id']}.wav"))
                    manifest[lg][s["id"]] = os.path.relpath(
                        os.path.join(audio_dir, f"{s['id']}.wav"), config.book_dir(book_id))
                total_done += len(sentences)
                qa[lg]["block_clean"] += 1
                print(f"  {label}: mock ({len(sentences)} WAVs)")
                continue

            # ----- LIVE: (1) Block in EINEM Call -- mit Sentinel-Satz am Ende -----
            # Sentinel gibt dem echten Schlusswort ein Folgewort -> innerer Satz ->
            # saubere Schnittregel greift; Sentinel-Segment wird danach verworfen.
            # Eigener Dateiname (_blockS_) markiert: dieses Block-WAV ENTHAELT den
            # Sentinel -> alte _block_-WAVs (ohne Sentinel) werden nicht reused.
            sentinel_txt = _ensure_terminal(SENTINEL.get(lg, SENTINEL["en"]))
            block_wav = os.path.join(audio_dir, f"_blockS_{sentences[0]['id']}.wav")
            if reuse_blocks and os.path.exists(block_wav) and os.path.getsize(block_wav) > 0:
                print(f"  {label}: Block-WAV wiederverwendet (kein TTS-Call)")
            else:
                block_text = " ".join(s["text"] for s in sentences) + " " + sentinel_txt
                if tts_client.is_gemini_api():
                    block_prompt = regie_s          # 3.8: nur kurzer Stil, keine Meta-Anweisung
                else:
                    block_prompt = (regie_s + "\n\n" + BLOCK_INSTRUCTION) if regie_s else BLOCK_INSTRUCTION
                if not _synthesize_retry(client, block_text, block_prompt, lang_code,
                                         block_wav, voice_name, label):
                    total_done += _fallback_block("Block-TTS gescheitert")
                    continue
                time.sleep(PAUSE_SECONDS)

            # ----- (1b) DAUER-PLAUSIBILITAET: Rauschen-Totalausfall abfangen -----
            # Erwartete Laenge aus Wortzahl/Sprechrate; ist das Block-WAV viel laenger,
            # ist der TTS-Call mitten im Block kollabiert (Rauschen) -> Fallback.
            n_words = sum(len(re.findall(r"\w+", s["text"], flags=re.UNICODE)) for s in sentences)
            exp_dur = max(1.0, n_words / BLOCK_WPS)
            act_dur = _wav_duration(block_wav)
            if act_dur > exp_dur * BLOCK_MAX_DUR_FACTOR:
                total_done += _fallback_block(
                    f"Block zu lang ({act_dur:.0f}s vs ~{exp_dur:.0f}s erwartet) -> Rauschen-Verdacht")
                if not keep:
                    _safe_remove(block_wav)
                continue

            # ----- (2) FA-Schnitt + Netz (Sentinel als Phantom-Satz -> Grenze nach Schlusswort) -----
            fa_sentences = sentences + [{"id": SENTINEL_ID, "text": sentinel_txt}]
            try:
                rep = audio_fa.fa_cut(block_wav, fa_sentences, valley_ratio=valley_ratio,
                                      fa_pre=fa_pre, cut_guard=cut_guard)
            except Exception as e:
                total_done += _fallback_block(f"FA-Fehler {type(e).__name__}")
                if not keep:
                    _safe_remove(block_wav)
                continue

            cuts = rep.get("cuts", [])
            bnds = rep.get("boundaries", [])
            # FA-Grenzreport persistieren (valley_depth etc.) -- QA + Schnitt-Tuning.
            # Die letzte Grenze sitzt nach dem echten Schlusswort (vor dem Sentinel).
            for b in bnds:
                fa_report[lg].append({"block": sentences[0]["id"], **b})
            need = len(sentences)          # N echte Saetze + Sentinel -> N Grenzen
            all_ok = (rep["net"]["ok"] and len(bnds) == need
                      and all(b["status"] == "OK" for b in bnds) and len(cuts) == need)
            if not all_ok:
                bad = [f"{b['after_id']}:{b['reason']}" for b in bnds if b["status"] != "OK"]
                total_done += _fallback_block("FLAG " + (",".join(bad) if bad else "Mengen/Schnitt"))
                if not keep:
                    _safe_remove(block_wav)
                continue

            # ----- (3) zerlegen: N echte Schnipsel + 1 Sentinel-Segment (verworfen) -----
            sentinel_tmp = os.path.join(audio_dir, f"_sentinel_{sentences[0]['id']}.wav")
            written = audio_fa.slice_block(block_wav, cuts, out_paths + [sentinel_tmp])
            if not keep:
                _safe_remove(block_wav)
            _safe_remove(sentinel_tmp)     # Sentinel-Segment immer verwerfen
            real_written = written[:len(sentences)]
            if not all(ok for _p, ok in real_written):
                # Ein echtes Segment leer -> ganzer Block in den Fallback (Sicherheit vor Versatz)
                for _p, ok in real_written:
                    if ok:
                        _safe_remove(_p)
                total_done += _fallback_block("leeres Segment nach Schnitt")
                continue

            for s in sentences:
                manifest[lg][s["id"]] = os.path.relpath(
                    os.path.join(audio_dir, f"{s['id']}.wav"), config.book_dir(book_id))
            total_done += len(sentences)
            qa[lg]["block_clean"] += 1
            print(f"  {label}: ok (Block geschnitten -> {len(sentences)} WAVs)")

        print(f"[stage58] {lg}: Bloecke {qa[lg]['block_clean']}/{qa[lg]['blocks']} sauber, "
              f"{len(qa[lg]['fallback_blocks'])} im Fallback, {qa[lg]['solo']} Solo-Tags")

        # ----- Wort-Alignment (nativ, schnipsel-relativ) fuer UI-Highlighting -----
        # Jeder fertige Schnipsel-WAV wird gegen seinen Satztext ausgerichtet ->
        # Wortzeiten in ms ab Schnipselanfang. Korrekt-per-Konstruktion (kein
        # Block-Offset noetig). Nur live (FA braucht torch); in mock uebersprungen.
        # INKREMENTELL: unveraenderte Schnipsel (gleicher WAV-Hash wie im vorigen
        # Lauf) behalten ihre Ausrichtung -> kein FA. Spart bei Reuse-/Reparatur-
        # Laeufen ~alle FA-Laeufe; nur die wirklich neuen Schnipsel werden gerechnet.
        alignment[lg] = {}
        alignment_hash[lg] = {}
        if is_mock or os.environ.get("READLAYER_58_OHNE_FA") == "1":
            # 15.10.2026: Wortzeiten kommen aus Stage 58c -> FA hier optional (spart ~1/3 Laufzeit)
            alignment[lg] = dict(prev_align_all.get(lg, {}))
            alignment_hash[lg] = dict(prev_hash_all.get(lg, {}))
        else:
            prev_a = prev_align_all.get(lg, {})
            prev_h = prev_hash_all.get(lg, {})
            n_new, n_reused = 0, 0
            for tag_id, rel in manifest[lg].items():
                wav_path = os.path.join(config.book_dir(book_id), rel)
                cur_hash = _wav_md5(wav_path)
                # Unveraendert + vorhandene Ausrichtung -> uebernehmen, kein FA
                if cur_hash and prev_h.get(tag_id) == cur_hash and tag_id in prev_a:
                    alignment[lg][tag_id] = prev_a[tag_id]
                    alignment_hash[lg][tag_id] = cur_hash
                    n_reused += 1
                    continue
                text = str(tag_entry[tag_id].get(lg, "")).strip()
                try:
                    words = audio_fa.align_words(wav_path, text)
                except Exception as e:
                    print(f"  [align] {tag_id}: FA-Fehler {type(e).__name__} -> uebersprungen")
                    continue
                alignment[lg][tag_id] = [{"id": f"{tag_id}_w{i+1}", **w}
                                         for i, w in enumerate(words)]
                alignment_hash[lg][tag_id] = cur_hash
                n_new += 1
            n_words = sum(len(v) for v in alignment[lg].values())
            print(f"[stage58] {lg}: Wort-Alignment {n_new} neu / {n_reused} uebernommen "
                  f"({len(alignment[lg])} Schnipsel, {n_words} Woerter) -> production.alignment")

    # Schlankes Manifest + QA fuer Resume / Assembler / Pruefung
    data.setdefault("production", {})["audio_manifest"] = manifest
    data["production"]["audio_voice_used"] = voice_name
    data["production"]["audio_qa"] = qa
    data["production"]["audio_fa"] = fa_report
    data["production"]["alignment"] = alignment
    data["production"]["alignment_hash"] = alignment_hash
    out_json = config.work_path(book_id, "500_vertonung")
    # 15.10.2026: parallele Kapitel-Laeufe -> unter Sperre mit dem aktuellen Stand auf der Platte zusammenfuehren
    _sperre = out_json + ".lock"
    for _ in range(600):
        try:
            _fd = os.open(_sperre, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(_fd)
            break
        except FileExistsError:
            time.sleep(0.5)
    try:
        if chapter and os.path.exists(out_json):
            with open(out_json, "r", encoding="utf-8") as f:
                disk = json.load(f).get("production", {})
            for key in ("audio_manifest", "alignment", "alignment_hash"):
                neu = data["production"].get(key, {})
                alt = disk.get(key, {}) or {}
                for _lg, eintraege in neu.items():
                    alt.setdefault(_lg, {}).update(eintraege or {})
                data["production"][key] = alt
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    finally:
        try:
            os.remove(_sperre)
        except OSError:
            pass

    print(f"[stage58] Fertig: {total_done} Schnipsel vertont "
          f"({'mock' if is_mock else 'live'}), Stimme {voice_name}. Manifest -> {out_json}")
    return data


def _safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    book = args[0] if args else "jekyll-and-hyde"

    def _opt(name):
        if name in sys.argv:
            i = sys.argv.index(name)
            return sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        return None

    _lim = _opt("--limit")
    _vr = _opt("--valley-ratio")
    _fp = _opt("--fa-pre")
    _cg = _opt("--cut-guard")
    run(book,
        chapter=_opt("--chapter"),
        lang=_opt("--lang"),
        force="--force" in sys.argv,
        limit=int(_lim) if _lim else None,
        voice=_opt("--voice"),
        valley_ratio=float(_vr) if _vr else 0.45,
        fa_pre=float(_fp) if _fp else 0.02,
        cut_guard=float(_cg) if _cg else 0.10,
        keep_blocks=("--keep-blocks" in sys.argv) or ("--keep-block" in sys.argv),
        reuse_blocks=("--reuse-blocks" in sys.argv) or ("--reuse-block" in sys.argv))
