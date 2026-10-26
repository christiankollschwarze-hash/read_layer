"""STAGE 345 — Verschiebungsdetektor (Pruefaligner neben s340)
Funktion:      Findet Saetze, in denen die DeepSeek-Wortanker aus s340 um ein Wort verrutscht sind, und
               laesst NUR diese Saetze von DeepSeek neu zuordnen.
Wirkungsweise: awesome-align-with-co (Modal, gpu_align/pruefaligner_modal.py) liefert je Satz unabhaengige
               Anker {"id","w":[[i,[[a,b],..]],..]}. Vergleich auf Ebene der Ziel-Tokens (\\S+):
               Treffer(i,d) = Pruefanker von i trifft den s340-Anker des Nachbarn i+d (d=-1/+1), nicht den eigenen.
               Kette = >= MIN_KETTE Treffer gleicher Richtung hintereinander (Woerter ohne Anker auf einer Seite
               unterbrechen nicht). Markierte Saetze -> DeepSeek (s340-Prompt + Hinweis auf die Kette).
               Neue Zuordnung wird nur uebernommen, wenn sie weniger Kettentreffer hat und nicht mehr als
               MAX_ANKERVERLUST Anker verliert; sonst bleibt s340.
Komponenten:   pipeline/s345_verschiebung.py, s340 (Prompt, resolve_alignment), s525 (ziel_spans),
               gpu_align/pruefaligner_modal.py (awesome_co auf Modal-T4, Hugging Face nur dort)
Zulieferer:    s340 (work/340_wortalignment.json), Pruefaligner (work/345_pruefaligner.json)
Abnehmer:      s340-Datei (reparierte Saetze, Sicherung work/340_wortalignment_vor345.json),
               s525 Wortbruecke, s710. Bericht: work/345_verschiebung.json
Aufruf:        python -m pipeline.s345_verschiebung <werk>              (nur erkennen)
               python -m pipeline.s345_verschiebung <werk> --nachlauf   (erkennen + DeepSeek fuer markierte Saetze)
(AP 54b, 26.10.2026)
"""
import os
import re
import sys
import json
import shutil
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

STAGE = "345"
MIN_KETTE = 3
MAX_ANKERVERLUST = 0.10
BATCH = 10


def _ztok(text):
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text or "")]


def _tokset(spans, ztok):
    return {k for k, (a, b) in enumerate(ztok) for s in spans if a < s[1] and s[0] < b}


def ketten(align, ziel_text, pruef_w):
    """-> Liste von Ketten [{"von","bis","richtung","treffer":[i,..]}]."""
    from pipeline.s525_wortbruecke import ziel_spans
    zt = _ztok(ziel_text)
    A = {}
    for w, (sp, _) in zip(align, ziel_spans(align, ziel_text, reparatur=True)):
        A[w["i"]] = _tokset(sp, zt)
    B = {i: _tokset(sp, zt) for i, sp in pruef_w}
    n = max(A) + 1 if A else 0
    status = []          # je i: +1/-1 = Treffer, 0 = neutral, None = Bruch
    for i in range(n):
        a, b = A.get(i, set()), B.get(i, set())
        if not a and not b or not b:
            status.append(0)
            continue
        if b & a:
            status.append(None)
            continue
        d_hit = [d for d in (-1, 1) if b & A.get(i + d, set())]
        status.append(d_hit[0] if len(d_hit) == 1 else (None if not d_hit else d_hit[0]))
    out = []
    for d in (-1, 1):
        lauf = []
        for i, s in enumerate(status + [None]):
            if s == d:
                lauf.append(i)
            elif s == 0 and lauf:
                continue
            else:
                if len(lauf) >= MIN_KETTE:
                    out.append({"von": lauf[0], "bis": lauf[-1], "richtung": d, "treffer": lauf})
                lauf = []
    return sorted(out, key=lambda k: k["von"])


def _anker(align):
    _, _, ks = config.align_keys()
    return sum(1 for w in align if w.get(ks))


def erkennen(content, pruef):
    src, tgt = config.SOURCE_LANGUAGE, config.TARGET_LANGUAGES[0]
    markiert = {}
    for tid, w in pruef.items():
        v = content.get(tid) or {}
        if not v.get("align"):
            continue
        k = ketten(v["align"], v.get(tgt, ""), w)
        if k:
            markiert[tid] = k
    return markiert


def _hinweis(tid, kett, align):
    teile = []
    for k in kett:
        woerter = " ".join(f'[{w["i"]}]{w[config.SOURCE_LANGUAGE]}' for w in align if k["von"] <= w["i"] <= k["bis"])
        teile.append(f"{woerter}")
    return (f"CHECK for ID {json.dumps(tid)}: a previous attempt shifted the anchors of these words by one "
            f"position (each word got the counterpart of its neighbour): {' | '.join(teile)}. "
            f"Map each of them to ITS OWN counterpart, or null.")


