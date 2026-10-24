# PROZESS – Hörbare Trennung Figur ↔ Erzähler (Hörspiel-Schicht)

Stand 16.10.2026. Übergabe für eine neue Sitzung. Projektordner: `C:\Users\sabin\read_layer`.
Bezug: PROJEKTSTAND.md (Eintrag 16.10.2026), docs/BERICHT_trennung_cotw_2026-10-16.md, claude/PROZESS_hoerspiel-schicht.md.

## Ziel

Jede Figurenstimme im Hörspiel ist hörbar vom Erzähler getrennt, ohne künstlich zu klingen.
Das gilt in jedem Werk automatisch. Nur am Tor entscheidet CK.

## Soll-Prozess je Werk

| # | Schritt | Werkzeug | Ergebnis | Tor |
|---|---|---|---|---|
| 1 | Einzelstimmen-Fassung (Erzähler) | Stage 58 (Gemini) | `fassungen/<lg>/audio` | – |
| 2 | Casting mit Abstandsregel | `py -3.11 -m pipeline.stage_57_casting <werk>` (bestehende Besetzung: `--trennung`) | `casting.json`: `trennung` + `korrektur` je Figur und Sprache | Stimmen-Tor (CK) |
| 3 | Sprecherzuordnung | Stage 57b + `tools/kontrollansicht_docx.py` | `sprecher.json` | Kontrollansicht (CK) |
| 4 | Overlay | `tools/overlay_vorbereiten.py` → Modal `gpu_overlay/overlay_modal.py` → `tools/overlay_montage.py` (wendet `korrektur` nach dem VC an) | `audio_overlay/vc` | – |
| 5 | Prüfung am Overlay | `tools/trennung_messen.py` → Modal `gpu_messung/messung_modal.py` → `tools/trennung_auswerten.py` | Urteil je Figur | **Hörspiel-Prüfung** |
| 6 | Rückfluss | Auswertung schreibt nach `casting.json`: ok / Korrektur anpassen / umbesetzen | höchstens 1 Nachrunde (zurück zu 4) | Umbesetzungs-Tor (CK) |
| 7 | optional Hörtest | Generator → Artifact „TÆLLA Hörtest Stimmen“ → `tools/blindtest_auswerten.py` | Urteil Dritter | – |

## Regel (gilt, Datei `stimmen_archiv/_trennungsregel.json`)

- **Abstand:** `D = sqrt((dF0/1,438)^2 + (dVTL/0,445)^2)`, beides in Halbtönen. Gemessen wird Figur (Zielstimme bzw. VC-Ergebnis) gegen den **Erzähler des Werks**, nicht gegen seine Archiv-Hörprobe.
  - F0 wird zweistufig ermittelt (Hirst).
  - VTL kommt aus dem Formantabstand F1–F4, mit fester Formantdecke 5500 Hz.
- **Schwellen:**

  | Status | Bereich |
  |---|---|
  | zu nah | D < 3,24 |
  | knapp | 3,24 ≤ D < 4,06 |
  | getrennt (Ziel) | D ≥ 4,06 |

  Geeicht an 105 Gleich- und 5355 Verschieden-Paaren aus dem Stimmen-Archiv (EER 21,7 %).
- **Prüfkriterium am Overlay (ECAPA):** Kosinus-Abstand Figur ↔ Erzähler ≥ 0,599 (EER 8,6 %), und die Figur bleibt näher an ihrer Zielstimme als am Erzähler.
- **Korrektur nach dem VC (Praat „Change gender“):**
  - Richtung: weg vom Erzähler auf der gemessenen VTL-Achse. Den Steckbrief zieht die Regel nur heran, wenn die VTL-Differenz unter 2 % liegt.
  - knapp: Formantfaktor 1,05 bzw. 0,97.
  - zu nah: Formantfaktor 1,10 bzw. 0,94.
  - Tonhöhe: Standard 0.
- **Natürlichkeitsgrenzen (CK, hart codiert):** Formantfaktor 0,94–1,10, Tonhöhe höchstens ±2 HT. Reicht das nicht: **umbesetzen**, nicht stärker verbiegen.

## Befunde, die die Regel begründen (Ruf der Wildnis, DE, 77 Spannen)

