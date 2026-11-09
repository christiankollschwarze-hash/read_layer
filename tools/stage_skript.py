"""Erzeugt docs/STAGE_SKRIPT.md (Stage-Skript: Ziel, zuliefernd, folgend, betroffen je Stage).
Abhaengigkeiten live aus pipeline/kette.py + pipeline/status.STAGES; Ziele/Texte hier gepflegt.
Aufruf: py -3.11 tools/stage_skript.py"""
import os, sys
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = {"080": [], "090": ["080"], "095": ["090"], "100": ["095"], "110": ["100"], "150": ["095"],
 "115": ["110", "150"], "120": ["115"], "190": ["120"], "195": ["190"], "200": ["195"], "210": ["200"],
 "300": ["210"], "310": ["300"], "320": ["310"], "330": ["320"], "340": ["330"], "400": ["330"],
 "410": ["400"], "420": ["410"], "500": ["400", "410"], "510": ["500", "420"], "530": ["500", "510"],
 "520": ["530", "340"], "540": ["510", "530", "520"], "600": ["190", "330"], "610": ["600"],
 "615": ["610", "410"], "620": ["615", "650"], "630": ["615", "330", "650"], "640": ["600", "410"],
 "650": ["530", "615"], "700": None, "710": ["700"]}
ORD = ["080","090","095","100","110","150","115","120","190","195","200","210","300","310","320","330","340",
       "400","410","420","500","510","530","520","540","600","610","615","620","630","640","650","700","710"]
try:
    sys.path.insert(0, BASE)
    from pipeline import kette as _k, status as _s
    V, ORD = dict(_k.VORGAENGER), list(_s.STAGES)
except Exception:
    pass
