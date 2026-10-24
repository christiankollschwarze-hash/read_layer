# PIPELINE.md – Statusdatei Pipeline-Lead (read_layer)

## Versionsverwaltung (seit 24.10.2026)
- Git-Repo `read_layer`, Zweig `main`, erster Commit „Ausgangsstand 24.10.2026“.
- Ausgeschlossen (.gitignore): Audio, Modelle/Adapter, `authors/**/raw.txt|images|output|_alt_*`, `users/`, `archive/`, Logs, `.env`, `JSON_Key/`.
- Nachtsicherung: `start_git_sicherung.bat`, Windows-Aufgabe „READ LAYER Git-Sicherung“ täglich 23:00, Log `cockpit/logs/git_sicherung.txt`.
- Regel: keine neuen `.bak`-Dateien mehr; Altstände liegen in `archive/2026-10-24_bak/`. Änderungen = Commit mit Kurzbeschreibung.
