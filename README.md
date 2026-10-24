# READ LAYER — MVP Pipeline

Multilinguale Hörbuch-/E-Book-Pipeline. Ein Quelltext wird satz-aligned
in mehrere Sprachen übersetzt und vertont.

## Schnellstart (lokal)

1. Python 3.11+, dann:  `pip install requests python-dotenv`
2. API-Keys als Umgebungsvariablen setzen (nur für --live nötig):
   `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`
3. Lauf im Mock (kostenlos, testet Mechanik):
   `python run.py aesop_three_fables`
4. Lauf mit echten Modellen:
   `python run.py aesop_three_fables --live`

## Befehle
- `python run.py <book_id>`            ganzer Lauf (Checkpoints aktiv)
- `python run.py <book_id> --from 03`  ab Stage 03 fortsetzen
- `python run.py <book_id> --only 04b` nur eine Stage
- `python run.py <book_id> --force`    Checkpoints ignorieren, neu rechnen
- `python run.py <book_id> --live`     echte APIs statt Mock

## Struktur
- `config/config.py`   — alle Parameter (Sprachen, Modelle, Pausen, Tag-Schema)
- `pipeline/`          — die 9 Stages + api_layer
- `data/raw/`          — Eingabe: <book_id>_marked.txt (manuell mit ###MARKER###)
- `data/work/`         — Zwischenstände pro Stage (Checkpoints)
- `data/output/<id>/`  — finale Audio-Schnipsel + manifest.json
- `docs/BOARD.md`      — Ideen-Board (später)

## Pipeline-Stages
00 Tagger → 01 Profiler → 02 Pretranslator → 03 Translator →
04a Integrity → 04b Backtranslation → 05 SSML+Pausen → 06 Phoneme → 07 TTS

## Neuen Titel hinzufügen
1. Text als `data/raw/<book_id>_marked.txt` ablegen, mit Markern:
   ###TITLE### / ###AUTHOR### / ###CHAPTER###
2. `python run.py <book_id>`
