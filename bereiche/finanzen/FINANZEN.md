# FINANZEN — CFO TÆLLA / Read Layer / SOMNIO
Stand: 17.10.2026 (Sitzung 1). Basis: taella_ertragsmodell.xlsx, kosten.jsonl (254 Werke), PROJEKTSTAND.md, ANFORDERUNGEN.md, VERTRIEB.md.
Währung: API-Kosten in $ (so abgerechnet), Preise in €.

## 1 Ist-Kosten (nachgerechnet aus work/kosten.jsonl)
- Geloggt 10.–16.10.2026: **146,06 $** (Gemini-Text 89,28 · DeepSeek 40,96 · Bild 12,77 · TTS 3,05).
- Größter Einzelposten: Stage 55 Validator gemini-2.5-flash 51,83 $ (seit 12.10. auf DeepSeek umgestellt).
- Nicht im Log: Modal (GPU), Stage 57/57b, TTS vor 12.10., Abos/Infra. -> Monatsfixkosten fehlen (CK liefert).
- TTS gemessen (As You Like It): 3,73 h Audio = 3,05 $ -> **0,82 $/Audio-h** (bestätigt Annahme 0,81).

## 2 Stückkosten (Durchschnittswerk Startliste: 99.266 Wörter ≈ 10,7 h je Sprache; 9.300 Wörter/h)
| Posten | 2026 | ab 01.01.2027 |
|---|---|---|
| Text (Modernisierung, Übersetzung, 11–56), 0,09 $/1.000 W | 8,93 $ | 8,93 $ |
| Hörbuch Gemini, je Sprache (0,81 / 1,62 $/h) | 8,65 $ | 17,30 $ |
| Hörbuch Chatterbox/Modal, je Sprache (0,94 $/h) | 10,05 $ | 10,05 $ |
| Hörspiel-Overlay (VC, nur Zitat-Spannen) | < 1 $ je Werk (Ruf der Wildnis ~0,50 $) | gleich |
| **Werk EN+DE Hörbuch (EN Chatterbox, DE Gemini)** | **27,63 $** | **36,28 $** |
Direktkosten je fertiger Audiostunde inkl. Text: 2026 ≈ 1,65 $, 2027 ≈ 2,46 $.
Engpass ist CK-Zeit (Tore, Hörproben), nicht Geld.

## 3 Kapitalbedarf je Ausbaustufe (Direktkosten, ohne Fixkosten/Unternehmerlohn)
| Stufe | Umfang | Betrag |
|---|---|---|
| S1 Text Restkatalog | 237 Werke / 26,7 Mio. W | 2.403 $ |
| S2 Hörbuch-Katalog DE (Gemini) | 187 Werke / 18,56 Mio. W = 2.000 h | 1.620 $ (2026) / 3.240 $ (2027) |
| S3 Hörbuch-Katalog EN (Chatterbox) | 2.000 h | 1.880 $ |
| S4 Monte Christo (M-03) | ~464k W EN | Text 42 $; Vollvertonung EN+DE 162 $ (2027) |
| S5 eigene GPU | ersetzt Modal 0,94 $/h | lohnt erst, wenn Kaufpreis < erwartete Audio-h × 0,94 $ (Katalog EN: 1.880 $) |
**Summe S1–S4 bei Start 2026: ≈ 6.100 $; bei DE-Vertonung erst 2027: ≈ 7.700 $.**
Kapazität: 1,08 Mio. Sätze je Sprache; Gemini-Limit 10.000 Anfragen/Tag -> mit 8-Satz-Paketen DE-Katalog in ~14 Tagen.

## 4 Entscheidungen / Empfehlungen CFO
1. **DE-Basisvertonung der freigegebenen Titel vor 31.12.2026** (Preisverdopplung) – spart 8,65 $ je Werk, 1.620 $ auf den Katalog. Hörprobe-Tor bleibt.
2. **Phase 1 bis Leipzig 03/2027: Eigenmittel.** Rahmen Direktkosten ≈ 6.100 $ + Fixkosten.
3. **Gründung = Voraussetzung für jeden Förderantrag (CK 17.10.).** Rechtsform UG (haftungsbeschränkt), Musterprotokoll, 1 Gesellschafter CK, Stammkapital 1.000 €.
   Einmalkosten 479,75 € (Notar 148,75 + Handelsregister 300 + Gewerbe ~31; Gemeinde Haßfurt prüfen); laufend Transparenzregister 19,80 €/Jahr + IHK + Jahresabschluss.
   Termin: Eintragung bis 31.01.2027 (vor Patenschafts-Verkauf und Leipzig). Vorher Nebentätigkeit bei Messe München anzeigen.
   Förderfristen bleiben gewahrt: Start?Zuschuss Gründung ≤ 2 Jahre, KfW StartGeld ≤ 5 Jahre.