D = {
"080": ("Mandant & Rechte", "Querschicht", "immer",
  "Legt fest, wem das Werk gehört (Somnio, User, Verlag) und wer welche Aktion ausführen darf. Jede Gate-Entscheidung wird mit wer/wann protokolliert."),
"090": ("Eingangsweiche", "Eingang", "immer",
  "Bestimmt die Eingangsart (Gutenberg, mitgebrachte TXT, User-/Verlags-ePub, Fremd-Audio geparkt), prüft Rechte-Versicherung und DRM und leitet zu 100 oder 150 weiter."),
"095": ("Produktwahl", "Eingang", "immer",
  "Hält die Bestellung fest (Sprache × Inhalt × Stufe × Kanal), prüft sie gegen die Gültigkeitsmatrix und setzt daraus, welche Stages laufen und welche entfallen."),
"100": ("Werk anlegen", "Eingang", "Gutenberg, user_txt",
  "Legt Autor, Werk, Index-Eintrag und Rohtext (raw.txt) an. Prüft Marken, Länge, Sprache (nur Sprachliste) und EU-Gemeinfreiheit bzw. PD-/Rechte-Nachweis."),
"110": ("Wikidata", "Eingang", "Gutenberg, user_txt",
  "Verifiziert den Autor (Lebensdaten, Q-ID) und das Werk (Werk-Q-ID, Titel je Sprache) gegen Wikidata; zweite PD-Prüfung."),
"150": ("ePub-Import", "Eingang", "user_epub, verlag_epub",
  "Liest ein ePub ein: Kapitel, Text, Metadaten, Bilder/Fußnoten, Cover und vorhandenen Klappentext; prüft Inhaltsanteil, Sprache, DRM."),
"115": ("Fassungsweiche", "Text", "immer",
  "Legt die Fassung fest (heute modernisiert/original; entschieden: original | modernisiert | einfach | gekürzt | glace) und prüft das Bearbeitungsrecht."),
"120": ("Modernisierung (sanft)", "Text", "immer",
  "Erkennt Kapitel (künftig eigene Stage 118) und modernisiert den Text sanft; prüft Absatzabdeckung, Längen, Ausreißer, Eigennamen, Lizenzreste."),
"190": ("Eingangsvertrag", "Vertrag", "immer",
  "Rein automatischer Vertrag: alle Pflichtdateien des Textwegs vorhanden, Kapitelzahl stimmig, Text deckungsgleich. Danach gilt der Werktext als fest."),
"195": ("Teilung", "Text", "immer",
  "Teilt sehr lange Werke (> ca. 400.000 Zeichen) an Kapitelgrenzen in Teile <slug>-1…n; danach läuft die Kette in den Teilen weiter."),
"200": ("Tagging", "Text", "alles außer reinem Text-ePub in Ausgangssprache",
  "Zerlegt den Text in Knoten (ein Knoten = ein Satz, Typen s/dl/p/qt/h …) mit festen IDs – das Gerüst für Übersetzung, Audio und App."),
"210": ("Profil", "Text", "Übersetzung oder Audio bestellt",
  "Erstellt das Werkprofil: Stil, Figuren (Übersetzung, Aussprache), Unübersetztes, Glossar, Redewendungen; steuert Übersetzung und Casting."),
"300": ("Vorübersetzung", "Übersetzung", "Zielsprache bestellt",
  "Übersetzt kapitelweise als Anker für die satzgenaue Übersetzung (je Zielsprache)."),
"310": ("Übersetzung", "Übersetzung", "Zielsprache bestellt",
  "Übersetzt jeden Knoten in jede bestellte Zielsprache; prüft Abdeckung, Sprache, Länge, Glossar, Kapitelschema."),
"320": ("Integrität", "Vertrag", "Zielsprache bestellt",
  "Rein automatischer Vertrag: ID-Menge, Quelltext und Zielsprachen gegenüber 200/310 vollständig und unverändert."),
"330": ("Rückübersetzung", "Übersetzung", "Zielsprache bestellt",
  "Bewertet jede Übersetzung per Rückübersetzung (Score je Satz), repariert geflaggte Sätze; liefert den endgültigen Zieltext."),
"340": ("Wort-Alignment", "Übersetzung", "TÆLLA-Produkt in Zielsprache",
  "Ordnet Wörter Quelle ↔ Ziel zu (Anker für Wort-Tippen und Karaoke), inkl. Prüfaligner für verschobene Anker."),
"400": ("Regie", "Audio", "Audio bestellt",
  "Erzeugt je Knoten und Audiosprache den Sprechtext (Zahlen, römische Ziffern, Aussprache), Pausen und bei Premium/Drama Regieanweisungen."),
"410": ("Casting", "Audio", "Audio bestellt",
  "Besetzt Erzähler und (Hörspiel) Figuren mit Stimmen; prüft Passung und Abstand; casting.json ist die einzige Stimmablage."),
"420": ("Sprecher", "Audio", "Hörspiel bestellt",
  "Ordnet jedem Satzsegment den Sprecher zu (Erzähler oder Figur) – Drehbuch fürs Hörspiel."),
"500": ("Vertonung", "Audio", "Audio bestellt",
  "Vertont jeden Satz (Basic Chatterbox, Premium/Drama Gemini) nach Kostenfreigabe; prüft jeden Satz per Forced Alignment."),
"510": ("Hörspiel-Overlay", "Audio", "Hörspiel bestellt",
  "Erzeugt Figuren-Takes und montiert sie in die Hörspielspur; die Hörbuchspur bleibt unberührt."),
"530": ("Audio-Prüfung", "Audio", "Audio bestellt",
  "Erstellt die Endfassung: Ränder, Tempo, Lautheit je Kapitel, Sprachprüfung je Satz; gekippte Sätze zurück an 500/510."),
"520": ("Wortzeiten", "Audio", "TÆLLA-Audio",
  "Misst Wortzeiten auf der Endfassung (Karaoke) und überträgt sie über die Anker (525) auf die andere Sprache."),
"540": ("Trennung", "Audio", "Hörspiel bestellt",
  "Prüft, ob Figurenstimmen hörbar vom Erzähler getrennt sind (ECAPA); Nachrunde oder Umbesetzen."),
"600": ("Klappentext", "Vermarktung", "immer",
  "Übernimmt oder erzeugt den Klappentext (Köder, Einordnung, Autor) je Sprache mit Pflichtvermerken; Metadaten für Cover und Teaser."),
"610": ("Cover", "Vermarktung", "immer",
  "Erzeugt die Cover-Illustration (ohne Text) einmal je Werk und prüft sie bildtechnisch."),
"615": ("Cover final", "Vermarktung", "immer",
  "Setzt Titel, Autor, Vermerke und ggf. Sprecher auf die Illustration – je Sprache × Variante (Text, Audio, quadratisch); einmalige Sichtfreigabe."),
"620": ("ePub Ausgangssprache", "Ausgabe", "Kanal EPUB in Ausgangssprache",
  "Baut das ePub der Ausgangssprache (Text, bei Hörbuch Basic EPUB3 mit Media Overlay); epubcheck Pflicht."),
"630": ("ePub Zielsprache", "Ausgabe", "Kanal EPUB in Zielsprache",
  "Baut das ePub je Zielsprache aus dem Text nach 330 (Text bzw. Audio-Variante)."),
"640": ("Teaser", "Vermarktung", "TÆLLA-Produkt",
  "Vertont den Klappentext als Hör-Teaser für das Katalog-Schaufenster der App."),
"650": ("Hörbuch-Assembler", "Ausgabe", "Hörbuch Basic für Extern oder EPUB3-Audio",
  "Fügt die Satz-Clips zu Kapiteldateien (MP3/M4B) mit Ansagen, Metadaten, Cover und Satz-Zeitmarken zusammen."),
"700": ("Auslieferungs-Vertrag", "Vertrag", "immer",
  "Prüft vor jeder Auslieferung, dass für jedes bestellte Produkt alle Pflicht-Artefakte vorhanden, frei und aktuell sind."),
"710": ("Auslieferung", "Ausgabe", "immer",
  "Liefert aus: TÆLLA-Cloud (Manifest, Audio, Wortzeiten, Cover, Teaser), EPUB-Download, Extern-Paket; erstes Freischalten im Katalog durch Mensch."),
}
HILFE = {}
try:
    import json as _json
    with open(os.path.join(BASE, "config", "stage_hilfe.json"), encoding="utf-8") as _f:
        HILFE = {k: v for k, v in _json.load(_f).items() if not k.startswith("_")}
