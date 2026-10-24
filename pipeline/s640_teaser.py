"""STAGE 640 — Teaser-Audio
Funktion:     Vertont den Klappentext je Sprache.
Wirkungsweise: Gemini-TTS je Satz, Resume pro Datei; Checkpoint nur bei vollstaendigen Snippets.
Komponenten:  pipeline/s640_teaser.py, tts_client
Zulieferer:   s600 Klappentext (work/600_klappentext.json)
Abnehmer:     Katalog / App (fassungen/<lang>/blurb/, work/640_teaser.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 10: Blurb-Vertonung (Schaufenster-Audio, PRO SPRACHE)
========================================================================
Nimmt den Klappentext aus Stage 09 (work/600_klappentext.json) und legt ihn EINSPRACHIG
je Fassung ab -- Text UND Audio nebeneinander:

    fassungen/<lang>/blurb/text/blurb.json      (geordnete Saetze NUR dieser Sprache)
    fassungen/<lang>/blurb/audio/<id>.mp3        (ein Satz = eine MP3)
    fassungen/<lang>/blurb/audio/manifest.json   (Schnipsel-Liste dieser Fassung)

Damit ist jede Fassung self-contained: der SOMNIO-Assembler (Stage 59) findet den
Blurb-Vorspann seiner Sprache direkt; TÆLLA aligned DE/EN ueber die identischen
Schnipsel-IDs (gleicher block_index in beiden Sprachordnern -> "Upps!!").

Frueher: ein flacher, MEHRSPRACHIGER teaser_audio/ auf Werk-Ebene. Abgeloest --
der einsprachige Blurb ist eine FASSUNGS-Sache und gehoert unter fassungen/<lang>/.

Autornamen-Aussprache (Variante D, getestet): Name in der AUSGANGSSPRACHE des
Werks; bei fremdsprachigem Satz kontextueller Prompt-Hinweis, natuerlich + unbetont.

Checkpoint (run.py): work_path(book_id, "640_teaser") (kleine Statusdatei, alle Sprachen).

UMBAU 08.10.2026 (Gemini 3.8 TTS via pipeline/tts_client.py):
  - Steuerung: Text wortgetreu, Regie als KURZER style (kein "Read the following..."),
    Autornamen-Hinweis als Stil-Stichwort.
  - 3.8 liefert WAV, kein MP3 -> Umwandlung per ffmpeg. Ohne ffmpeg bleibt die
    Datei .wav und das Manifest verweist darauf.
"""

import os, json, time, re, shutil, subprocess
from config import config
from pipeline import tts_client

STAGE = "640_teaser"

LANG_CODE = {"de": "de-DE", "en": "en-US", "fr": "fr-FR", "ru": "ru-RU", "es": "es-ES", "it": "it-IT"}
LANG_NAME = {"de": "German", "en": "English", "fr": "French", "ru": "Russian", "es": "Spanish", "it": "Italian"}


# ---- Text-Normalisierung fuer die TTS ----------------------------------
# Quelle ist Gutenberg-Rohtext; dessen Markup darf nicht in die Sprachsynthese.
# _wort_ / *wort* = Kursiv-Marker -> nur der Inhalt bleibt. '--' = Gedankenstrich.
_EMPH_US  = re.compile(r"_([^_\n]+)_")     # _kursiv_  -> kursiv
_EMPH_AST = re.compile(r"\*([^*\n]+)\*")   # *kursiv*  -> kursiv

def _clean_text(t: str) -> str:
    """Entfernt Kursiv-/Betonungs-Marker und Gutenberg-Artefakte aus dem
    Vertonungstext. Aendert NICHT den in 600_klappentext.json gespeicherten Rohtext."""
    t = _EMPH_US.sub(r"\1", t)
    t = _EMPH_AST.sub(r"\1", t)
    t = t.replace("_", " ")                # uebrig gebliebene Einzel-Marker
    t = re.sub(r"(?<!\w)\*|\*(?!\w)", "", t)
    t = t.replace("--", "\u2014")          # Doppel-Bindestrich -> Gedankenstrich
    t = re.sub(r"\s{2,}", " ", t).strip()  # Mehrfach-Leerzeichen glaetten
    return t