- Die Regel „Zielstimme gegen Werk-Erzähler“ hat das Overlay-Ergebnis 5/5 richtig vorhergesagt.
- herr_a im Archiv und herr_a im Werk sind für ECAPA verschiedene Sprecher (0,64).
- Chatterbox VC übernimmt etwa 65 % der F0- und etwa 70 % der VTL-Differenz. Der Erzähler hebt Zitate selbst um 1–4 HT an, das VC nimmt das wieder zurück.
- `tonhoehe_ht` vor dem VC (am Quellaudio) kommt nur zu etwa einem Fünftel an. Das ist überholt.
- Tonhöhe allein ändert die Sprecheridentität kaum (Perrault +3 HT: ECAPA unverändert 0,40). Der Hebel ist der Formant.
- −3 HT zusammen mit Formant 0,9 klang wie ein Stimmverzerrer (CK).
- **Runde 3:**

  | Figur | ECAPA vorher → nachher | pyannote: Anteil getrennt |
  |---|---|---|
  | François (1,10) | 0,71 → 0,88 | 5 % → 37 % |
  | Perrault (1,10) | 0,40 → 0,68 | 0 % → 39 % |
  | Hal | 0,68 | 90 % |
  | Mercedes | 0,83 | 99 % |
  | Thornton (0,94) | 0,46 → 0,55, nicht getrennt | 40 % |

  Thornton muss umbesetzt werden.
- **pyannote:**
  - Kontrolle nur Erzähler: 1 Sprecher, 0 s Verwechslung.
  - Fehlerrate (DER) 0,25 → 0,21. Davon sind etwa 0,10 der Sockel aus der Spracherkennung, den auch die reine Erzählerspur hat.
  - Kurze Zitate werden schwach getrennt (Wechsel-Recall etwa 27 %).
- Baskerville-Bug behoben: `erzaehler_stimme` gilt fest, auch bei Ich-Erzählern.

## Ist-Stand Code

- **Teil der Pipeline (fertig):**
  - `pipeline/trennung.py`: Messung, Regel, Richtung, Grenzen.
  - `pipeline/voice_registry.py`: `beste_stimme` sortiert nach ok > knapp > zu nah.
  - `pipeline/stage_57_casting.py`: Erzähler fest; `trennung`/`korrektur` je Figur; `--trennung [--neu]` für bestehende Besetzungen.
  - `tools/overlay_korrektur.py`: Funktion `anwenden`, mit Grenzen.
  - `tools/overlay_montage.py`: ruft die Korrektur auf und montiert aus `spannen/vc_korr`.
  - `tools/klaviatur_trennung.py`: Daten für die Klaviatur (Artifact auf claude.ai).
  - Backups: `*.bak_20261016`.
- **Werkbank (seit 16.10.2026 werkunabhängig, Backups `*.bak_20261016b`):**
  - `start_trennung_messen.bat <werk> [lg|de,en] [--korrektur] [--eichen]`: Paket + Runde (`--runde auto`) + Praat → Modal (je Sprache ein T4, höchstens 10 gleichzeitig) → Auswertung + Rückfluss.
  - `tools/trennung_messen.py <werk> <lg>`: Eichung nur mit `--eichen`; `--korrektur` aus `casting.json`; `--runde auto|<name>`; Paket wird neu gebaut, wenn das Overlay neuer ist.
  - `tools/trennung_auswerten.py <werk> <lg>`: schreibt `pruefung[lg]` je Figur und `hoerspiel_tor[lg]` nach `casting.json` (ok / nachrunde / umbesetzen).
  - Cockpit-Reiter „Hörspiel-Prüfung“: Ampel, Messwerte, Hörproben, Knöpfe, Umbesetzungs-Kandidaten mit „wählen“.
  - `tools/blindtest_bauen.py <werk> <lg>` → `gpu_messung/<werk>_<lg>/blindtest_<runde>/hoertest.html`; `tools/blindtest_auswerten.py <ordner> <werk> <lg>`.
  - `start_umbesetzen.bat <werk> <lg> "<Figur>"` (`tools/umbesetzen.py`): Kandidaten höher/heller und größer/dunkler, gemessen gegen den Werk-Erzähler; Wahl im Cockpit.
  - `start_overlay_teil.bat <werk> <lg> "<Figur>"`: Overlay nur für eine Figur; frühere Teilpakete bleiben erhalten (`_teil_v<n>`).