except (OSError, ValueError):
    pass
_ohne = [x for x in ORD if x not in D]
if _ohne:
    print("WARNUNG: Stage(s) ohne Beschreibung, nicht im Skript:", _ohne)
ORD = [x for x in ORD if x in D]
def vor(s):
    v = V[s]; return ORD[:ORD.index(s)] if v is None else v
NACH = {s: [t for t in ORD if s in vor(t) and V[t] is not None] for s in ORD}
for s in ORD:
    if s not in ("700", "710") and not NACH[s]: NACH[s].append("700")
def betroffen(s):
    out, st = set(), list(NACH[s])
    while st:
        x = st.pop()
        if x in out: continue
        out.add(x); st += NACH[x]
    if s not in ("700", "710"): out |= {"700", "710"}
    return sorted(out, key=ORD.index)
def vorkette(s):
    out, st = set(), list(vor(s))
    while st:
        x = st.pop()
        if x in out: continue
        out.add(x); st += vor(x)
    return sorted(out, key=ORD.index)
L = lambda xs: ", ".join(f"{x} {D[x][0]}" for x in xs) or "–"
K = lambda xs: " · ".join(xs) or "–"
o = []
o.append("# STAGE-SKRIPT – Read Layer Pipeline (Stand 04.11.2026)\n")
o.append("Je Stage: Name, Ziel, Bereich, wann sie läuft, **zuliefernde** Stages (direkte Eingänge, deren Gate frei sein muss), **folgende** Stages (die direkt auf ihr aufbauen) und **betroffene** Stages in der Kette (alle, die bei einem Neulauf veraltet sind und neu laufen müssen).\n")
o.append("Quelle der Abhängigkeiten: `pipeline/kette.py` (VORGAENGER, Reihenfolge = `pipeline/status.STAGES`); Ziele aus `GATE_KATALOG.md`; „Produziert“ und „Mensch entscheidet“ aus `config/stage_hilfe.json` (dieselben Texte wie das Hilfe-Popup im Cockpit). Regeln: 700 kommt nach der letzten bestellten Stage (alle davor) und ist daher bei jeder Stage betroffen; unter „folgend“ steht 700 nur, wenn sonst nichts folgt; entfällt ein Zulieferer laut Bestellung (095), springt die Kette auf dessen Zulieferer.\n")
o.append("## Reihenfolge\n")
o.append(" → ".join(ORD) + "\n")
o.append("## Übersicht\n")
o.append("| Stage | Name | Bereich | läuft bei | zuliefernd | folgend |\n|---|---|---|---|---|---|")
for s in ORD:
    n, b, l, z = D[s]
    o.append(f"| {s} | {n} | {b} | {l} | {K(vor(s)) if V[s] is not None else 'alle davor'} | {K(NACH[s])} |")