def _build_prompt(snippet_lang, src_lang, autor, text=""):
    if tts_client.is_gemini_api():
        style = "calm, warm narration"
        if autor and src_lang and snippet_lang != src_lang and autor in text:
            nl = LANG_NAME.get(src_lang, "its original language")
            style += f"; {autor} pronounced as in {nl}, unstressed"
        return style
    spoken = LANG_NAME.get(snippet_lang, "the following")
    base = f"Read the following {spoken} text aloud in a calm, warm narrator voice"
    # Aussprache-Hinweis NUR, wenn der Name wirklich in diesem Satz steht und die
    # Satzsprache von der Wirkungssprache abweicht. Sonst wird das Modell auf einen
    # nicht vorhandenen Namen gehetzt -> Stolpern/Wiederholungen.
    if autor and src_lang and snippet_lang != src_lang and autor in text:
        nl = LANG_NAME.get(src_lang, "its original language")
        base += (f". It contains the name '{autor}' \u2014 pronounce it with {nl} phonetics, "
                 f"but completely naturally and WITHOUT special emphasis, as just another "
                 f"word in the flowing sentence")
    return base + ":"


def _write_audio(out_mp3, data_wav):
    """3.8: WAV -> MP3 per ffmpeg. Gibt den tatsaechlichen Dateinamen zurueck."""
    ff = shutil.which("ffmpeg")
    wav = out_mp3[:-4] + ".wav"
    open(wav, "wb").write(data_wav)
    if not ff:
        return os.path.basename(wav)
    r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", wav, "-codec:a", "libmp3lame",
                        "-q:a", "2", out_mp3], capture_output=True)
    if r.returncode == 0 and os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 0:
        os.remove(wav)
        return os.path.basename(out_mp3)
    return os.path.basename(wav)


def _collect(blurb, lang):
    """Schnipsel EINER Sprache, geordnet nach Block + Index.
    ID OHNE Sprach-Suffix -- der Ordner kodiert die Sprache schon. Dadurch
    heissen DE/EN-Schnipsel gleich und liegen alignierbar nebeneinander."""
    snippets = []
    for block in ("koeder", "einordnung", "autor"):
        for i, sent in enumerate(blurb.get(block, []), 1):
            text = _clean_text((sent.get(lang) or "").strip())
            if text:
                snippets.append({"id": f"{block}_{i:02d}", "lang": lang,
                                 "block": block, "index": i, "text": text})
    return snippets


def _fassung_blurb_dirs(book_id, lang):
    """fassungen/<lang>/blurb/{text,audio} -- inline gebildet (config.py unveraendert,
    konsistent mit den uebrigen Fassungs-Stages)."""
    base = os.path.join(config.book_dir(book_id), "fassungen", lang, "blurb")
    return os.path.join(base, "text"), os.path.join(base, "audio")


