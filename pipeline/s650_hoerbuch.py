"""STAGE 650 — Hoerbuch-Assembler (Neuaufbau Phase 2, 03.11.2026)
Funktion:     Baut aus der Endfassung (530, audio_final/) je Hoerbuch-Sprache Kapiteldateien je Kanalprofil:
              epub   (EPUB3-Audio, Media Overlay 620): MP3 je Kapitel, ohne Cover
              extern (Plattform, ACX-nah): MP3 je Kapitel (CBR, 44,1 kHz) mit Tags + Cover _quadrat, optional M4B
              mit Kapitelmarken. Ansagen aus 400 (Typ ansage) als eigene Dateien Anfang/Ende. Pausen aus 400
              (pause_after_ms), Kopf-/Schluss-Stille und Lautheit je Profil. Hoerspiel entfaellt vorerst.
Komponenten:  pipeline/s650_hoerbuch.py; Bausteine s500 (einheiten), s530 (lautheit, begrenzen), s510 (WAV),
              s615 (Titel, Autor, Cover-Pfad), s410 (Sprecher)
Eingang:      fassungen/<lg>/audio_final/<tid>.wav + work/530_pruefung_<lg>.json (Gate 530 frei, Datei aktuell);
              work/400_regie.json (Reihenfolge, pause_after_ms, ansagen); casting.json (Sprecher); Cover
              cover_final_<lg>_quadrat.jpg (Gate 615 <lg>:quadrat frei, nur extern); book.json/author.json
Ausgabe:      fassungen/<lg>/hoerbuch/<profil>/<NN>_<kapitel>.mp3 (+ <werk>_<lg>.m4b);
              work/650_hoerbuch_<lg>.json {"kapitel": [{kapitel, datei, dauer, saetze {tid: [start, ende]}}] (Profil
              epub, sonst erstes; Format fuer SMIL 620), "profile": {profil: {kapitel: [...], m4b}}, pruefung};
              Hoerprobe work/_650/<lg>/hoerprobe_<profil>.mp3; Regler work/650_entscheidungen.json
Gate:         je Sprache (status teile "<lg>"): Stopp: Gate 530 nicht frei, 400_regie fehlt, Satz ohne aktuelle
              Endfassung (Luecke), Mock im Live-Lauf, ffmpeg fehlt, Titel/Autor fehlt, extern: Cover/Gate 615, Sprecher,
              Zeitmarken nicht monoton. Kapitelzahl = 190 (sonst Stopp -> 400). Ansagen 100 % (-> Mensch 400).
              Kapiteldauer = Summe Saetze + Pausen +- 0,5 s; Profil (LUFS, Spitze, Grundrauschen, Kopf/Schluss,
              Kapitellaenge, Abtastrate, Bitrate) verfehlt -> 1x automatisch neu normiert, dann Mensch.
              Kanal extern -> einmal je Werk x Sprache Mensch (Hoerprobe Anfang/Schluss + Ansagen, --freigeben);
              danach auto bei gruen. Geaenderte Eingaenge (Hash je Kapitel x Profil) -> nur diese Kapitel neu.
Kosten:       0 $ (CPU/ffmpeg).
Abnehmer:     s620 Audio-Variante (SMIL), s710 Export Extern, s700.

Aufruf:  py -3.11 -m pipeline.s650_hoerbuch <werk> [--profil P:SCHLUESSEL=WERT] [--ausgabe mp3|m4b|beide]
         [--ansagen an|aus] [--sprache LG] [--neu] [--freigeben] [--trocken]
"""
import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, manifest, mock, status

STAGE = "650"
VERSION = 1
SR = 24000
PROFILE = getattr(config, "HOERBUCH_PROFILE", {
    "epub": {"bitrate": "64k", "rate": 24000, "lufs": -18.0, "lufs_tol": 1.0, "peak": -1.0, "rauschen": -60.0,
             "kopf": 0.5, "schluss": 1.0, "kapitel_max_min": 120, "cover": False, "tags": True},
    "extern": {"bitrate": "192k", "rate": 44100, "lufs": -20.0, "lufs_tol": 2.0, "peak": -3.0, "rauschen": -60.0,
               "kopf": 0.75, "schluss": 2.0, "kapitel_max_min": 120, "cover": True, "tags": True},
})
ANSAGE_PFLICHT = ("ansage_titel", "ansage_sprecher", "ansage_ende")     # Autor entfaellt bei unbekanntem Autor
HOERPROBE_S = 20.0
DAUER_TOL = 0.5


