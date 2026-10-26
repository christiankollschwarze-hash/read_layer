"""AP 58 - Casting Winnie-the-Pooh mit Gemini-Standardstimmen (EN + DE gleiche Stimme je Figur).
Schreibt work/casting.json (Tor "offen"). Figurenrede spaeter direkt mit Gemini (tools/overlay_gemini.py, plan.overlay_gemini),
keine Chatterbox-VC. Erzaehler = A. A. M. (Ich-Erzaehler der Rahmenhandlung, spricht mit Christopher Robin).
Hoerproben der Stimmen: stimmen_archiv/_gemini_standard/<Name>/muster_<lg>.wav
Aufruf: python tools/pooh_casting.py [--force]
"""
import os, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
BOOK = "winnie-the-pooh"

ERZ = ("Algieba", "warmer, ruhiger Vater-Erzaehler (A. A. M.), schmunzelnd, nie theatralisch")
# figur EN, name DE, Gemini-Stimme, Geschlecht, Kurzbeschreibung
FIGUREN = [
 ("Pooh", "Pu", "Umbriel", "m", "gemuetlicher kleiner Baer, langsam, gutmuetig, summt gern, wenig Verstand, viel Herz"),
 ("Piglet", "Ferkel", "Leda", "m", "sehr kleines Ferkel, hoch, schnell, aengstlich, tapfer wider Willen"),
 ("Eeyore", "I-Ah", "Algenib", "m", "alter grauer Esel, tief, rau, langsam, truebsinnig, trocken-sarkastisch"),
 ("Owl", "Eule", "Rasalgethi", "m", "Eule, wichtigtuerisch, belehrend, umstaendlich, aelter"),
 ("Kanga", "Känga", "Sulafat", "w", "Kaengurumutter, warm, ruhig, bestimmt, muetterlich"),
 ("Roo", "Ruh", "Laomedeia", "m", "Baby-Kaenguru, hell, quietschig, uebermuetig"),
 ("Rabbit", "Kaninchen", "Fenrir", "m", "Kaninchen, geschaeftig, schnell, rechthaberisch, organisiert alles"),
 ("Christopher Robin", "Christopher Robin", "Puck", "m", "Junge, ca. sechs, froehlich, klar, selbstbewusst-kindlich"),
]


def main():
    p = os.path.join(config.work_dir(BOOK), "casting.json")
    if os.path.exists(p) and "--force" not in sys.argv:
        print(f"[casting] {p} existiert (--force zum Ueberschreiben)"); return
    ens = [{"quelle": "gemini_standard_ap58", "stimme": v, "id": v, "figur": en, "name_de": de,
            "gewicht": "haupt" if en in ("Pooh", "Piglet", "Christopher Robin") else "neben", "kurz": k}
           for en, de, v, g, k in FIGUREN]
    c = {
        "werk": BOOK, "datum": datetime.date.today().isoformat(), "quelle": "tools/pooh_casting.py (AP 58)", "tor": "offen",
        "steckbriefe": {
            "erzaehler": {"erzaehlform": "ich_rahmen", "ich_figur": "", "genre_stimme": "kinderbuch", "kurz": ERZ[1]},
            "figuren": [{"name": en, "name_de": de, "gewicht": e["gewicht"], "merkmale": {"geschlecht": g}, "kurz": k}
                        for (en, de, v, g, k), e in zip(FIGUREN, ens)]},
        "plan": {
            "erzaehler": {"quelle": "gemini_standard_ap58", "stimme": ERZ[0], "id": ERZ[0], "figur": "Erzaehler", "kurz": ERZ[1]},
            "ensemble": ens,
            "statisten": [],
            "vertonung": {"de": "gemini", "en": "gemini"},
            "gemini_stimmen": {"Erzaehler": ERZ[0], **{en: v for en, de, v, g, k in FIGUREN}},
            "overlay_gemini": {en: v for en, de, v, g, k in FIGUREN},
            "gemini_hinweis": "AP 58 (26.10.2026): Erzaehler + alle Figuren Gemini-Standardstimmen, EN und DE gleich; "
                              "Figurenrede direkt mit Gemini (overlay_gemini), Lieder (vs) singt die Figur (meist Pu).",
        },
    }
    json.dump(c, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[casting] Erzaehler {ERZ[0]}; " + ", ".join(f"{de}={v}" for en, de, v, g, k in FIGUREN))
    print("[casting] Tor offen -> Hoerprobe anhoeren, dann Freigabe")


if __name__ == "__main__":
    main()
