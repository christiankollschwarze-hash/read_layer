# TODO / KONZEPT — Kurzsatz-Doppler (Saetze < 5 Woerter)

> Festgehalten 15.06.2026 spaet. NICHT heute bauen (CK: erst Gelbe Tapete fertig).
> Sauber spezifiziert, damit es beim naechsten Mal richtig gebaut wird statt schnell.

## Befund (empirisch, gehoert + gemessen)
- Sleepy Hollow/de: nach allen Fixes 3 hartnaeckige Doppler, die sich NICHT
  wegwuerfeln lassen (--fix passes 2 -> konstant dieselbe Zahl):
    c001_00455 "Was sollte er tun?"        (4 W) -> gehoert 8 = 2x
    c001_00458 "Er erhielt keine Antwort."  (4 W) -> gehoert 8 = 2x
    c001_00460 "Noch immer keine Antwort."  (4 W) -> gehoert 8 = 2x
- CK hat reingehoert: ECHTE Doppler (Satz wird zweimal gesprochen), KEINE
  Whisper-Messgrenze.
- Ursache: SEHR kurze Saetze (<= ~5 W) -> dem Modell zu wenig "Material" ->
  es fuellt durch WIEDERHOLUNG. Deterministisch (jeder Kurzsatz neigt dazu),
  daher wuerfelt sich's nicht weg. Die nackte "do not repeat"-Anweisung in
  stage_58 _build_prompt reicht bei dieser Kuerze NICHT.

## Entscheidung (CK)
- Loesung: Saetze < 5 Woerter an den NACHBARN anhaengen (zusammen vertonen).
- Alignment fuer DIESE Saetze bewusst aufgegeben -- es sind narrative Fuellsaetze
  ("Er erhielt keine Antwort."), kein "Upps!!"-Lernstoff. Fuer TAELLA unkritisch.

## ARCHITEKTUR-HAKEN (warum es KEIN Zweizeiler ist)
Zusammenlegen bricht die 1:1-Beziehung **Tag-ID <-> WAV**, auf der die ganze
Kette steht:
- Zwei Tags teilen sich dann eine WAV -> STT-Check, Manifest, Assembler fragen
  "wo ist die WAV fuer den angehaengten Tag?".
- Naiver Weg (Nachbar mit ins text-Feld, eine WAV unter erster Tag-ID) erzeugt
  zwei Folgeprobleme: (a) STT-Check flaggt den langen Schnipsel dauerhaft als
  "zu viele Woerter"; (b) der Nachbar wird doppelt vertont (einmal angehaengt,
  einmal als eigener Schnipsel) -> Dopplung im Hoerbuch.
-> Sauber loesen heisst: das MERGEN als echten Schritt modellieren, nicht
   im Prompt tricksen.

## Sauberer Loesungsweg (Vorschlag, spaeter)
- Merge auf TAGGER-Ebene (Stage 50) ODER als eigener Vor-Schritt: benachbarte
  Tags zu EINEM Audio-Tag zusammenfassen, wenn der erste < N Woerter hat.
  - Merge-Regel: kurzer Satz + Folgesatz -> ein kombinierter Tag (z.B.
    c001_00458+459) mit zusammengefuegtem Text, EINE Tag-ID, EINE WAV.
  - Soll-Wortzahl fuer STT = Summe -> Mengenpruefung bleibt korrekt, kein
    Fehlalarm.
  - Manifest/Assembler sehen weiterhin saubere 1:1 Tag<->WAV.
  - Pausen-Dramaturgie: Pause des kombinierten Tags = Pause des LETZTEN Teilsatzes.
- Schwelle N konfigurierbar (Vorschlag <=5 Woerter). An mehreren Werken testen
  (Kurzsaetze "Ja." "Er schwieg." "Was nun?" kommen ueberall vor).
- ACHTUNG TAELLA: gemergte Saetze sind nicht mehr einzeln antippbar. Nur fuer
  Saetze anwenden, die als Lernstoff entbehrlich sind -- oder als bewusste
  Produktentscheidung dokumentieren.

## Heute-Workaround (akzeptiert)
- Die 3 Doppler in Sleepy Hollow/de bleiben stehen (3 von 502 = 99,4% sauber).
  Bei Bedarf manuell die 2 betroffenen WAVs nachbearbeiten (zweite Haelfte
  abschneiden) -- aber nicht noetig fuer einen Test-/Ersttitel.
