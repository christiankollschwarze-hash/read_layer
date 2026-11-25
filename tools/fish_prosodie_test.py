"""READ LAYER — Prosodie-Stresstest Fish Drama 3 auf Modal (25.11.2026, Wunsch CK: Modell an die Grenzen bringen).
Eigener Fantasietext (DE), Erzaehlerstimme spielt alle Figuren: Fluestern, Jauchzen, Stottern, Traurigkeit, Wut,
akkurate Aufzaehlung. Vier Varianten in EINEM Modal-Lauf (ein Kaltstart):
  1_ohne        Text ohne Anweisungen (Basis)
  2_anweisung   Anweisungen wie Stage 430 (Grundhaltung; Moment) + <whisper>/<emphasis>
  3_stark       dieselben Anweisungen mit Verstaerkern + mehr nonverbal ([laughs], [sighs], [gasps], [sobs])
  4_stark_t09   wie 3, temperature/top_p 0,9 statt 0,7 (mehr Spielraum)
Ausgabe tools/fish_prosodie_test/<lg>/<variante>.wav + hoertest.md. Kosten ~0,2 $ (H100, Kaltstart ~65 s).
Aufruf:  py -3.11 tools/fish_prosodie_test.py [--stimme grossmutter_a]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config  # noqa: E402
from pipeline import fish_motor as F  # noqa: E402
from pipeline import manifest  # noqa: E402
from pipeline import s503_vertonung_fish as V  # noqa: E402

AUS = os.path.join(config.BASE_DIR, "tools", "fish_prosodie_test")

# (Figur, Text, Anweisung normal, Anweisung stark) – Erzaehler ohne Anweisung
SZENE = [
    ("Erzaehler", "Es war die Nacht vor dem Mondfest, und im Turm von Kaltenbrunn brannte nur noch eine einzige Kerze.", None, None),
    ("Mira", "Pssst … hörst du das? <whisper>Da unten, hinter der Tür, flüstert jemand unsere Namen.</whisper>",
     "voicing Mira, a curious girl: whispering; tense", "voicing Mira, a curious girl: barely audible whisper; extremely tense, breathless"),
    ("Erzaehler", "Holm, der alte Wächter, trat einen Schritt zurück und hielt die Laterne mit zitternder Hand.", None, None),
    ("Holm", "I-i-ich … w-weiß nicht, ob wir … ob wir da wirklich hinuntergehen s-sollten.",
     "voicing Holm, an old guard: hesitant, slow; nervous", "voicing Holm, an old guard: very hesitant, stammering, slow; extremely nervous, voice trembling"),
    ("Erzaehler", "Doch als Mira die Tür aufstieß, fiel goldenes Licht in den Gang – der verlorene Mondstein lag mitten auf dem Tisch.", None, None),
    ("Mira", "Wir haben ihn! Wir haben ihn wirklich gefunden! Holm, schau doch, er leuchtet!",
     "voicing Mira, a curious girl: joyful, fast; excited", "[gasps] voicing Mira, a curious girl: jubilant, squealing with joy, fast; extremely excited [laughs]"),
    ("Erzaehler", "Hinter dem Tisch saß Witwe Alba. Sie hob den Kopf nur langsam.", None, None),
    ("Alba", "Drei Winter lang habe ich auf ihn gewartet. Er hat ihn mir geschenkt, am Abend, bevor er nicht mehr zurückkam.",
     "voicing Alba, an old widow: sad, slow; melancholic", "[sighs] voicing Alba, an old widow: deeply sad, voice breaking, very slow; grieving [sobs]"),
    ("Erzaehler", "Da krachte die Tür gegen die Wand. König Brand stand im Rahmen, das Gesicht rot vor Zorn.", None, None),
    ("Brand", "Wer hat es gewagt, meinen Turm zu betreten? <emphasis>Niemand</emphasis> rührt diesen Stein an – NIEMAND!",
     "voicing King Brand: angry, loud; furious", "voicing King Brand: shouting, roaring with rage, loud; extremely furious"),
    ("Erzaehler", "Nur die Schreiberin Oda blieb ruhig. Sie schlug ihr Buch auf und las vor.", None, None),
    ("Oda", "Eintrag vierhundertzwölf. Mondstein, Gewicht: dreiundzwanzig Gramm. Fundort: Nordturm, drittes Geschoss. Besitzerin: Alba von Kaltenbrunn. Gezeichnet am siebten Tag des Frostmonds.",
     "voicing Oda, a scribe: precise, crisp articulation, measured; calm", "voicing Oda, a scribe: extremely precise, crisp and clipped articulation, measured pace; perfectly calm and matter-of-fact"),
    ("Erzaehler", "Und für einen Augenblick war es so still, dass man die Kerze knistern hörte.", None, None),
]


def text(variante):
    teile = []
    for fig, t, normal, stark in SZENE:
        if fig == "Erzaehler" or variante == "1_ohne":
            teile.append(t.replace("<whisper>", "").replace("</whisper>", "").replace("<emphasis>", "")
                         .replace("</emphasis>", "") if variante == "1_ohne" else t)
            continue
        a = normal if variante == "2_anweisung" else stark
        vor, nach = "", ""
        while a.startswith("["):                               # nonverbale Marken vorn/hinten aus der Anweisung loesen
            k = a.index("]") + 1
            vor, a = vor + a[:k] + " ", a[k:].strip()
        while a.endswith("]"):
            k = a.rindex("[")
            nach, a = " " + a[k:] + nach, a[:k].strip()
        teile.append(f"{vor}[{a}] {t}{nach}")
    return " ".join(teile)


VARIANTEN = {"1_ohne": {}, "2_anweisung": {}, "3_stark": {}, "4_stark_t09": {"temperature": 0.9, "top_p": 0.9}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stimme", default="grossmutter_a")
    ap.add_argument("--lang", default="de")
    a = ap.parse_args(argv)
    lg = a.lang
    d = os.path.join(AUS, lg)
    os.makedirs(d, exist_ok=True)
    for alt in os.listdir(d):                      # alte Takes weg (sonst stehen sie bei Fehlern im Hoertest)
        if alt.endswith(".wav"):
            os.remove(os.path.join(d, alt))
    paket = f"prosodie_test_{lg}"
    pd = os.path.join(config.BASE_DIR, "gpu_fish", paket)
    shutil.rmtree(pd, ignore_errors=True)
    os.makedirs(os.path.join(pd, "ref"))
    shutil.copy2(F.klon_clip(a.stimme, lg), os.path.join(pd, "ref", "ref.wav"))
    jobs = []
    for v, extra in VARIANTEN.items():
        t = text(v)
        j = V._modal_jobs({"text": t, "soll": "pt_" + manifest.hash_obj({"t": t, "v": v, "st": a.stimme}),
                           "ids": [v]}, 0)
        j.update(extra, variante=v)
        jobs.append(j)
    manifest.json_atomar(os.path.join(pd, "jobs.json"), {"werk": "prosodie_test", "lang": lg, "stimme": a.stimme,
                         "ref": {"datei": "ref.wav", "text": F.klon_text(lg)}, "jobs": jobs}, indent=1)
    print(f"[prosodie] {len(jobs)} Varianten, {sum(len(j['text']) for j in jobs)} Zeichen -> Modal", flush=True)
    r = subprocess.run([sys.executable, "-m", "modal", "run", "gpu_fish/fish_modal.py", "--paket", paket],
                       cwd=config.BASE_DIR)
    zeilen = [f"# Prosodie-Stresstest Fish Drama 3 (Modal) – {lg}", "",
              "Szene: Erzaehlerin + Mira (Fluestern, Jauchzen), Holm (Stottern/Unsicherheit), Alba (Trauer), "
              "Brand (Wut), Oda (akkurate Aufzaehlung).", "",
              "| Variante | Datei | Dauer s | Fokus |", "|---|---|---|---|"]
    fokus = {"1_ohne": "Basis ohne Anweisungen", "2_anweisung": "Anweisungen wie Stage 430",
             "3_stark": "Verstaerker + nonverbal", "4_stark_t09": "wie 3, temperature/top_p 0,9"}
    for j in jobs:
        q = os.path.join(pd, "out", j["key"] + ".wav")
        if os.path.exists(q):
            shutil.copy2(q, os.path.join(d, j["variante"] + ".wav"))
            with open(os.path.join(pd, "out", j["key"] + ".json"), encoding="utf-8") as f:
                sek = json.load(f)["info"].get("sek")
            zeilen.append(f"| {j['variante']} | {j['variante']}.wav | {sek} | {fokus[j['variante']]} |")
        else:
            zeilen.append(f"| {j['variante']} | fehlt | – | {fokus[j['variante']]} |")
    if os.path.exists(os.path.join(pd, "bericht.txt")):
        shutil.copy2(os.path.join(pd, "bericht.txt"), os.path.join(d, "modal_bericht.txt"))
    zeilen += ["", "## Texte"] + [f"### {j['variante']}\n{j['text']}\n" for j in jobs]
    zeilen += ["## Hoerurteil CK (je Figur: traegt / schwach / kippt)", "- Mira fluestern:", "- Mira jauchzen:",
               "- Holm stottern:", "- Alba Trauer:", "- Brand Wut:", "- Oda akkurat:", "- Beste Variante:"]
    with open(os.path.join(d, "hoertest.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen) + "\n")
    print("\n".join(zeilen[:10]), flush=True)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