def _write_text(text_dir, lang, snippets):
    """Materialisiert die Einzelsprach-Saetze als blurb.json (Quelle bleibt 600_klappentext.json;
    dies ist die fertige, vertonte Fassung dieser Sprache -- gratis, auch im Mock)."""
    os.makedirs(text_dir, exist_ok=True)
    doc = {"lang": lang,
           "snippets": [{"id": s["id"], "block": s["block"],
                         "index": s["index"], "text": s["text"]} for s in snippets]}
    json.dump(doc, open(os.path.join(text_dir, "blurb.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


def run(book_id):
    langs = config.ALL_LANGUAGES

    blurb_data = json.load(open(config.work_path(book_id, "600_klappentext"), encoding="utf-8"))
    blurb = blurb_data["blurb"]
    # Autorname + Wirkungssprache aus Stage 09 (autor-zentriertes Modell).
    # Reihenfolge: Top-Level (neu) -> meta.autor (Rueckwaerts-Kompat.) -> leer.
    autor = (blurb_data.get("autor")
             or blurb_data.get("meta", {}).get("autor", "")
             or "")
    # Aussprache des Namens in der Wirkungssprache des Autors (Variante D),
    # Fallback auf globale Ausgangssprache, falls wirkungssprache leer ist.
    src_lang = (blurb_data.get("wirkungssprache") or config.SOURCE_LANGUAGE)

    files = {}   # (lang, id) -> tatsaechlicher Dateiname (mp3 oder wav)

    grand_total, grand_done = 0, 0
    per_lang = {}

    for lang in langs:
        text_dir, audio_dir = _fassung_blurb_dirs(book_id, lang)
        snippets = _collect(blurb, lang)
        if not snippets:
            print(f"[640_teaser] {lang}: keine Saetze in 600_klappentext.json -> uebersprungen")
            continue

        # Text immer materialisieren (gratis, datenseitig -- auch im Mock).
        _write_text(text_dir, lang, snippets)
        os.makedirs(audio_dir, exist_ok=True)

        total, done = len(snippets), 0
        print(f"[640_teaser] {lang}: {total} Schnipsel | Autor='{autor}' | src={src_lang}")

        if config.RUN_MODE == "mock":
            for sn in snippets:
                open(os.path.join(audio_dir, f"{sn['id']}.mp3"), "wb").write(b"MOCK")
            done = total
        else:
            for n, sn in enumerate(snippets, 1):
                out = os.path.join(audio_dir, f"{sn['id']}.mp3")
                alt = out[:-4] + ".wav"
                if os.path.exists(out) and os.path.getsize(out) > 0:
                    done += 1; continue
                if os.path.exists(alt) and os.path.getsize(alt) > 0:
                    files[(lang, sn["id"])] = os.path.basename(alt); done += 1; continue
                prompt = _build_prompt(sn["lang"], src_lang, autor, sn["text"])
                for attempt in range(1, 5):
                    try:
                        if tts_client.is_gemini_api():
                            wav = tts_client.synthesize_bytes(sn["text"], prompt, config.TTS_VOICE)
                            files[(lang, sn["id"])] = _write_audio(out, wav)
                        else:
                            mp3 = tts_client.synthesize_bytes(sn["text"], prompt, config.TTS_VOICE,
                                                              LANG_CODE.get(lang, "en-US"), fmt="mp3")
                            open(out, "wb").write(mp3)
                        done += 1
                        print(f"  [{lang} {n}/{total}] {sn['id']}: ok")
                        break
                    except Exception as e:
                        if attempt < 4: time.sleep(attempt * 3)
                        else: print(f"  [{lang} {n}/{total}] {sn['id']}: FEHLER {e}")
                time.sleep(config.TTS_DELAY_SECONDS)

        # Manifest pro Fassung (in den Audio-Ordner).
        manifest = {"lang": lang, "voice": config.TTS_VOICE, "model": config.MODELS["tts"],
                    "autor": autor, "source_language": src_lang,
                    "snippets": [{"id": s["id"], "file": files.get((lang, s["id"]), f"{s['id']}.mp3"), "block": s["block"],
                                  "index": s["index"], "text": s["text"]} for s in snippets]}
        json.dump(manifest, open(os.path.join(audio_dir, "manifest.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

        per_lang[lang] = {"snippets": total, "done": done, "audio_dir": audio_dir}
        grand_total += total; grand_done += done
        print(f"[640_teaser] {lang}: {done}/{total} -> {audio_dir}")

    # QF-3 (18.10.2026): Checkpoint nur bei Vollstaendigkeit -- sonst holt der naechste
    # Lauf die fehlenden Snippets nach (vorhandene Dateien werden uebersprungen).
    if grand_done < grand_total:
        print(f"[640_teaser] UNVOLLSTAENDIG: {grand_done}/{grand_total} -- kein Checkpoint, "
              f"bitte Stage 40 erneut starten.")
        return
    # kleine Checkpoint-Statusdatei fuer run.py (ueber alle Sprachen).
    json.dump({"languages": list(per_lang.keys()), "per_lang": per_lang,
               "snippets": grand_total, "done": grand_done},
              open(config.work_path(book_id, STAGE), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"[640_teaser] Fertig: {grand_done}/{grand_total} ueber {len(per_lang)} Sprachen.")


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else "time_machine")
