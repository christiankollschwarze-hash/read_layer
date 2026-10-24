# Testset Prosodie v0.1 (30 Sätze)

Markup nach Vokabelheft v0.1. Für die Baseline wird derselbe Text ohne Markup synthetisiert (Parser entfernt Emojis, `*`, `|`, `@`, `{}`).
Texte sind Eigenentwürfe, frei nutzbar. Nach jedem Lauf gleiche Reihenfolge, gleiche Referenzstimme, fester Seed.

## Bewertung (je Satz 1-5, vorher/nachher)
- **V** Verständlichkeit und Aussprache
- **S** Stimmung passend
- **B** Betonung sitzt auf dem richtigen Wort
- **P** Pausen natürlich
- **A** Artefakte (Nachhall, Abbrüche, Wiederholungen): 5 = keine

## Deutsch

- **DE01** neutral, Baseline (Satzmelodie, Rhythmus)
  `Am Morgen lag der Nebel noch über den Wiesen, und der Fluss zog still an den Weiden vorbei.`
- **DE02** fröhlich
  `😄 Endlich Ferien! Wir packen die Koffer, wir nehmen den frühen Zug, und heute Abend sitzen wir am Meer.`
- **DE03** traurig
  `😢 Das Haus war leer, nur der Stuhl am Fenster stand noch dort, wo sie immer gesessen hatte.`
- **DE04** wütend mit Betonung
  `😠 Ich habe dir *gesagt*, dass du die Tür nicht offen lassen sollst, und du hast es *schon wieder* vergessen!`
- **DE05** flüsternd
  `🤫 Leise jetzt, || sie schlafen noch. Wenn wir die Treppe hinunter wollen, müssen wir an der dritten Stufe vorbei.`
- **DE06** erschrocken
  `😱 Hinter ihm krachte die Tür ins Schloss, und im selben Augenblick erlosch das Licht!`
- **DE07** nachdenklich mit Pausen
  `🤔 Vielleicht | war es gar nicht der Zufall, || der uns hierher geführt hat, | sondern etwas, das wir nicht sehen konnten.`
- **DE08** liebevoll
  `🥰 Komm her, mein Kleiner. Es ist alles gut, ich bin ja da, und morgen früh gehen wir zusammen zu den Enten.`
- **DE09** verschmitzt
  `😏 Natürlich habe ich nichts gesehen. Ich war ja die ganze Zeit hier, genau neben dem leeren Kuchenteller.`
- **DE10** ironisch
  `🙄 Oh, großartig. Noch ein Meeting, das auch eine E-Mail hätte sein können.`
- **DE11** Dialog, Sprecherwechsel
  `@Erzähler: Anna blieb an der Tür stehen. @Anna: 🤔 Und wenn er nicht zurückkommt? @Max: 🙂 Er kommt zurück. Er kommt immer zurück.`
- **DE12** Zahlen, Namen, Lexikon
  `Am 14. März 1848 reiste {Wilhelmine|Vilhelmine} Schmidt mit 3 Koffern und 250 Mark nach Zürich.`
- **DE13** archaisches Vokabular
  `Gar sehr verwunderte sich der Alte ob solcher Rede, und er sprach: Wohlan, so lasst uns denn des Weges ziehen.`
- **DE14** langer Schachtelsatz
  `Der Mann, der gestern Abend, als es schon dunkel wurde und die Laternen angezündet waren, noch vor dem Haus gestanden hatte, kam nicht mehr wieder.`
- **DE15** Tempo und Szenenpause
  `🐢 Langsam öffnete sie den Brief. ||| 🐇 Und dann ging alles ganz schnell: Wir rannten die Treppe hinab, durch den Hof und auf die Straße!`

## Englisch

- **EN01** neutral, Baseline
  `By the time the lamps were lit, the street had emptied, and only the sound of the river remained.`
- **EN02** überrascht
  `😮 You came all this way? I had no idea, I really thought you were still abroad!`
- **EN03** ängstlich
  `😨 Something moved in the cellar. I heard it twice, and both times it was closer than before.`
- **EN04** müde
  `😴 I haven't slept properly in days, and the letters on the page keep sliding away from me.`
- **EN05** dramatisch/feierlich
  `🎭 And so, upon the last night of the old kingdom, || the bells rang out over the silent towers.`
- **EN06** freundlich
  `🙂 Good morning! Come in, sit down, and let me put the kettle on. You must be freezing.`
- **EN07** wütend mit Betonung
  `😠 I told you *twice* not to touch the lock, and now the whole door is ruined!`
- **EN08** Dialog, Sprecherwechsel
  `@Narrator: The captain turned from the window. @Captain: 🤔 How many days of water do we have left? @Mate: 😨 Four, sir. Perhaps five.`
- **EN09** Namen, Lexikon
  `Ms. {Featherstonehaugh|Fanshaw} arrived at 7:45 on the 3rd of November, carrying 12 letters for Mr. {Cholmondeley|Chumley}.`
- **EN10** archaisch
  `Thou shalt not pass, quoth the old knight, for I have sworn an oath upon this bridge, and none shall break it.`
- **EN11** langer Satz mit Kommas
  `He walked slowly, hat in hand, through the long gallery, past the portraits of men he had never met, and out into the garden.`
- **EN12** Betonung in der Satzmitte
  `I did not say *he* stole the money. | I only said that someone did.`
- **EN13** traurig
  `😢 The last train had gone, and she stood alone on the platform, holding a ticket for nowhere.`
- **EN14** Tempo und Pause
  `🐢 Wait. || Listen. ||| 🐇 Now run, run, run, before they close the gates behind us!`
- **EN15** Intensität (Verdopplung) und Frage/Ausruf
  `😠😠 How dare you stand there and ask me why? Get out of my house!`

## Hinweise zur Auswertung
- DE und EN getrennt bewerten, Mittelwerte pro Kriterium und Stimmung bilden.
- Besonders beobachten: DE04/EN07 (Betonung), DE11/EN08 (Sprecherwechsel), DE12/EN09 (Lexikon), DE15/EN14 (Tempo, Pausen), EN15 (Intensität, Obergrenze von `exaggeration`).
- Neue Problemfälle aus echten Hörproben ergänzen und mit Datum versehen (v0.2).
