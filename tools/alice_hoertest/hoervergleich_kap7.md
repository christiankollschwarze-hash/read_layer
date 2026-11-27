# Hörvergleich Alice Kap. 7 (DE): bisher vs. Qwen-Besetzung

| | bisher | neu (Qwen) |
|---|---|---|
| Datei | `tools/fish_test/de/fish_erz_vc_c007_de.wav` | `tools/alice_hoertest/de/fish_erz_vc_qwen_c007_de.wav` |
| Erzähler (Fish Drama 3) | grossmutter_a (Gemini-Klon) | w_tief_02 |
| Alice (Chatterbox-VC) | w_kind_hoch_neugierig | w_hoch_02 |
| Hutmacher | m_mittel_mittel_albern | m_mittel_04 |
| Märzhase | m_mittel_hoch_albern | m_hoch_01 |
| Haselmaus | m_alt_tief_schlaefrig | m_tief_01 |
| Länge | 19:59 | 22:32 |

Gleicher Ablauf in beiden Fassungen: Fish spricht alles in der Erzählerstimme (Figuren mit Regie-Tag), Chatterbox-VC wandelt die
Figurenzeilen in die Zielstimme, Montage mit denselben Pausen. Unterschiede kommen also nur aus der Besetzung (und dem neuen Fish-Durchlauf).

| Stelle | Figur | bisher | neu | Figurentrennung | Aussprache | Prosodie | Artefakte |
|---|---|---|---|---|---|---|---|
| Kein Platz! (Einstieg) | Hutmacher | 0:37 | 0:41 | | | | |
| Rätsel Rabe/Schreibpult | Hutmacher | 2:07 | 2:18 | | | | |
| Wechselrede ich sehe / ich esse | Hutmacher/Märzhase | 2:55 | 3:11 | | | | |
| Streit mit der Zeit | Hutmacher | 7:04 | 7:39 | | | | |
| Haselmaus-Geschichte (Sirupbrunnen) | Haselmaus | 12:43 | 14:39 | | | | |
| Abgang Alice | Alice | 18:46 | 21:09 | | | | |

Kosten neue Fassung: Fish API 0,36 $ (269 Beiträge), VC A10G 0,06 $. Hörtest davor 0,21 $.
Besetzung: `tools/alice_hoertest/kapitel/besetzung.json`, Einzelteile `tools/alice_hoertest/de/kapitel/erz/`, VC `gpu_overlay/alice_c007_qwen_de/ergebnis.zip`.
