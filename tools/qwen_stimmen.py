"""READ LAYER — Stimmen-Matrix mit Qwen3-TTS VoiceDesign (AP Qwen-Stimmdesign 26.11.2026, PROMPT_qwen_stimmdesign.md).

  py -3.11 tools/qwen_stimmen.py matrix                       Matrix schreiben -> tools/qwen_stimmen/matrix.json
  py -3.11 tools/qwen_stimmen.py kandidaten [--nur ID,..] [--seeds 11,22,33] [--paket NAME]
        je Stimme x Seed ein DE-Referenz-Clip (Nordwind-Auszug, ~25 s: Aussage, Frage, Ausruf) per VoiceDesign,
        Kinder zusaetzlich aus heller Frauenstimme abgeleitet, ECAPA je Clip -> gpu_qwen/<paket>/out
  py -3.11 tools/qwen_stimmen.py katalog [--paket NAME]       Hoerkatalog -> tools/qwen_stimmen/hoerkatalog.html
        (Filter Geschlecht/Alter/Charakter/Erzaehler, Seed waehlen, auswahl.json exportieren)
  py -3.11 tools/qwen_stimmen.py referenzen auswahl.json [--sprachen en,zh] [--paket NAME]
        gewaehlte Seeds: Referenz-Clip je weiterer Sprache per Qwen3 Base-Klon aus dem DE-Clip (gleiche Person)
  py -3.11 tools/qwen_stimmen.py uebernehmen auswahl.json [--paket NAME]
        gewaehlte Seeds -> stimmen_archiv/<id>/ (klon_de.wav, klon_en.wav, steckbrief.json) + stimmen.json
  py -3.11 tools/qwen_stimmen.py xl ID SEED [--paket NAME]    Cross-lingual-Probe: DE-Clip -> EN + ZH per Base-Klon
Kosten: je Modal-Lauf Zeile in tools/qwen_stimmen/kosten_log.jsonl (WALL x Modal-Listenpreis der GPU aus config).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

LESER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LESER)
from config import config  # noqa: E402
from pipeline import voice_registry as VR  # noqa: E402

AUS = os.path.join(LESER, "tools", "qwen_stimmen")
GPU_DIR = os.path.join(LESER, "gpu_qwen")
STANDARD_PAKET = "matrix_v1"
SEEDS = [11, 22, 33]
SPRACHEN = {"de": "German", "en": "English"}
ANKER = "de"            # Designstimme entsteht nur in dieser Sprache; andere Sprachen per Base-Klon aus dem Anker-Clip
                        # (Probe 26.11.: je Sprache getrennt designt -> ECAPA DE<->EN 0,27 = andere Person; Klon 0,64)
SPRACHNAME = {"de": "German", "en": "English", "zh": "Chinese"}
ZH_TEXT = "北风和太阳争论谁更有力量。谁会想到温和的太阳能赢得这样的比赛呢？最后，这是多么温暖美好的一天！"
WERKZEUG = "Qwen3-TTS VoiceDesign 1.7B (Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign)"
HERKUNFT = "Qwen3-TTS VoiceDesign, Apache-2.0, keine reale Person"

# ============================================================ Matrix
ALTER = {  # id: (DE, EN-Phrase m, EN-Phrase w, Register-Alter)
    "jung": ("jung (18-25)", "a young man of about twenty", "a young woman of about twenty", "jung"),
    "jungerw": ("jung-erwachsen (25-35)", "a man of about thirty", "a woman of about thirty", "jung"),
    "mittel": ("mittel (35-50)", "a man in his early forties", "a woman in her early forties", "mittel"),
    "reif": ("reif (50-65)", "a man in his late fifties", "a woman in her late fifties", "alt"),
    "alt": ("alt (65+)", "an old man in his mid-seventies", "an old woman in her mid-seventies", "greis"),
}
TON = {  # Tonlage je Alter (Spreizung im Ensemble), m / w
    "jung": ("medium-high pitch", "bright, medium-high pitch"), "jungerw": ("medium pitch", "medium pitch"),
    "mittel": ("medium-low pitch", "medium-low pitch"), "reif": ("low pitch", "low, mature pitch"),
    "alt": ("low pitch, thinned by age", "medium pitch, thinned and slightly wavering with age"),
}
CHARAKTER = {  # id: (DE, EN m, EN w, Klangfarben, Temperamente, Tempo)
    "warm": ("warm / väterlich-mütterlich", "warm, fatherly and reassuring, a gentle smile in the voice",
             "warm, motherly and reassuring, a gentle smile in the voice", ["warm", "samtig"], ["guetig", "ruhig"], "mittel"),
    "kuehl": ("kühl / autoritär", "cool, authoritative, precise and controlled, little visible emotion",
              "cool, authoritative, precise and controlled, little visible emotion", ["kuehl", "klar"], ["streng"], "mittel"),
    "verschmitzt": ("verschmitzt / ironisch", "mischievous and ironic, a playful undertone as if holding back a joke",
                    "mischievous and ironic, a playful undertone as if holding back a joke", ["hell"], ["verschmitzt"], "mittel"),
    "nervoes": ("nervös / gehetzt", "nervous and hurried, slightly breathless, speaking quickly",
                "nervous and hurried, slightly breathless, speaking quickly", ["duenn"], ["nervoes", "aengstlich"], "schnell"),
    "rau": ("rau / brüchig", "rough and gravelly, slightly cracked and worn", "rough and husky, slightly cracked and worn",
            ["rau", "bruechig"], ["ruhig"], "mittel"),
    "weich": ("weich / verträumt", "soft and dreamy, gentle and airy, unhurried",
              "soft and dreamy, gentle and airy, unhurried", ["samtig", "hell"], ["ruhig", "melancholisch"], "langsam"),
}
# Eigenheit je Geschlecht x Charakter x Alter (Reihenfolge wie ALTER): (DE, EN)
EIGEN = {
    "m": {
        "warm": [("lacht leise mit", "a soft chuckle never far from his words"),
                 ("ruhiges Tempo, runde Vokale", "a calm pace with round, full vowels"),
                 ("tiefe Brustresonanz", "rich chest resonance"),
                 ("leicht nordische Färbung, gemütlich", "a slight, comfortable northern colouring"),
                 ("bedächtig, kleine Atempausen", "deliberate, with small breathing pauses")],
        "kuehl": [("knapp, abgehackte Sätze", "clipped, short phrasing"),
                  ("sehr deutliche Konsonanten", "very crisp consonants"),
                  ("gleichmäßiger, fast monotoner Fluss", "an even, almost monotonous flow"),
                  ("trocken, leicht nasal", "dry and slightly nasal"),
                  ("langsam, schneidend", "slow and cutting")],
        "verschmitzt": [("Grinsen hörbar, schnelles Tempo", "an audible grin and quick tempo"),
                        ("hebt am Satzende spielerisch an", "playfully lifts at the end of phrases"),
                        ("leicht heiser, Lachen im Ton", "slightly husky, laughter in the tone"),
                        ("gedehnte Pointen", "drawn-out punchlines"),
                        ("kichert gelegentlich", "an occasional giggle")],
        "nervoes": [("stolpert gelegentlich über Wörter", "occasionally tripping over words"),
                    ("hohe Spannung, flache Atmung", "high tension, shallow breathing"),
                    ("räuspert sich", "a habit of clearing his throat"),
                    ("Stimme bricht leicht nach oben", "voice cracking slightly upwards"),
                    ("zittrig, hastig", "shaky and hasty")],
        "rau": [("rauchig, leicht heiser", "smoky and slightly hoarse"),
                ("kehlig, etwas Straßenton", "throaty, a little street-wise"),
                ("verrauchte Tiefe", "a smoky depth"),
                ("Seemannsstimme, kräftig", "a strong, weathered sailor's voice"),
                ("brüchig, mit Luft in der Stimme", "brittle, with breath in the voice")],
        "weich": [("leises Sprechen, fast flüsternd", "speaking softly, almost whispering"),
                  ("melodisch, singende Satzbögen", "melodic, sing-song phrasing"),
                  ("samtig, langsam", "velvety and slow"),
                  ("nachdenklich, Pausen vor wichtigen Wörtern", "thoughtful, pausing before important words"),
                  ("sanft, etwas verträumt abwesend", "gentle and a little absent-minded")],
    },
    "w": {
        "warm": [("hell und herzlich, lacht leicht", "bright and hearty, laughing lightly"),
                 ("klar, freundlich, mittleres Tempo", "clear and friendly, moderate pace"),
                 ("volle, runde Altstimme", "a full, round alto"),
                 ("leicht süddeutsche Färbung, gemütlich", "a slight, cosy southern colouring"),
                 ("großmütterlich, bedächtig", "grandmotherly and deliberate")],
        "kuehl": [("knapp und präzise", "brief and precise"),
                  ("sehr klare Artikulation", "very clear articulation"),
                  ("tief, kontrolliert, wenig Melodie", "low, controlled, little melody"),
                  ("trocken, distanziert", "dry and distant"),
                  ("streng, langsam, jedes Wort gesetzt", "stern and slow, every word placed")],
        "verschmitzt": [("kichernd, schnell", "giggly and quick"),
                        ("augenzwinkernd, singt die Satzenden", "with a wink, sing-song phrase endings"),
                        ("rauchig-ironisch", "smoky and ironic"),
                        ("trockener Humor, gedehnte Vokale", "dry humour with drawn-out vowels"),
                        ("spitzbübisch, leises Lachen", "impish, with a quiet laugh")],
        "nervoes": [("schnell, atemlos", "fast and breathless"),
                    ("hohe Spannung, abgebrochene Sätze", "high tension, broken-off phrases"),
                    ("hüstelt, zögert", "a nervous little cough, hesitating"),
                    ("leicht schrill bei Aufregung", "slightly shrill when agitated"),
                    ("zittrig, flüsternd-hastig", "shaky, hasty half-whisper")],
        "rau": [("heiser, leicht rauchig", "hoarse and slightly smoky"),
                ("kehlig, tief für ihr Alter", "throaty, low for her age"),
                ("verrauchte Barstimme", "a smoky late-night voice"),
                ("rau und kräftig, Marktfrau", "rough and strong, like a market trader"),
                ("brüchig, zittrig", "brittle and tremulous")],
        "weich": [("hauchig, sehr sanft", "breathy and very gentle"),
                  ("melodisch, träumerisch", "melodic and dreamy"),
                  ("samtig, ruhig, warm timbriert", "velvety and calm, warm timbre"),
                  ("leise, nachdenklich", "quiet and reflective"),
                  ("sanft, märchenhaft erzählend", "gentle, like telling a fairy tale")],
    },
}
KINDER = [  # id, DE, EN-Instruct, Geschlecht, Tonlage, Temperamente
    ("k_j_klein_neugierig", "Junge 5-8, neugierig", "a little boy of about six, curious and excited, high bright voice", "m", "hoch", ["neugierig"]),
    ("k_j_klein_frech", "Junge 5-8, frech", "a cheeky little boy of about seven, quick and playful, high voice", "m", "hoch", ["verschmitzt", "albern"]),
    ("k_j_gross_ernst", "Junge 9-13, ernst", "a serious boy of about eleven, thoughtful, clear unbroken voice", "m", "hoch", ["ruhig"]),
    ("k_j_gross_aufgeweckt", "Junge 9-13, aufgeweckt", "a lively boy of about ten, energetic and cheerful", "m", "hoch", ["froehlich"]),
    ("k_j_gross_schuechtern", "Junge 9-13, schüchtern", "a shy boy of about twelve, quiet and hesitant, voice not yet broken", "m", "mittel", ["aengstlich"]),
    ("k_m_klein_froehlich", "Mädchen 5-8, fröhlich", "a happy little girl of about six, bright and bubbly, high voice", "w", "hoch", ["froehlich"]),
    ("k_m_klein_vertraeumt", "Mädchen 5-8, verträumt", "a dreamy little girl of about seven, soft and wondering", "w", "hoch", ["neugierig", "ruhig"]),
    ("k_m_gross_klug", "Mädchen 9-13, klug", "a clever girl of about eleven, articulate and confident", "w", "hoch", ["neugierig"]),
    ("k_m_gross_frech", "Mädchen 9-13, frech", "a sassy girl of about twelve, quick-witted and teasing", "w", "hoch", ["verschmitzt"]),
    ("k_m_gross_aengstlich", "Mädchen 9-13, ängstlich", "a timid girl of about ten, anxious and soft-spoken", "w", "hoch", ["aengstlich"]),
]
ABGELEITET = [  # Kinder aus heller Frauenstimme (Tonhoehe + Formanten), Vergleich zu direkter Beschreibung
    ("k_m_klein_abgeleitet", "w_jung_weich", 5.0, "Mädchen 5-8, abgeleitet aus w_jung_weich (+5 HT)", "w"),
    ("k_j_gross_abgeleitet", "w_jung_verschmitzt", 3.0, "Junge 9-13, abgeleitet aus w_jung_verschmitzt (+3 HT)", "m"),
]
STUDIO = ("Natural audiobook voice, believable, never cartoonish. Clean dry studio recording, close microphone, "
          "no reverb, no background noise, no music. An original voice, not imitating any real or famous person.")
ERZAEHLER = {("warm", "jungerw"), ("warm", "mittel"), ("warm", "reif"), ("kuehl", "mittel"), ("kuehl", "reif"),
             ("weich", "jungerw"), ("weich", "mittel"), ("weich", "reif"), ("warm", "alt")}


def matrix():
    st = []
    for g in ("m", "w"):
        for ai, (a, (a_de, a_m, a_w, a_reg)) in enumerate(ALTER.items()):
            for c, (c_de, c_m, c_w, klang, temp, tempo) in CHARAKTER.items():
                e_de, e_en = EIGEN[g][c][ai]
                erz = (c, a) in ERZAEHLER
                instruct = (f"{(a_m if g == 'm' else a_w).capitalize()}, {TON[a][0 if g == 'm' else 1]}. "
                            f"{(c_m if g == 'm' else c_w).capitalize()}; {e_en}. "
                            + ("Steady and pleasant enough to narrate long passages. " if erz else "") + STUDIO)
                st.append({"id": f"{g}_{a}_{c}", "geschlecht": g, "alter": a, "charakter": c,
                           "beschreibung_de": f"{'Mann' if g == 'm' else 'Frau'}, {a_de}, {c_de}; {e_de}",
                           "instruct": instruct, "erzaehler": erz,
                           "merkmale": {"geschlecht": g, "alter": a_reg, "tonlage": _tonlage(g, a),
                                        "klangfarbe": klang, "tempo": tempo, "temperament": temp,
                                        "sicherheit": "fest" if c in ("kuehl", "warm") else "neutral", "akzent": ""}})
    for kid, de, en, g, ton, temp in KINDER:
        st.append({"id": kid, "geschlecht": g, "alter": "kind", "charakter": kid.split("_")[-1],
                   "beschreibung_de": f"Kind: {de}", "erzaehler": False,
                   "instruct": f"The voice of {en}. A real child's voice, not an adult imitating a child. " + STUDIO,
                   "merkmale": {"geschlecht": g, "alter": "kind", "tonlage": ton, "klangfarbe": ["hell"], "tempo": "mittel",
                                "temperament": temp, "sicherheit": "neutral", "akzent": ""}})
    for kid, quelle, ht, de, g in ABGELEITET:
        st.append({"id": kid, "geschlecht": g, "alter": "kind", "charakter": "abgeleitet", "beschreibung_de": f"Kind: {de}",
                   "erzaehler": False, "abgeleitet": {"quelle": quelle, "halbtoene": ht}, "instruct": "",
                   "merkmale": {"geschlecht": g, "alter": "kind", "tonlage": "hoch", "klangfarbe": ["hell"],
                                "tempo": "mittel", "temperament": [], "sicherheit": "neutral", "akzent": ""}})
    os.makedirs(AUS, exist_ok=True)
    with open(os.path.join(AUS, "matrix.json"), "w", encoding="utf-8") as f:
        json.dump({"stand": str(datetime.date.today()), "stimmen": st}, f, ensure_ascii=False, indent=1)
    print(f"[matrix] {len(st)} Stimmen -> tools/qwen_stimmen/matrix.json "
          f"({sum(s['erzaehler'] for s in st)} Erzaehler, {sum(s['alter'] == 'kind' for s in st)} Kinder)")
    return st


def _tonlage(g, a):
    return {"jung": "hoch" if g == "w" else "mittel", "jungerw": "mittel", "mittel": "mittel",
            "reif": "tief", "alt": "tief" if g == "m" else "mittel"}[a]


def _matrix_laden():
    p = os.path.join(AUS, "matrix.json")
    return json.load(open(p, encoding="utf-8"))["stimmen"] if os.path.exists(p) else matrix()


def ref_text(lg):
    """Nordwind-Auszug (~20 s): Titel, langer Satz, Aussage, Frage, Ausruf."""
    if lg == "zh":
        return ZH_TEXT
    s = json.load(open(os.path.join(LESER, "stimmen_archiv", "_texte", "nordwind.json"), encoding="utf-8"))[lg]
    return " ".join(s[i] for i in (0, 1, 5, 6, 7))


def key(sid, seed, lg):
    return f"{sid}__s{seed}_{lg}"


# ============================================================ Modal
def _modal(paket, jobs, art):
    d = os.path.join(GPU_DIR, paket)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=1)
    t0 = time.time()
    r = subprocess.run(["py", "-3.11", "-m", "modal", "run", "gpu_qwen/qwen_modal.py", "--paket", paket], cwd=LESER)
    wall = time.time() - t0
    ber = open(os.path.join(d, "bericht.txt"), encoding="utf-8").read() if os.path.exists(os.path.join(d, "bericht.txt")) else ""
    m = re.search(r"^WALL ([\d.]+)", ber, re.M)
    gpu_wall = float(m.group(1)) if m else 0.0       # kein Bericht = Lauf vor GPU-Start abgebrochen (Image-Bau)
    g = re.search(r"^GPU (?:NVIDIA )?(\w+)", ber, re.M)
    gpu = (g.group(1) if g else "L40S").upper()
    gpu = {"A10": "A10G"}.get(gpu, gpu)
    preis = float(getattr(config, f"MODAL_{gpu}_USD_H", 1.95))
    m_ecapa = re.search(r"^ECAPA .*?([\d.]+) s", ber, re.M)
    usd = gpu_wall / 3600 * preis + (float(m_ecapa.group(1)) / 3600 * 0.2 if m_ecapa else 0)
    zeile = {"zeit": time.strftime("%Y-%m-%d %H:%M:%S"), "art": art, "paket": paket, "gpu": gpu,
             "gpu_wall_s": round(gpu_wall, 1), "lokal_wall_s": round(wall, 1), "usd_h": preis, "usd": round(usd, 4),
             "clips": sum(len(jobs.get(k, [])) for k in ("design", "klon", "ableiten")), "rc": r.returncode}
    with open(os.path.join(AUS, "kosten_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(zeile) + "\n")
    print(f"[qwen] Kosten ~{usd:.3f} $ ({gpu}, {gpu_wall:.0f} s GPU-Wall) -> tools/qwen_stimmen/kosten_log.jsonl")
    return r.returncode


def kandidaten(nur, seeds, paket):
    st = _matrix_laden()
    if nur:
        st = [s for s in st if s["id"] in nur]
    jobs = {"design": [], "ableiten": [], "embed": True}
    lg, lang = ANKER, SPRACHNAME[ANKER]
    for s in st:
        for seed in seeds:
            if s.get("abgeleitet"):
                jobs["ableiten"].append({"key": key(s["id"], seed, lg), "halbtoene": s["abgeleitet"]["halbtoene"],
                                         "ref": key(s["abgeleitet"]["quelle"], seed, lg)})
            else:
                jobs["design"].append({"key": key(s["id"], seed, lg), "instruct": s["instruct"],
                                       "text": ref_text(lg), "language": lang, "seed": seed})
    quellen = {j["ref"] for j in jobs["ableiten"]}
    fehlt = quellen - {j["key"] for j in jobs["design"]}
    if fehlt:   # Quelle (helle Frauenstimme) mit erzeugen, falls nicht in --nur
        q = {s["id"]: s for s in _matrix_laden()}
        for k in sorted(fehlt):
            sid, rest = k.split("__s")
            seed, lg = rest.split("_")
            jobs["design"].append({"key": k, "instruct": q[sid]["instruct"], "text": ref_text(lg),
                                   "language": SPRACHNAME[lg], "seed": int(seed)})
    print(f"[qwen] {len(st)} Stimmen x {len(seeds)} Seeds ({ANKER}) = "
          f"{len(jobs['design'])} Design + {len(jobs['ableiten'])} abgeleitet")
    return _modal(paket, jobs, "kandidaten")


def referenzen(auswahl_pfad, sprachen, paket):
    """gewaehlte Seeds: Referenz-Clip je weiterer Sprache per Base-Klon aus dem Anker-Clip (gleiche Person)."""
    auswahl = json.load(open(auswahl_pfad, encoding="utf-8"))
    st = {s["id"]: s for s in _matrix_laden()}
    jobs = {"klon": [], "ableiten": [], "embed": True}
    quellen = set()
    for sid, seed in auswahl.items():
        s, seed = st.get(sid), int(seed)
        if not s:
            continue
        for lg in sprachen:
            if s.get("abgeleitet"):          # Kind aus Frauenstimme: Quelle in lg klonen, dann verschieben
                q = s["abgeleitet"]["quelle"]
                quellen.add((q, seed, lg))
                jobs["ableiten"].append({"key": key(sid, seed, lg), "halbtoene": s["abgeleitet"]["halbtoene"],
                                         "ref": key(q, seed, lg)})
            else:
                quellen.discard((sid, seed, lg))
                jobs["klon"].append(_klon_job(sid, seed, lg))
    for q, seed, lg in quellen:
        if not any(j["key"] == key(q, seed, lg) for j in jobs["klon"]):
            jobs["klon"].append(_klon_job(q, seed, lg))
    print(f"[qwen] Referenzen {','.join(sprachen)}: {len(jobs['klon'])} Klon + {len(jobs['ableiten'])} abgeleitet")
    return _modal(paket, jobs, "referenzen")


def _klon_job(sid, seed, lg):
    return {"key": key(sid, seed, lg), "ref": key(sid, seed, ANKER), "ref_text": ref_text(ANKER),
            "text": ref_text(lg), "language": SPRACHNAME[lg], "seed": seed}


def xl(sid, seed, paket):
    """Cross-lingual-Probe: DE-Designclip -> EN + ZH per Base-Klon (Akzent bewerten; ZH: Fangyoung)."""
    zh = "北风和太阳争论谁更有力量。谁会想到温和的太阳能赢得这样的比赛呢？最后，这是多么温暖美好的一天！"
    jobs = {"klon": [{"key": f"{sid}__s{seed}_xl_{lg}", "ref": key(sid, seed, "de"), "ref_text": ref_text("de"),
                      "text": t, "language": lang, "seed": seed}
                     for lg, lang, t in (("en", "English", ref_text("en")), ("zh", "Chinese", zh))],
            "embed": True}
    jobs["klon"].append({"key": f"{sid}__s{seed}_xl_de", "ref": key(sid, seed, "de"), "ref_text": ref_text("de"),
                         "text": ref_text("de"), "language": "German", "seed": seed})   # Kontrolle: Klon in Ausgangssprache
    return _modal(paket, jobs, "xl")


# ============================================================ Auswertung + Hoerkatalog
def _emb(out, k):
    p = os.path.join(out, f"{k}.emb.json")
    return json.load(open(p)) if os.path.exists(p) else None


def _cos(a, b):
    import numpy as np
    a, b = np.array(a), np.array(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def auswerten(paket):
    """je Stimme x Seed: Dauer, Grundton DE/EN, ECAPA DE<->EN (gleiche Stimme?), naechste andere Stimme (Abstand)."""
    import wave
    out = os.path.join(GPU_DIR, paket, "out")
    st = _matrix_laden()
    werte, embs = {}, {}
    for s in st:
        for seed in SEEDS:
            w = {}
            for lg in SPRACHEN:
                p = os.path.join(out, key(s["id"], seed, lg) + ".wav")
                if not os.path.exists(p):
                    continue
                with wave.open(p) as f:
                    w[f"dauer_{lg}"] = round(f.getnframes() / f.getframerate(), 1)
                w[f"f0_{lg}"] = round(VR.grundton(p), 1)
                e = _emb(out, key(s["id"], seed, lg))
                if e:
                    embs[(s["id"], seed, lg)] = e
            if w:
                werte[(s["id"], seed)] = w
    for (sid, seed), w in werte.items():
        if (sid, seed, "de") in embs and (sid, seed, "en") in embs:
            w["de_en"] = round(_cos(embs[(sid, seed, "de")], embs[(sid, seed, "en")]), 3)
        if (sid, seed, "de") in embs:
            nah = max(((round(_cos(embs[(sid, seed, "de")], e), 3), o) for (o, os_, lg), e in embs.items()
                       if lg == "de" and o != sid), default=None)
            if nah:
                w["naechste"], w["naechste_cos"] = nah[1], nah[0]
    return st, werte


def katalog(paket):
    st, werte = auswerten(paket)
    rel = os.path.relpath(os.path.join(GPU_DIR, paket, "out"), AUS).replace("\\", "/")
    daten = []
    for s in st:
        seeds = []
        for seed in SEEDS:
            w = werte.get((s["id"], seed))
            if w:
                seeds.append({"seed": seed, **w, **{lg: f"{rel}/{key(s['id'], seed, lg)}.wav" for lg in SPRACHEN
                                                    if f"dauer_{lg}" in w}})
        daten.append({k: s[k] for k in ("id", "geschlecht", "alter", "charakter", "beschreibung_de", "erzaehler")}
                     | {"instruct": s.get("instruct", ""), "seeds": seeds})
    html = KATALOG_HTML.replace("/*DATEN*/[]", json.dumps(daten, ensure_ascii=False)).replace("{PAKET}", paket)
    p = os.path.join(AUS, "hoerkatalog.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[katalog] {sum(bool(d['seeds']) for d in daten)}/{len(daten)} Stimmen mit Clips -> {p}")


# ============================================================ Uebernahme ins Archiv
LAGEN = {"m": (95, 125), "w": (190, 240)}   # Hz-Grenzen tief|mittel|hoch (CK 26.11.); Kinder ohne Lage (k_01 ...)


def lage(g, f0):
    if g == "k":
        return ""
    lo, hi = LAGEN[g]
    return "tief" if f0 < lo else "mittel" if f0 <= hi else "hoch"


def uebernehmen(auswahl_pfad, paket):
    """CK 26.11.: Ablage NUR nach Geschlecht + Stimmlage (gemessener Grundton DE-Clip), nicht nach Matrix-Charakter
    (Stimmen treffen die Beschreibung nicht immer). Name <g>_<lage>_<nr> bzw. k_<nr>, Nummer aufsteigend nach F0.
    casting = "hoertest": 410 besetzt sie nie automatisch (voice_registry.verfuegbar)."""
    auswahl = json.load(open(auswahl_pfad, encoding="utf-8"))
    st = {s["id"]: s for s in _matrix_laden()}
    _, werte = auswerten(paket)
    out = os.path.join(GPU_DIR, paket, "out")
    reg = VR.laden()
    heute = str(datetime.date.today())
    zuord_pfad = os.path.join(AUS, "zuordnung.json")
    zuord = json.load(open(zuord_pfad, encoding="utf-8")) if os.path.exists(zuord_pfad) else {}
    gruppen = {}
    for sid, seed in auswahl.items():
        seed = int(seed)
        if sid not in st or (sid, seed) not in werte:
            print(f"  ? {sid} s{seed} nicht in Matrix/Paket")
            continue
        g = "k" if sid.startswith("k_") else st[sid]["geschlecht"]
        f0 = werte[(sid, seed)].get("f0_de") or 0.0
        gruppen.setdefault((g, lage(g, f0)), []).append((f0, sid, seed))
    n = 0
    for (g, lg_lage), liste in sorted(gruppen.items()):
        for nr, (f0, sid, seed) in enumerate(sorted(liste), 1):
            s, w = st[sid], werte[(sid, seed)]
            name = f"{g}_{lg_lage}_{nr:02d}" if lg_lage else f"{g}_{nr:02d}"
            herkunft_key = f"{sid}__s{seed}"
            alt = reg.get(name)
            if alt and alt.get("herkunft_matrix") != herkunft_key:
                print(f"  ! {name} existiert schon ({alt.get('werkzeug')}, {alt.get('herkunft_matrix')}) - uebersprungen")
                continue
            ziel = os.path.join(VR.STIMMEN_DIR, name)
            os.makedirs(ziel, exist_ok=True)
            refs = {}
            for lg in SPRACHNAME:
                q = os.path.join(out, key(sid, seed, lg) + ".wav")
                if not os.path.exists(q):
                    if lg in SPRACHEN:
                        print(f"  ! {name} ({sid} s{seed}) {lg} fehlt (erst 'referenzen' laufen lassen)")
                    continue
                shutil.copyfile(q, os.path.join(ziel, f"klon_{lg}.wav"))
                refs[lg] = {"datei": f"klon_{lg}.wav", "text": ref_text(lg)}
            if "de" in refs:
                shutil.copyfile(os.path.join(ziel, "klon_de.wav"), os.path.join(ziel, "hoerprobe.wav"))
            geschl = {"k": "m" if sid.startswith("k_j") else "w"}.get(g, g)
            gtxt = {"k": "Kind", "m": "maennlich", "w": "weiblich"}[g]
            kurz = f"Qwen-Designstimme {gtxt}, {lg_lage or 'Kind'}, F0 {f0:.0f} Hz - Charakter per Hoertest"
            steck = {
                "id": f"qwen_{name}", "name": name, "status": "kandidat", "rolle_typ": "beides",
                "casting": "hoertest",
                "sichtbarkeit": "katalog",      # katalog | exklusiv:<mandant>  (status bleibt Lebenszyklus)
                "herkunft": "design",           # design | sprecher
                "herkunftsvermerk": HERKUNFT if not s.get("abgeleitet") else
                HERKUNFT + f"; abgeleitet aus {s['abgeleitet']['quelle']} (+{s['abgeleitet']['halbtoene']} Halbtoene)",
                "werkzeug": WERKZEUG, "seed": seed,
                "seed_hinweis": "Clip ist massgeblich (Seed je Stapel, nicht bitgenau reproduzierbar)",
                "herkunft_matrix": herkunft_key,
                "herkunft_prompt": s.get("instruct", ""),   # nur Herkunftsnachweis, KEINE Beschreibung der Stimme
                "beschreibung": kurz, "kurz": kurz,
                "merkmale": {"geschlecht": geschl, "tonlage": lg_lage or "hoch",
                             **({"alter": "kind"} if g == "k" else {})},
                "stimmlage": lg_lage, "grundton_hz": f0, "grundton_en_hz": w.get("f0_en"), "referenzen": refs,
                "speaker_embedding": {"modell": "speechbrain/spkrec-ecapa-voxceleb",
                                      **{lg: _emb(out, key(sid, seed, lg)) for lg in refs}},
                "referenz_weg": {ANKER: "VoiceDesign", **{lg: f"Base-Klon aus {ANKER}" for lg in refs if lg != ANKER}},
                "aehnlichkeit": {"de_en": w.get("de_en")},
                "rechte": {"inhaber": "TAELLA", "laufzeit": None, "werke": [], "sprachen": list(refs),
                           "territorien": ["weltweit"]},
                "mandant": None, "werke": [], "language_code": "", "datum": heute, "letzte_nutzung": heute,
                "ttl": "1 Jahr ab letzter Nutzung", "einsatz": "",
            }
            with open(os.path.join(ziel, "steckbrief.json"), "w", encoding="utf-8") as f:
                json.dump(steck, f, ensure_ascii=False, indent=1)
            reg[name] = {k: v for k, v in steck.items() if k != "speaker_embedding"}
            zuord[name] = herkunft_key
            n += 1
            print(f"  + {name:12s} <- {sid} s{seed} (F0 {f0} Hz, DE<->EN {w.get('de_en')})")
    VR.speichern(reg)
    with open(zuord_pfad, "w", encoding="utf-8") as f:
        json.dump(zuord, f, ensure_ascii=False, indent=1)
    print(f"[uebernehmen] {n} Stimmen -> stimmen_archiv/ + stimmen.json, Zuordnung tools/qwen_stimmen/zuordnung.json")


KATALOG_HTML = r"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Qwen-Stimmen Hörkatalog</title><style>
:root{--bg:#faf9f6;--fg:#1f1d1a;--mut:#6b665e;--line:#e3dfd6;--card:#fff;--acc:#2f5d50;--warn:#a5532a}
@media (prefers-color-scheme:dark){:root{--bg:#191816;--fg:#ece8e1;--mut:#9c968c;--line:#34312c;--card:#22201d;--acc:#7fb8a5;--warn:#e09a6f}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;z-index:2}
h1{font-size:17px;margin:0 0 8px}.f{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
select,button,label{font:inherit}select,button{padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
button.p{background:var(--acc);color:var(--bg);border-color:var(--acc)}main{padding:12px 16px;display:grid;gap:10px}
.c{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.c.gew{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}.id{font-weight:600;font-family:ui-monospace,monospace}
.mut{color:var(--mut);font-size:12px}.tag{font-size:11px;border:1px solid var(--line);border-radius:10px;padding:0 6px;margin-left:6px}
.s{display:grid;grid-template-columns:auto 1fr 1fr;gap:6px 10px;align-items:center;margin-top:8px}
.s audio{width:100%;height:32px}.w{color:var(--warn)}details{margin-top:4px}
@media (max-width:640px){.s{grid-template-columns:1fr}}
</style></head><body><header><h1>Qwen-Stimmen Hörkatalog <span class="mut">Paket {PAKET}</span></h1><div class="f">
<select id="g"><option value="">Geschlecht: alle</option><option value="m">männlich</option><option value="w">weiblich</option></select>
<select id="a"><option value="">Alter: alle</option><option>jung</option><option>jungerw</option><option>mittel</option><option>reif</option><option>alt</option><option>kind</option></select>
<select id="ch"><option value="">Charakter: alle</option><option>warm</option><option>kuehl</option><option>verschmitzt</option><option>nervoes</option><option>rau</option><option>weich</option></select>
<label><input type="checkbox" id="e"> nur Erzähler</label><label><input type="checkbox" id="o"> nur ohne Wahl</label>
<span class="mut" id="n"></span><button class="p" id="x">auswahl.json exportieren</button></div>
<div class="mut">DE↔EN = ECAPA-Ähnlichkeit derselben Designstimme in beiden Sprachen (niedrig: klingt wie zwei Personen). „nächste“ = ähnlichste andere Matrixstimme (hoch: zu nah).</div></header>
<main id="m"></main><script>
const D=/*DATEN*/[];let W={};try{W=JSON.parse(localStorage.getItem("qwen_auswahl")||"{}")}catch(e){}
const $=i=>document.getElementById(i);
function sp(){try{localStorage.setItem("qwen_auswahl",JSON.stringify(W))}catch(e){}}
function r(){const g=$("g").value,a=$("a").value,c=$("ch").value,e=$("e").checked,o=$("o").checked;
const L=D.filter(d=>(!g||d.geschlecht==g)&&(!a||d.alter==a)&&(!c||d.charakter==c)&&(!e||d.erzaehler)&&(!o||!W[d.id]));
$("n").textContent=L.length+" Stimmen, "+Object.keys(W).length+" gewählt";
$("m").innerHTML=L.map(d=>`<div class="c ${W[d.id]?"gew":""}"><span class="id">${d.id}</span>${d.erzaehler?'<span class="tag">Erzähler</span>':""}
<div>${d.beschreibung_de}</div><details><summary class="mut">Beschreibung (EN-Prompt)</summary><div class="mut">${d.instruct||"abgeleitet"}</div></details>
${d.seeds.length?d.seeds.map(s=>`<div class="s"><label><input type="radio" name="${d.id}" value="${s.seed}" ${W[d.id]==s.seed?"checked":""}> Seed ${s.seed}<br>
<span class="mut">F0 ${s.f0_de||"–"}/${s.f0_en||"–"} Hz · ${s.dauer_de||"–"} s<br>DE↔EN <b class="${s.de_en<0.6?"w":""}">${s.de_en??"–"}</b> · nächste ${s.naechste||"–"} <b class="${s.naechste_cos>0.85?"w":""}">${s.naechste_cos??""}</b></span></label>
<div><span class="mut">DE</span><audio controls preload="none" src="${s.de}"></audio></div><div><span class="mut">EN (Klon aus DE)</span>${s.en?`<audio controls preload="none" src="${s.en}"></audio>`:'<div class="mut">erst nach Wahl (referenzen)</div>'}</div></div>`).join(""):'<div class="mut">noch keine Clips</div>'}</div>`).join("")}
document.addEventListener("change",ev=>{const t=ev.target;if(t.type=="radio"){W[t.name]=+t.value;sp();r()}else r()});
$("x").onclick=()=>{const b=new Blob([JSON.stringify(W,null,1)],{type:"application/json"});const l=document.createElement("a");l.href=URL.createObjectURL(b);l.download="auswahl.json";l.click()};
r();</script></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("befehl", choices=["matrix", "kandidaten", "katalog", "referenzen", "uebernehmen", "xl"])
    ap.add_argument("--sprachen", default="en")
    ap.add_argument("arg", nargs="*")
    ap.add_argument("--nur", default="")
    ap.add_argument("--seeds", default=",".join(map(str, SEEDS)))
    ap.add_argument("--paket", default=STANDARD_PAKET)
    a = ap.parse_args()
    if a.befehl == "matrix":
        matrix()
    elif a.befehl == "kandidaten":
        sys.exit(kandidaten({x for x in a.nur.split(",") if x}, [int(x) for x in a.seeds.split(",")], a.paket))
    elif a.befehl == "katalog":
        katalog(a.paket)
    elif a.befehl == "referenzen":
        sys.exit(referenzen(a.arg[0], [x for x in a.sprachen.split(",") if x], a.paket))
    elif a.befehl == "uebernehmen":
        uebernehmen(a.arg[0], a.paket)
    elif a.befehl == "xl":
        sys.exit(xl(a.arg[0], int(a.arg[1]), a.paket))