## Arbeitspaket für die neue Sitzung

Status 16.10.2026: Punkte 1–5 umgesetzt. Punkt 6 vorbereitet (Werkzeuge stehen, Stimmdesign läuft nur unter Windows: `start_umbesetzen.bat call-of-the-wild de "John Thornton"`). Punkt 7 offen.

1. **`trennung_messen.py` allgemein machen:**
   - Parameter `<werk> <lg>`.
   - Die Archiv-Eichung nur mit `--eichen`. Sonst Regel und Schwellen aus `_trennungsregel.json`; die Modal-Ausgabe braucht dann keine Archivsegmente.
   - `--korrektur` ohne Figurennamen, stattdessen alle Figuren mit `korrektur` in `casting.json`.
   - `--runde <name>` für alle Sprachen.
2. **`start_trennung_messen.bat <werk> <lg>`** parametrieren. Modal-Limit beachten: höchstens 10 GPUs gleichzeitig.
3. **Rückkopplung in `trennung_auswerten.py`.** Je Figur schreibt sie `pruefung` nach `casting.json` (ECAPA, pyannote, Runde, Urteil):
   - getrennt und näher an der Zielstimme → ok.
   - nicht getrennt, Grenze noch nicht ausgeschöpft → Korrektur eine Stufe weiter, Richtung aus der Overlay-Messung (VC gegen Nachbar-Erzähler).
   - nicht getrennt an der Grenze, oder entfernt sich von der Zielstimme → `umbesetzen`.
   - Höchstens eine Nachrunde.
4. **Cockpit-Schritt „Hörspiel-Prüfung“** (`cockpit/server.py`, `index.html`), nach dem Overlay:
   - Torseite mit Ampel je Figur: D, ECAPA vorher/nachher, pyannote, Korrektur.
   - Hörproben vorher/nachher je Figur.
   - Knöpfe: Freigeben / Nachrunde / Umbesetzen.
5. **Hörtest-Generator** als `tools/blindtest_bauen.py <werk> <lg>`: Paare Erzähler/Figur vorher/nachher plus Kontrollen → HTML aus Vorlage → Artifact republish. Vorlage und Seite: Artifact „TÆLLA Hörtest Stimmen“; die Antworten liegen in dessen Datenbank, Sammlung `antworten`.
6. **Thornton (Ruf der Wildnis) neu besetzen.**
   - Kein Archivkandidat passt und liegt zugleich weit genug vom Erzähler.
   - Neue Stimme designen mit Abgrenzung zu Arthur (herr_a): hörbar höher und heller oder hörbar größer, D ≥ 4,06 gegen den Werk-Erzähler.
   - Probe → CK-Tor → Overlay nur Thornton → Prüfung.
7. Dasselbe für die Vorschläge aus Alice, Baskerville und Wie es euch gefällt (`--trennung` ist dort schon gelaufen): Overlay, Prüfung, Tor.

**Abnahme**
- Ein beliebiges Werk läuft ohne Codeänderung durch die Schritte 4 bis 6.
- Das Cockpit zeigt das Tor.
- Für Ruf der Wildnis gilt: alle Figuren ECAPA getrennt und näher an ihrer Zielstimme, keine Korrektur außerhalb der Grenzen.

## Voraussetzungen

- **Windows:** `py -3.11 -m pip install praat-parselmouth soundfile` (fehlt noch; ohne das fällt Stage 57 auf den Grundton allein zurück).
- **Modal:** HF_TOKEN steht in `.env`. Die Bedingungen für pyannote 3.1 und segmentation-3.0 sind akzeptiert. Ein Lauf kostet etwa 0,03 $.
- **Lange Läufe** über Windows-Batch starten. VM-Hintergrundprozesse sterben, wenn der Aufruf endet.

## Startsatz für die neue Sitzung

> Lies PROJEKTSTAND.md und claude/PROZESS_abstandsregel.md. Setze das Arbeitspaket Punkt 1–5 um (Prozess allgemein machen, Rückkopplung, Cockpit-Tor, Hörtest-Generator), danach Punkt 6 (Thornton).