# ------------------------------------------------------------------ Ablage
def pfad(werk, lg):
    return config.work_path(werk, f"650_hoerbuch_{lg}")


def ausgabe_dir(werk, lg, profil):
    return os.path.join(config.book_dir(werk), "fassungen", lg, "hoerbuch", profil)


def _json(p, leer=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def entscheidungen(werk):
    return _json(config.work_path(werk, "650_entscheidungen"), {}) or {}


def entscheidung_setzen(werk, wer, **kw):
    d = entscheidungen(werk)
    d.setdefault("protokoll", [])
    for k, v in kw.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    d["protokoll"].append({"wer": wer, "wann": manifest.jetzt(), **kw})
    manifest.json_atomar(config.work_path(werk, "650_entscheidungen"), d, indent=2)
    return d


def profil_werte(ents, name):
    return {**PROFILE[name], **((ents.get("profile") or {}).get(name) or {})}


def profile_fuer(b, lg):
    out = []
    for name in ("epub", "extern"):
        if any(p["inhalt"] == "hoerbuch" and p.get("stufe") == "basic" and name in p["kanaele"]
               for p in b.produkte_fuer(sprache=lg)):
            out.append(name)
    return out


# ------------------------------------------------------------------ Audio
def kap_von(tid):
    return str(tid).split("_")[0]


def gruppen(units):
    """[(kapitel, [unit])] in Hoerreihenfolge; Ansagen vor dem ersten Knoten -> 'anfang', danach -> 'ende'."""
    out = collections.OrderedDict()
    inhalt = False
    for u in units:
        if u["typ"] == "ansage":
            k = "ende" if inhalt else "anfang"
        else:
            k, inhalt = kap_von(u["id"]), True
        out.setdefault(k, []).append(u)
    return list(out.items())


def zusammensetzen(teile, kopf, schluss):
    """teile [(tid, x, pause_ms)] -> (y, {tid: [start, ende]}). Keine Pause nach dem letzten Satz."""
    stuecke, marken, pos = [np.zeros(int(kopf * SR), np.float32)], {}, int(kopf * SR)
    for i, (tid, x, pause) in enumerate(teile):
        marken[tid] = [round(pos / SR, 3), round((pos + len(x)) / SR, 3)]
        stuecke.append(x.astype(np.float32))
        pos += len(x)
        if i < len(teile) - 1 and pause:
            n = int(int(pause) / 1000 * SR)
            stuecke.append(np.zeros(n, np.float32))
            pos += n
    stuecke.append(np.zeros(int(schluss * SR), np.float32))
    return np.concatenate(stuecke), marken


def rauschen_db(y, fenster=0.5):
    """Leisestes 0,5-s-Fenster (RMS dB, Boden -120)."""
    n = int(fenster * SR)
    if len(y) < n:
        return -120.0
    k = len(y) // n
    r = np.sqrt(np.mean(y[:k * n].reshape(k, n).astype(np.float64) ** 2, axis=1))
    return round(float(max(-120.0, 20 * np.log10(max(r.min(), 1e-6)))), 1)


def stille(y, schwelle_db=-60.0):
    """(Stille am Anfang, Stille am Ende) in s."""
    lim = 10 ** (schwelle_db / 20)
    idx = np.nonzero(np.abs(y) > lim)[0]
    if not len(idx):
        return round(len(y) / SR, 3), round(len(y) / SR, 3)
    return round(idx[0] / SR, 3), round((len(y) - 1 - idx[-1]) / SR, 3)


def normieren(y, pw, korrektur=0.0):
    from pipeline import s530_audio_pruefung as P5
    lu, pk = P5.lautheit(y)
    gain = max(-P5.GAIN_MAX, min(P5.GAIN_MAX, float(pw["lufs"]) - lu + korrektur)) if lu > -70 else 0.0
    z = (y * 10 ** (gain / 20)).astype(np.float32)
    if pk + gain > float(pw["peak"]) - 0.5:
        z = P5.begrenzen(z, float(pw["peak"]) - 1.0)
    return z, round(gain, 2)


def kodieren(y, ziel, pw, tags=None, cover=None):
    """float -> MP3 (CBR pw.bitrate, pw.rate, mono) mit ID3-Tags und Cover."""
    from pipeline import s510_hoerspiel_hybrid as s510
    with tempfile.TemporaryDirectory() as d:
        q = os.path.join(d, "k.wav")
        s510.schreiben(q, y)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", q]
        if cover:
            cmd += ["-i", cover, "-map", "0:a", "-map", "1:v", "-c:v", "mjpeg", "-disposition:v", "attached_pic",
                    "-metadata:s:v", "title=Cover", "-metadata:s:v", "comment=Cover (front)"]
        cmd += ["-c:a", "libmp3lame", "-b:a", pw["bitrate"], "-ar", str(pw["rate"]), "-ac", "1", "-id3v2_version", "3"]
        for k, v in (tags or {}).items():
            if v:
                cmd += ["-metadata", f"{k}={v}"]
        tmp = ziel + ".tmp.mp3"
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        r = subprocess.run(cmd + [tmp], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg {os.path.basename(ziel)}: {r.stderr[-300:]}")
        os.replace(tmp, ziel)


def messen(p):
    """Ausgabedatei -> {dauer, rate, bitrate, lufs, peak} (ffprobe + ebur128)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                        "stream=sample_rate,bit_rate:format=duration", "-of", "json", p], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    s = (d.get("streams") or [{}])[0]
    e = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", p, "-map", "0:a", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    i = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", e)
    pk = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", e)
    f = lambda v: -70.0 if (not v or v[-1] == "-inf") else max(-70.0, float(v[-1]))
    return {"dauer": round(float((d.get("format") or {}).get("duration") or 0), 3), "rate": int(s.get("sample_rate") or 0),
            "bitrate": int(s.get("bit_rate") or 0), "lufs": f(i), "peak": f(pk)}


def m4b(werk, lg, dateien, ziel, tags, cover, kapitel_titel):
    """MP3-Kapitel -> M4B (AAC) mit Kapitelmarken und Cover."""
    with tempfile.TemporaryDirectory() as d:
        liste = os.path.join(d, "l.txt")
        with open(liste, "w", encoding="utf-8") as f:
            f.writelines(f"file '{p}'\n".replace("\\", "/") for p in dateien)
        meta = [";FFMETADATA1"] + [f"{k}={v}" for k, v in tags.items() if v]
        pos = 0
        for p, t in zip(dateien, kapitel_titel):
            du = int(messen(p)["dauer"] * 1000)
            meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={pos}", f"END={pos + du}", f"title={t}"]
            pos += du
        mp = os.path.join(d, "meta.txt")
        with open(mp, "w", encoding="utf-8") as f:
            f.write("\n".join(meta) + "\n")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", liste, "-i", mp]
        if cover:
            cmd += ["-i", cover, "-map", "0:a", "-map", "2:v", "-c:v", "mjpeg", "-disposition:v", "attached_pic"]
        cmd += ["-map_metadata", "1", "-map_chapters", "1", "-c:a", "aac", "-b:a", "128k", "-f", "mp4"]
        tmp = ziel + ".tmp"
        r = subprocess.run(cmd + [tmp], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg m4b: {r.stderr[-300:]}")
        os.replace(tmp, ziel)


# ------------------------------------------------------------------ Lauf
def run(werk, wer=None, nur=None, neu=False, freigeben=False, trocken=False):
    from pipeline import s410_casting as s410
    from pipeline import s500_vertonung_gemini as s500
    from pipeline import s510_hoerspiel_hybrid as s510
    from pipeline import s615_cover_final as s615
    wer = wer or "pipeline"
    if freigeben and not trocken:
        return _freigeben(werk, wer)
    b = bestellung.lesen(werk)
    ents = entscheidungen(werk)
    ansagen_an = ents.get("ansagen", "an") != "aus"
    ausgabe = ents.get("ausgabe", "mp3")
    d400 = _json(config.work_path(werk, "400_regie"))
    stt = status.laden(werk)
    z530 = status.zustand(werk, "530", d=stt)
    st = stt["stages"].get(STAGE) or {}
    kap190 = ((stt["stages"].get("190") or {}).get("metriken") or {}).get("kapitel")
    gates = []
    for lg in b.audiosprachen():
        prof = profile_fuer(b, lg)
        if not prof or (nur and lg not in nur):
            continue
        g = gate.Gate(werk, STAGE, scope=lg, ruecksprung="650", wer=wer)
        g.metrik("profile", prof)
        pf = g.hinweis if trocken else g.pflicht
        kw = (lambda r: {}) if trocken else (lambda r: {"ruecksprung": r})
        pf("gate_530", z530 in status.FREI, z530, **kw("530"), text=f"Gate 530 frei ({z530})")
        g.pflicht("regie", bool(d400), ruecksprung="400", text="400_regie.json vorhanden")
        cover = None
        if "extern" in prof:
            z615 = status.zustand(werk, "615", scope=f"{lg}:quadrat", d=stt)
            cover = s615.ausgabe_pfad(werk, lg, "quadrat")
            pf("gate_615", z615 in status.FREI, z615, **kw("615"), text=f"Gate 615 {lg}:quadrat frei ({z615})")
            g.pflicht("cover", os.path.exists(cover), ruecksprung="615", text="Cover _quadrat vorhanden")
        g.pflicht("ffmpeg", bool(shutil.which("ffmpeg") and shutil.which("ffprobe")), text="ffmpeg/ffprobe vorhanden")
        if g.fehler():
            g.entscheide(schreiben=not trocken)
            gates.append(g)
            continue

        # Eingaenge
        units, _ = s500.einheiten(d400, lg)
        if not ansagen_an:
            units = [u for u in units if u["typ"] != "ansage"]
            g.hinweis("ansagen_aus", False, text="Ansagen aus (Regler)")
        m5p = config.work_path(werk, f"530_pruefung_{lg}")
        m5 = manifest.Manifest(werk, f"530_pruefung_{lg}", stage="530") if os.path.exists(m5p) else None
        quelle, fehlt, mocks = {}, [], []
        for u in units:
            k = f"hoerbuch/{u['id']}"
            e = (m5.get(k) if m5 else None) or {}
            if not e or not m5.datei_aktuell(k):
                fehlt.append(u["id"])
                continue
            p = m5._abs(e["datei"])
            quelle[u["id"]] = (p, e.get("datei_hash"))
            if mock.ist_datei(p):
                mocks.append(u["id"])
        n = len(units)
        g.pflicht("abdeckung", n and not fehlt, round(1 - len(fehlt) / n, 4) if n else 0.0, ruecksprung="530",
                  text=f"Abdeckung {n - len(fehlt)}/{n} Saetze mit aktueller Endfassung 530"
                       + (f" – fehlt: {', '.join(fehlt[:5])}" if fehlt else ""))
        g.mock(len(mocks), mocks[:3], ruecksprung="500")
        grp = gruppen(units)
        inhalt = [k for k, _ in grp if k not in ("anfang", "ende")]
        g.metrik("kapitel", len(inhalt))
        if kap190:
            g.gleich("kapitel_190", len(inhalt), kap190, ruecksprung="400")
        else:
            g.hinweis("kapitel_190", False, text="Kapitelzahl 190 unbekannt")
        if ansagen_an:
            da = {u["id"] for u in units if u["typ"] == "ansage"}
            soll = list(ANSAGE_PFLICHT) + [a["id"] for a in (d400.get("ansagen") or {}).get(lg) or []
                                           if a.get("id") not in ANSAGE_PFLICHT]
            fe_a = [a for a in dict.fromkeys(soll) if a not in da]
            g.pruefe("ansagen", not fe_a, round(1 - len(fe_a) / len(set(soll)), 4), 1.0, "mensch", "400",
                     text="Ansagen vollstaendig" + (f" – fehlt: {', '.join(fe_a)}" if fe_a else ""))
        roh = b.roh
        titel, _, _, _ = s615.titel(roh, lg, b.quellsprache)
        autor = s615.autor(werk, roh, lg)
        sprecher = s410.stimme(werk, lg)
        g.pflicht("titel", bool(titel), ruecksprung="110", text=f"Titel {lg}: {titel or '–'}")
        if "extern" in prof:
            g.pflicht("autor", bool(autor), ruecksprung="110", text=f"Autor: {autor or '–'}")
            g.pflicht("sprecher", bool(sprecher), ruecksprung="410", text=f"Sprecher (casting.json): {sprecher or '–'}")
        else:
            g.hinweis("sprecher", bool(sprecher), text=f"Sprecher (casting.json): {sprecher or '–'}")
        if g.fehler() or trocken:
            g.entscheide(schreiben=not trocken)
            gates.append(g)
            continue

        # Bauen je Kapitel x Profil
        alt = _json(pfad(werk, lg), {}) or {}
        altp = {p: {e["kapitel"]: e for e in (v.get("kapitel") or [])} for p, v in (alt.get("profile") or {}).items()}
        kom = f"{s615.GELESEN.get(lg, 'Read by')} {sprecher} · {s615.KI.get(lg, 'AI voice')}" if sprecher else ""
        content = d400.get("content") or {}
        aus = {p: [] for p in prof}
        marken_alle, verletzt, dauer_fehl, kap_lang, neu_normiert = {}, collections.defaultdict(list), [], [], []
        mono_fehl, probe = [], {p: [] for p in prof}
        for i, (kid, us) in enumerate(grp, 1):
            h = next((u for u in us if u["typ"] == "h"), None)
            ktitel = (str((content.get(h["id"]) or {}).get(lg) or "").strip() if h else "") or \
                {"anfang": "Intro", "ende": "Outro"}.get(kid, kid)
            teile_h = [(u["id"], quelle[u["id"]][1], u.get("pause")) for u in us]
            y0, marken = None, None
            for p in prof:
                pw = profil_werte(ents, p)
                ein = manifest.hash_obj({"v": VERSION, "t": teile_h, "pw": pw, "titel": titel, "autor": autor,
                                         "kom": kom, "kt": ktitel, "nr": [i, len(grp)],
                                         "cover": manifest.hash_datei(cover) if (cover and pw["cover"]) else None})
                ziel = os.path.join(ausgabe_dir(werk, lg, p), f"{i:02d}_{kid}.mp3")
                ae = (altp.get(p) or {}).get(kid) or {}
                aktuell = (not neu and ae.get("eingang_hash") == ein and os.path.exists(ziel)
                           and manifest.hash_datei(ziel) == ae.get("datei_hash"))
                if aktuell:
                    e = ae
                else:
                    if y0 is None:
                        teile = [(u["id"], s510.lesen(quelle[u["id"]][0]), u.get("pause")) for u in us]
                        y0, marken = zusammensetzen(teile, 0.0, 0.0)
                    yk = np.concatenate([np.zeros(int(pw["kopf"] * SR), np.float32), y0,
                                         np.zeros(int(pw["schluss"] * SR), np.float32)])
                    mk = {t: [round(a + pw["kopf"], 3), round(b_ + pw["kopf"], 3)] for t, (a, b_) in marken.items()}
                    tags = {"title": ktitel, "album": titel, "artist": autor, "album_artist": autor,
                            "composer": sprecher, "genre": "Audiobook", "track": f"{i}/{len(grp)}",
                            "language": lg, "comment": kom} if pw["tags"] else {}
                    z, gain = normieren(yk, pw)
                    kodieren(z, ziel, pw, tags, cover if pw["cover"] else None)
                    me = messen(ziel)
                    if not (abs(me["lufs"] - pw["lufs"]) <= pw["lufs_tol"] and me["peak"] <= pw["peak"]):
                        z, gain = normieren(yk, pw, korrektur=pw["lufs"] - me["lufs"])
                        kodieren(z, ziel, pw, tags, cover if pw["cover"] else None)
                        me = messen(ziel)
                        neu_normiert.append(f"{p}/{kid}")
                    vorn, hinten = stille(z)
                    soll_dauer = round(len(yk) / SR, 3)
                    e = {"kapitel": kid, "nr": i, "titel": ktitel, "datei": os.path.relpath(ziel, config.book_dir(werk)).replace("\\", "/"),
                         "datei_hash": manifest.hash_datei(ziel), "eingang_hash": ein, "dauer": me["dauer"],
                         "dauer_soll": soll_dauer, "saetze": mk, "gain_db": gain, "rauschen": rauschen_db(z),
                         "kopf": vorn, "schluss": hinten, **{k_: me[k_] for k_ in ("rate", "bitrate", "lufs", "peak")}}
                aus[p].append(e)
                # Pruefung je Kapitel
                if abs(e["dauer"] - e["dauer_soll"]) > DAUER_TOL:
                    dauer_fehl.append(f"{p}/{kid} {e['dauer']}≠{e['dauer_soll']}")
                if e["dauer"] > pw["kapitel_max_min"] * 60:
                    kap_lang.append(f"{p}/{kid}")
                for k_, ok in (("lufs", abs(e["lufs"] - pw["lufs"]) <= pw["lufs_tol"]), ("peak", e["peak"] <= pw["peak"]),
                               ("rauschen", e["rauschen"] <= pw["rauschen"]),
                               ("kopf", e["kopf"] >= pw["kopf"] - 0.05), ("schluss", e["schluss"] >= pw["schluss"] - 0.05),
                               ("rate", e["rate"] == pw["rate"]),
                               ("bitrate", abs(e["bitrate"] - int(pw["bitrate"].rstrip("k")) * 1000) <= 2000)):
                    if not ok:
                        verletzt[k_].append(f"{p}/{kid}")
                zm = sorted(e["saetze"].values())
                if any(b_ <= a for a, b_ in zm) or any(zm[j][0] < zm[j - 1][1] for j in range(1, len(zm))) \
                        or (zm and zm[-1][1] > e["dauer"] + 0.05):
                    mono_fehl.append(f"{p}/{kid}")
                if kid in ("anfang", "ende") or kid == (inhalt[0] if inhalt else None) or \
                        kid == (inhalt[-1] if inhalt else None):
                    probe[p].append((kid, os.path.join(config.book_dir(werk), e["datei"])))
                marken_alle.setdefault(kid, e["saetze"])

        # M4B (extern, Regler)
        m4b_e = {}
        if "extern" in prof and ausgabe in ("m4b", "beide"):
            pw = profil_werte(ents, "extern")
            dateien = [os.path.join(config.book_dir(werk), e["datei"]) for e in aus["extern"]]
            ziel = os.path.join(ausgabe_dir(werk, lg, "extern"), f"{werk}_{lg}.m4b")
            ein = manifest.hash_obj([e["datei_hash"] for e in aus["extern"]])
            am = ((alt.get("profile") or {}).get("extern") or {}).get("m4b") or {}
            if neu or am.get("eingang_hash") != ein or not os.path.exists(ziel):
                m4b(werk, lg, dateien, ziel, {"title": titel, "artist": autor, "album": titel, "genre": "Audiobook",
                                              "comment": kom, "language": lg}, cover, [e["titel"] for e in aus["extern"]])
            m4b_e = {"datei": os.path.relpath(ziel, config.book_dir(werk)).replace("\\", "/"), "eingang_hash": ein,
                     "dauer": messen(ziel)["dauer"]}
        # Verwaiste Kapiteldateien
        for p in prof:
            od = ausgabe_dir(werk, lg, p)
            soll_f = {os.path.basename(e["datei"]) for e in aus[p]} | ({os.path.basename(m4b_e["datei"])} if
                                                                       (p == "extern" and m4b_e) else set())
            for f in os.listdir(od) if os.path.isdir(od) else []:
                if f not in soll_f and os.path.splitext(f)[1] in (".mp3", ".m4b"):
                    os.remove(os.path.join(od, f))
        # Hoerprobe (Anfang/Schluss + Ansagen)
        for p in prof:
            hp = os.path.join(config.work_dir(werk), "_650", lg, f"hoerprobe_{p}.mp3")
            teile = []
            for kid, dp in probe[p]:
                x = _mp3_lesen(dp)
                if kid in ("anfang", "ende"):
                    teile.append(x)
                elif kid == (inhalt[0] if inhalt else None):
                    teile.append(x[:int(HOERPROBE_S * SR)])
                if kid == (inhalt[-1] if inhalt else None) and kid != "ende":
                    teile.append(x[-int(HOERPROBE_S * SR):])
            if teile:
                os.makedirs(os.path.dirname(hp), exist_ok=True)
                kodieren(np.concatenate(teile), hp, {**profil_werte(ents, p), "rate": SR, "bitrate": "64k"})

        # Gate
        g.pruefe("zeitmarken", not mono_fehl, len(mono_fehl), 0, "stopp", "650",
                 text="Zeitmarken monoton, letzte <= Dauer" + (f" – {', '.join(mono_fehl[:4])}" if mono_fehl else ""))
        g.pruefe("dauer", not dauer_fehl, len(dauer_fehl), 0, "mensch", "650",
                 text=f"Kapiteldauer = Saetze + Pausen +- {DAUER_TOL} s" + (f" – {', '.join(dauer_fehl[:4])}" if dauer_fehl else ""))
        g.pruefe("kapitel_laenge", not kap_lang, len(kap_lang), 0, "mensch", "650",
                 text="Kapitellaenge im Profil" + (f" – {', '.join(kap_lang[:4])}" if kap_lang else ""))
        for k_ in ("lufs", "peak", "rauschen", "kopf", "schluss", "rate", "bitrate"):
            v = verletzt.get(k_) or []
            g.pruefe(f"profil_{k_}", not v, len(v), 0, "mensch", "530" if k_ in ("lufs", "peak", "rauschen") else "650",
                     text=f"Profil {k_}" + (f" verfehlt nach Neunormierung: {', '.join(v[:4])}" if v else " ok"))
        if neu_normiert:
            g.hinweis("neu_normiert", False, len(neu_normiert), text=f"1x automatisch neu normiert: {', '.join(neu_normiert[:4])}")
        for p in prof:
            g.metrik(f"dauer_{p}_min", round(sum(e["dauer"] for e in aus[p]) / 60, 1))
        ausgabe_hash = manifest.hash_obj({p: [e["datei_hash"] for e in aus[p]] for p in prof} | {"m4b": m4b_e.get("eingang_hash")})
        g.metrik("ausgabe_hash", ausgabe_hash)
        altt = (st.get("teile") or {}).get(lg) or {}
        mensch_gilt = altt.get("zustand") == "frei" and (altt.get("gate") or {}).get("ergebnis") == "mensch" \
            and (altt.get("metriken") or {}).get("ausgabe_hash") == ausgabe_hash
        if mensch_gilt:
            for p_ in g.pruefungen:
                if not p_["ok"] and p_["bei_fehler"] == "mensch":
                    p_["bei_fehler"] = "hinweis"
                    p_["text"] += " [Mensch-Freigabe gilt, Ausgabe unveraendert]"
        immer = "extern" in prof and not (ents.get("freigabe") or {}).get(lg) and not mensch_gilt
        e = g.entscheide(mensch_immer=immer, mensch_grund="Kanal extern: Hoerprobe Anfang/Schluss + Ansagen "
                         f"(work/_650/{lg}/hoerprobe_extern.mp3) anhoeren, dann --freigeben")
        haupt = "epub" if "epub" in prof else prof[0]
        manifest.json_atomar(pfad(werk, lg), {
            "schema": 1, "stage": STAGE, "sprache": lg, "version": VERSION, "profil": haupt,
            "kapitel": [{k_: x[k_] for k_ in ("kapitel", "datei", "dauer", "saetze", "titel")} for x in aus[haupt]],
            "profile": {p: {"werte": profil_werte(ents, p), "kapitel": aus[p], **({"m4b": m4b_e} if p == "extern" and m4b_e else {})}
                        for p in prof},
            "ausgabe_hash": ausgabe_hash, "pruefung": {"ergebnis": e, "gruende": g.ergebnis["gruende"],
                                                       "hinweise": g.ergebnis["hinweise"], "zeit": manifest.jetzt()}},
            indent=1)
        gates.append(g)
    return gates


def _mp3_lesen(p):
    """MP3 -> float 24 kHz mono (ffmpeg)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, "<i2").astype(np.float32) / 32768


def _freigeben(werk, wer):
    """Hoerprobe Kanal extern: alle Sprachen im Zustand mensch -> frei, einmal je Werk x Sprache."""
    d = status.laden(werk)
    teile = ((d["stages"].get(STAGE) or {}).get("teile") or {})
    offen = [s for s, t in teile.items() if t.get("zustand") == "mensch"]
    fg = dict(entscheidungen(werk).get("freigabe") or {})
    for s in offen:
        status.entscheiden(werk, STAGE, "frei", wer=wer, grund="Hoerprobe Hoerbuch 650", scope=s)
        fg[s] = {"wer": wer, "wann": manifest.jetzt()}
    entscheidung_setzen(werk, wer, freigabe=fg)
    print(f"[650] Freigabe: {', '.join(offen) or 'nichts offen'}")
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 650 Hoerbuch-Assembler")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--profil", action="append", metavar="P:SCHLUESSEL=WERT",
                    help="Profilwert ueberschreiben, z. B. extern:bitrate=128k, epub:schluss=1.5")
    ap.add_argument("--ausgabe", choices=["mp3", "m4b", "beide"], help="Kanal extern: MP3 je Kapitel und/oder M4B")
    ap.add_argument("--ansagen", choices=["an", "aus"])
    ap.add_argument("--sprache", action="append", metavar="LG")
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--freigeben", action="store_true", help="Hoerprobe freigeben (Kanal extern)")
    ap.add_argument("--trocken", action="store_true")
    ap.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--lang", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    wer = a.wer or "pipeline"
    try:
        kw = {}
        if a.profil:
            pr = dict(entscheidungen(a.werk).get("profile") or {})
            for x in a.profil:
                m = re.fullmatch(r"(epub|extern):(\w+)=(.*)", x.strip())
                if not m or m.group(2) not in PROFILE[m.group(1)]:
                    raise ValueError(f"--profil {x!r}: Format P:SCHLUESSEL=WERT ({', '.join(PROFILE['epub'])})")
                alt = PROFILE[m.group(1)][m.group(2)]
                v = m.group(3)
                v = (v.lower() in ("1", "ja", "an", "true")) if isinstance(alt, bool) else \
                    type(alt)(v) if not isinstance(alt, str) else v
                pr.setdefault(m.group(1), {})[m.group(2)] = v
            kw["profile"] = pr
        if a.ausgabe:
            kw["ausgabe"] = a.ausgabe
        if a.ansagen:
            kw["ansagen"] = a.ansagen
        if (kw or a.freigeben) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", wer)
            if kw:
                entscheidung_setzen(a.werk, wer, **kw)
        nur = a.sprache or (a.lang.split(",") if a.lang else None)
        gates = run(a.werk, wer, nur, a.neu or a.force, a.freigeben, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[650] Fehler: {e}")
        return 1
    for g in gates:
        print(f"--- {g.scope}")
        print(g.bericht())
    if a.freigeben or a.trocken:
        return 0
    return gate.EXIT[gate.gesamt([g.ergebnis["ergebnis"] for g in gates])] if gates else 0


if __name__ == "__main__":
    raise SystemExit(main())
