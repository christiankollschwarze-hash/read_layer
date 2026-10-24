# BEFUND — Charon: gelegentliches unnatuerliches Hochsetzen der Stimmlage

> Festgehalten 18.06.2026. Beobachtung CK beim Durchhoeren von Sleepy Hollow/de.
> Text-/Uebersetzungsqualitaet "wirklich toll" -- aber Charon setzt die Stimmlage
> ab und zu unnatuerlich hoch, passt dann nicht zum Kontext.

## Beobachtung
- Charon zieht vereinzelt die Tonhoehe nach oben, ohne dass Inhalt/Satz es hergibt.
- Bei Aoede (Yellow Wallpaper) NICHT aufgefallen -> moeglicherweise ein
  Charon-Merkmal (wie schon die hoehere Doppler-Neigung bei Charon).

## Erklaerung (Modellverhalten)
- Jeder Schnipsel = eigener, KONTEXTLOSER TTS-Call (noetig fuers Alignment).
  Charon hat keinen Tonhoehen-Anker zum Vorsatz -> Stimmlage kann springen.
- Ausloeser vermutlich: (1) Satzzeichen, die als Frage/Ausruf gedeutet werden
  (Doppelpunkt/Semikolon/rhetorische Saetze); (2) kurze Saetze (wenig Kontext
  zum "Erden" der Melodie -- gleiche Wurzel wie Doppler); (3) Sampling-Varianz
  bei Temperatur > 0.
- WICHTIG: Es ist NICHT-DETERMINISTISCH und STT-UNSICHTBAR (Wortmenge stimmt,
  nur die Prosodie kippt) -> automatische Detektion schwer. Praevention > Detektion.

## Loesungs-Idee (CK): Grundtonlage in die Regie (Stage 56)
- In directions_from_reglers einen festen Tonlagen-Anker mitgeben, z.B.
  "keep a calm, low, even vocal register, without rising in pitch".
- Ziel: Charon BEHALTEN (sonore Maennerstimme passt zu Irvings Erzaehlton --
  Aoede ist KEIN Ersatz, das ist eine INHALTLICHE Stimmwahl), aber das
  Hochrutschen daempfen.

## Vorbehalte (ehrlich -- vor dem Bauen testen)
1. PROMPT-HYPOTHESE: Charon ignoriert Prompt-Anweisungen bei kurzen Schnipseln
   nachweislich (4 Doppler-Varianten heute alle wirkungslos). Tonlagen-Hinweis
   koennte bei genau den anfaelligen Saetzen verpuffen.
2. AUSDRUCK vs. STABILITAET: zu strikter Tonlagen-Befehl koennte die natuerliche
   Modulation in direkter Rede daempfen (die CK bei Sleepy Hollow gelobt hat).
   Balance noetig: kein Ausreisser nach oben, aber nicht monoton.
3. Koennte Charon-Merkmal sein -> A/B gegen andere Stimme zur Einordnung.

## NAECHSTER SCHRITT (morgen, frischer Kopf)
- A/B mit tts_probe an ein paar HOCHGERUTSCHTEN Saetzen aus Sleepy Hollow:
  Charon MIT "low, even register"-Hinweis vs. Charon OHNE.
- Pruefen: greift der Hinweis? UND: bleibt die Modulation in direkter Rede erhalten?
- Wenn es greift -> als fester Baustein in Stage 56 (Grundtonlage pro Schnipsel).
- Wenn nicht -> als bekannte Charon-Limitation akzeptieren / Stimme pro Werk waehlen.