o.append("\n## Stages im Einzelnen\n")
for s in ORD:
    n, b, l, z = D[s]
    o.append(f"### {s} {n}\n")
    o.append(f"- **Ziel:** {z}")
    h = HILFE.get(s) or {}
    if h.get("produziert"):
        o.append(f"- **Produziert:** {h['produziert']}")
    if h.get("mensch"):
        o.append(f"- **Mensch entscheidet:** {h['mensch']}")
    o.append(f"- **Bereich / läuft bei:** {b} · {l}")
    o.append(f"- **Zuliefernd:** {'alle bestellten Stages davor' if V[s] is None else L(vor(s))}")
    o.append(f"- **Folgend:** {L(NACH[s])}")
    bt = betroffen(s)
    o.append(f"- **Betroffen in der Kette (bei Neulauf):** {K(bt)}" + (f" ({len(bt)} Stages)" if bt else ""))
    vk = vorkette(s)
    o.append(f"- **Gesamte Vorkette:** {K(vk)}\n")
o.append("## Entschieden, noch nicht in der Kette (Fassungsweiche 115, CK 03.11.2026)\n")
o.append("| Stage | Name | Ziel | zuliefernd | folgend |\n|---|---|---|---|---|")
o.append("| 118 | Kapitel | Kapitelplan manuell prüfbar (aus 120 herausgelöst), läuft bei allen Fassungen und nach 150 (übernimmt Verlags-Kapitelprüfung) | 115 (bzw. 150) | 120 / 122 / 124 / 125 |")
o.append("| 122 | Einfache Sprache | Fassung „einfach“ | 118 | 190 |")
o.append("| 124 | Gekürzte Lesung | Fassung „gekürzt“ (Nummer Vorschlag) | 118 | 190 |")
o.append("| 125 | Glace | Fassung „glace“ | 118 | 190 |")
o.append("\nAußerhalb der Pipeline: 900 LoRA-Training, 910 Sprecherauswahl LibriVox (Schnittstelle nur über freigegebene Adapter in 410/500). 345 ist Teil von 340, 525 Teil von 520.\n")
ziel = os.path.join(BASE, "docs", "STAGE_SKRIPT.md") if os.path.isdir(os.path.join(BASE, "docs")) else "STAGE_SKRIPT.md"
fehlt = [x for x in ORD if x not in D]
if fehlt:
    print("WARNUNG: ohne Beschreibung:", fehlt)
with open(ziel, "w", encoding="utf-8") as f:
    f.write("\n".join(o))
print("geschrieben:", ziel)