def nachlauf(book_id, data, markiert, pruef):
    from pipeline import api_layer, usage_log
    from pipeline import s340_wortalignment as s340
    usage_log.set_context(book_id, f"{STAGE}_verschiebung")
    src, tgt = config.SOURCE_LANGUAGE, config.TARGET_LANGUAGES[0]
    c = data["content"]
    ids = list(markiert)
    protokoll = {}
    for b in range(0, len(ids), BATCH):
        teil = ids[b:b + BATCH]
        items = [(t, c[t][src], c[t][tgt]) for t in teil]
        prompt = s340._build_prompt(items)
        prompt = prompt.replace("Return ONLY a JSON object",
                                "\n".join(_hinweis(t, markiert[t], c[t]["align"]) for t in teil) +
                                "\n\nReturn ONLY a JSON object", 1)
        n_w = sum(len(s340.tokenize_en(x[1])) for x in items)
        try:
            raw = api_layer.call_model("aligner", prompt, max_tokens=min(16000, max(2000, n_w * 12)))
            got = api_layer.parse_json(raw) or {}
        except Exception as e:
            print(f"  ! Batch {b // BATCH + 1}: {e}")
            got = {}
        for t in teil:
            alt = c[t]["align"]
            if not got.get(t):
                protokoll[t] = {"ergebnis": "keine_antwort"}
                continue
            neu = s340.resolve_alignment(c[t][src], c[t][tgt], got[t])
            k_alt = sum(len(k["treffer"]) for k in markiert[t])
            k_neu = sum(len(k["treffer"]) for k in ketten(neu, c[t][tgt], pruef[t]))
            a_alt, a_neu = _anker(alt), _anker(neu)
            ok = k_neu < k_alt and a_neu >= a_alt - max(1, int(MAX_ANKERVERLUST * a_alt))
            protokoll[t] = {"ergebnis": "uebernommen" if ok else "verworfen",
                            "kettentreffer": [k_alt, k_neu], "anker": [a_alt, a_neu]}
            if ok:
                c[t]["align"] = neu
        print(f"  Nachlauf {min(b + BATCH, len(ids))}/{len(ids)}")
    return protokoll


def run(book_id, mit_nachlauf=False):
    config.werk_sprachen(book_id)   # AP 55: richtungsneutral (Quelle aus book.json)
    p340 = config.work_path(book_id, "340_wortalignment")
    data = json.load(open(p340, encoding="utf-8"))
    pp = config.work_path(book_id, f"{STAGE}_pruefaligner")
    if not os.path.exists(pp):
        raise FileNotFoundError(f"{pp} fehlt - zuerst Modal: py -3.11 -m modal run gpu_align/pruefaligner_modal.py --werk {book_id}")
    pruef = {s["id"]: s["w"] for s in json.load(open(pp, encoding="utf-8"))}
    markiert = erkennen(data["content"], pruef)
    n_tr = sum(len(k["treffer"]) for v in markiert.values() for k in v)
    n_s = sum(1 for v in data["content"].values() if v.get("align"))
    print(f"[{STAGE}] {book_id}: {len(markiert)}/{n_s} Saetze mit Verschiebungskette (>= {MIN_KETTE}), "
          f"{n_tr} betroffene Woerter")
    bericht = {"erstellt": dt.datetime.now().isoformat(timespec="seconds"), "min_kette": MIN_KETTE,
               "saetze": n_s, "markiert": markiert, "betroffene_woerter": n_tr}
    if mit_nachlauf and markiert:
        sich = config.work_path(book_id, "340_wortalignment_vor345")
        if not os.path.exists(sich):
            shutil.copy2(p340, sich)
        prot = nachlauf(book_id, data, markiert, pruef)
        json.dump(data, open(p340, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        rest = erkennen(data["content"], pruef)
        bericht["nachlauf"] = prot
        bericht["nach_nachlauf"] = {"markiert": len(rest),
                                    "betroffene_woerter": sum(len(k["treffer"]) for v in rest.values() for k in v)}
        ue = sum(1 for x in prot.values() if x["ergebnis"] == "uebernommen")
        print(f"[{STAGE}] Nachlauf: {ue}/{len(prot)} uebernommen | danach {len(rest)} Saetze markiert, "
              f"{bericht['nach_nachlauf']['betroffene_woerter']} Woerter")
    pb = config.work_path(book_id, f"{STAGE}_verschiebung")
    if mit_nachlauf and os.path.exists(pb):      # AP 55: Bericht des vorigen Laufs behalten (2. Nachlauf)
        shutil.copy2(pb, config.work_path(book_id, f"{STAGE}_verschiebung_vorher"))
    json.dump(bericht, open(pb, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return bericht


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run(args[0] if args else "call-of-the-wild", mit_nachlauf="--nachlauf" in sys.argv)
