# AP – Kuratormodus Teil 2: Rücklauf

Stand 16.10.2026. Übergabe für eine neue Sitzung. Projektordner: `C:\Users\sabin\read_layer`.
Bezug: PROJEKTSTAND.md, Eintrag „12.10.2026 – Kuratormodus im Mock-Up (Testumgebung) – Teil 1 gebaut“.

## Ziel

Anmerkungen aus dem Kuratormodus werden abgearbeitet, ohne das ganze Werk neu zu erzeugen. Je Anmerkung wird nur der betroffene Satz korrigiert, neu vertont und in die Demo übernommen. Am Ende steht die Anmerkung auf „erledigt“ und ist belegt.

## Ausgangslage (Teil 1, fertig)

- **Erfassen:** Im Mock-up unter Einstellungen → Kuratormodus. Beim Lesen den Satz lang drücken, beim Hören die Stift-Taste.
- **Kategorien:** Sprecher, Aussprache, Übersetzung, Text, Audio, Wortzeit, Sonstiges. Dazu eine Notiz und gegebenenfalls `sprecher_neu`.
- **Ablage:** `authors/<autor>/books/<slug>/work/kuration.jsonl`, eine Zeile je Anmerkung. Felder: `id`, `zeit`, `status` ("offen"), `slug`, `tag_id`, `kategorie`, `notiz`, `sprache`, `modus`, `sekunde`, `text_en`, `text_de`, `sprecher_neu`.
- **Schreiben:** über den Vite-Dev-Server (`taella-app/vite.config.js`, `/api/kuration`), ohne Server Fallback auf localStorage.
- **Unsichere Sprecher:** 57b markiert sie in `sprecher.json` mit `"pruefen"` und listet sie in `work/sprecher_pruefen.txt`.

## Bestand offen (16.10.2026)

| Werk | Anzahl | Kategorien |
|---|---|---|
| the-hound-of-the-baskervilles | 11 | aussprache (DE-Satz englisch vorgetragen) |
| alice-s-adventures-in-wonderland | 4 | aussprache 2, audio 1, uebersetzung 1 |
| as-you-like-it | 2 | sprecher 1, text 1 |

## Rücklauf je Kategorie

| Kategorie | Maßnahme | Neu erzeugen |
|---|---|---|
| sprecher | `sprecher.json` für `tag_id` korrigieren (`sprecher_neu`, sonst Vorschlag DeepSeek mit Kontext), Status `bestaetigt` | Satz-Audio (Hörspiel: nur Overlay-Spanne), dann 58c für den Satz |
| aussprache | Satz mit `TTS_SPRACH_STIL` neu vertonen; Eigennamen-Hinweis aus profile/pronunciation; vorher automatische Prüfung der Sprache mit lokaler Spracherkennung (DE gekippt nach EN?) | Satz-Audio + 58c |
| audio | wie aussprache, ohne Textänderung | Satz-Audio + 58c |
| uebersetzung | Vorschlag DeepSeek (Satz + Nachbarsätze + Notiz) → CK-Tor → `stage06` (DE) ersetzen, 54a für den Satz | Satz-Audio DE + 54a + 58c DE |
| text | wie uebersetzung, Sprache laut Anmerkung | wie uebersetzung |
| wortzeit | nur 58c für den Satz | 58c |
| sonstiges | Aufgabenliste für CK, keine Automatik | – |

Danach `tools/export_demo.py <slug>` (nur betroffene Manifeste/Wortzeiten); die Anmerkung bekommt `status: "erledigt"` mit `erledigt_am`, `massnahme` und `vorher/nachher`.

## Arbeitspaket

1. **`tools/kuration_ruecklauf.py <slug> [--nur kategorie] [--trocken]`:**
   - liest die offenen Anmerkungen und teilt sie nach Kategorie ein,
   - erzeugt `work/kuration_plan.json` mit der Maßnahme je Anmerkung,
   - `--trocken` zeigt nur den Plan.
2. **Satzweise Werkzeuge, ohne Neulauf ganzer Kapitel:**
   - Satz neu vertonen: Gemini, Stimme laut `book.json`/`casting.json`, mit `TTS_SPRACH_STIL`. Gegebenenfalls `stage_58_cloud_tts` mit Tag-Filter oder ein kleiner Wrapper.
   - 58c nur für einzelne Tags: lokal auf der CPU reicht bei wenigen Sätzen.
   - 54a nur für einzelne Tags.
   - Vorher immer Backup des alten Satz-Audios: `fassungen/<lg>/audio/_kuration_alt/<tag>_<datum>.wav`.
3. **Sprachprüfung je DE-Satz-Audio:** lokale Spracherkennung (faster-whisper ist vorhanden) erkennt Sätze, die ins Englische gekippt sind. Gleich mit auf das ganze Werk anwenden; das ist zugleich das Reparaturpaket Baskerville DE aus PROJEKTSTAND 13.10.
4. **Übersetzungs- und Text-Vorschläge** als Tor, im Cockpit oder vorerst als Kontrollansicht (Word, `tools/kontrollansicht_docx.py` erweitern): alt / neu / Notiz, CK kreuzt an.
5. **Status-Rückschreibung** in `kuration.jsonl` (nichts löschen, Zeile aktualisieren) und erneuter Export in den Demo-Ordner.
6. **Mock-up:** Erledigte Anmerkungen nicht mehr unterstreichen; Filter „offen/erledigt“ in der Kuratorliste.
7. **Kostenlog:** Rücklauf-Kosten getrennt in `work/kosten.jsonl` (Stage `kuration`).

## Abnahme

- Alle 17 offenen Anmerkungen sind erledigt oder als CK-Aufgabe markiert.
- Baskerville: Die Sprachprüfung meldet keinen DE-Satz mehr als Englisch.
- Im Mock-up sind die korrigierten Sätze hörbar neu, die Wortzeiten stimmen.
- Kein ganzes Kapitel wurde neu vertont.

## Hinweise

- Lange Läufe über Windows-Batch mit `title READ LAYER - <Job>`. VM-Hintergrundprozesse sterben, wenn der Aufruf endet.
- Gemini-TTS-Tageslimit: etwa 10.000 Anfragen; hier unkritisch.
- Wird Ruf der Wildnis im Hörspiel-Job bearbeitet: dessen `sprecher.json`/Overlay nicht anfassen.

## Startsatz für die neue Sitzung

> Lies PROJEKTSTAND.md und claude/AP_kuratormodus_teil2.md. Setze das Arbeitspaket um; zuerst `kuration_ruecklauf.py --trocken` für alle drei Werke zeigen.
