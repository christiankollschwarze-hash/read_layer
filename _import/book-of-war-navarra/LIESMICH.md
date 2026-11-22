# Navarra 1910 – Eingang Pipeline (22.11.2026)

Inhalt
- raw.txt – Volltext mit ###TITLE###/###AUTHOR###/###CHAPTER### (20 Kapitel), Rechtschreibung 1910,
  Fußnoten als Absatz „Anmerkung: …“ direkt nach dem Bezugsabsatz, Gedichte: ein Vers je Absatz.
- anlegen.json – Eingabe für tools/s100_anlegen.py (Altweg): Autor Sunzi (Q37151), Übersetzer Navarra †1911.
- bilder_vorlage.json – 29 Bilder mit Kapitel + Ankertext (Ende des Absatzes davor bzw. KAPITELANFANG).
- images/bilder/navarra_NN.png – Originalillustrationen 1910, gesäubert.
- bildanker.py – allgemeine Fassung von tools/pooh_bildanker.py (liest work/bilder_vorlage.json).

Schritte (aus C:\Users\sabin\read_layer)
1. copy _import\book-of-war-navarra\bildanker.py tools\bildanker.py
2. python tools\s100_anlegen.py _import\book-of-war-navarra\anlegen.json
3. python tools\s100_anlegen.py book-of-war-navarra --textquelle vorhanden --uebersetzer-todesjahr 1911
4. xcopy _import\book-of-war-navarra\images authors\sunzi\books\book-of-war-navarra\images\ /E /I /Y
   copy _import\book-of-war-navarra\bilder_vorlage.json authors\sunzi\books\book-of-war-navarra\work\
5. python run.py book-of-war-navarra --to 200   (115 → original; 120 Kapitel-Gate: 20 Kapitel bestätigen)
6. python tools\bildanker.py book-of-war-navarra --probe   (nach 120)
   python tools\bildanker.py book-of-war-navarra           (nach 200) → work\bilder.json
7. Weiter bis 400; Kosten ab 500 nur nach Freigabe.