4. **Start?Zuschuss! Bayern** als erste Fremdmittel: 50 % bis 36.000 € Zuschuss, Gründung ≤ 2 Jahre (Vorgründung zulässig), Sitz Bayern außer Stadt/Lkr. München (Haßfurt passt), max. 20 Firmen/Jahr, Antrag bis 30.06.2027. Antrag mit Leipzig-Kennzahlen (Q2 2027). Förderfähig: Personal, Miete, Markteinführung, F&E -> Projektbudget 72.000 € = 36.000 € Zuschuss.
5. **KfW ERP-Gründerkredit StartGeld** (Merkblatt 067, Stand 18.06.2026): bis 200.000 €, Betriebsmittel max. 80.000 €, kein Mindestbetrag,
   Laufzeit 5 J (1 tilgungsfrei) oder 10 J (2 tilgungsfrei), 80 % Haftungsfreistellung, Nebenerwerb gefördert, Antrag über Hausbank VOR Vorhabenbeginn,
   < 5 Jahre seit erstem Umsatz, keine Lebenshaltung. Realistische Höhe = belegter Bedarf im Businessplan:
   - Stufe A (Katalog + Leipzig): ~10.000 € -> 10 J: 349 €/J Zins, dann 121 €/Monat.
   - Stufe B (Eigenanteil Start?Zuschuss 72.000-€-Projekt): 36.000 € -> 10 J: 1.256 €/J Zins, dann 436 €/Monat (Zinskosten gesamt 8.393 € bei 3,49 %).
   Kapitaldienst trägt CKs Gehalt (Nebenerwerb). Kombination mit Start?Zuschuss vorab mit Hausbank und Regierung von Unterfranken klären.
6. **BayTOU** derzeit geschlossen -> beobachten (Software-Entwicklung bis 150.000 €).
7. **Angels/VC erst nach Meilensteinen (Abschnitt 6).**

## 5 Bewertung Anforderungen (> 100 €)
- M-03 Monte Christo: **freigegeben bis 300 $** (Text 42 $ + Vollvertonung EN+DE 162 $ + Overlay/Klangteppich). Hinweis: nicht in der Startliste (Übersetzung) -> PD-Prüfung Übersetzer vorab.
- V-03 Preislogik: Preis = Paketpreis (Wert), Kostenlog nur als Kontrolle. Direktkosten: P0 (8 h, 1 Sprache) ≈ 20 $ bei 490 €; P2 ≈ 2,5 $/h bei 59 €/h; P3 VC ≈ 0,94 $/h bei 35 €/h. Pakete aus VERTRIEB.md tragfähig.

## 6 Meilensteine für Investoren (Ziel bis Leipzig 03/2027)
- Warteliste ≥ 2.000 (M-05), davon Gründungspaten-Vormerkung ≥ 10 %.
- ≥ 100 bezahlte Patenschaften (≈ 6.000 € Umsatz) = Zahlungsbereitschaft belegt.
- ≥ 3 Verlagspiloten (P0 bezahlt oder Barter), 1 Referenzkunde zitierfähig.
- Unit Economics belegt: Direktkosten < 2,50 $/Audio-h, Rohmarge Verlagspakete > 90 %.
- Katalog: ≥ 50 Werke EN+DE Text+Audio live.

## 7 Befunde Ertragsmodell (Umbau = nächstes Arbeitspaket CFO)
- READ LAYER rechnet 49 €/Werk + 79 € Extra und 2 Werke je Kunde jeden Monat -> auf Pakete P0–P3 (einmalig je Titel) umstellen.
- TÆLLA rechnet Abo 2,99 € / 3 % -> Preisstruktur 5,99/7,99 €/Monat, 59,99/79,99 €/Jahr, Patenschaften 59,99/74,99 € fehlen.
- Fixkosten 40 €/Monat und Unternehmerlohn 0 € -> echte Werte einsetzen.
- Monat 0 ohne Kalenderdatum; TTS-Kosten/Titel 18 € passt für 2027 (17,30 $ je Sprache).
- Modell-Ergebnis aktuell (alte Annahmen): Break-even monatlich Monat 9, kumuliert Monat 11, Run-Rate M35 6.094 €.

## Offen an CK
1. Monatsfixkosten (Claude-Abo, Domains, Hosting, Modal über Freiguthaben, sonstige Abos).
2. Monat 0 im Modell = November 2026?
3. Eigenmittel-Budget bis Leipzig (Obergrenze).
ENTSCHIEDEN 17.10.: Firma „TAELLA UG (haftungsbeschränkt)“, Sitz Haßfurt; Gegenstand in TAELLA_UG_Unternehmensgegenstand.md. Postfach finanzen@taella.io einrichten.
