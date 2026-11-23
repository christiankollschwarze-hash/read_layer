"""STAGE 120 — Schritt "Fremdsprache" (Teil B, 22.11.2026; Entscheidung CK 22.11.2026 15:33)
Funktion:     Fremdsprachige Saetze (Zitate) im Lesetext erkennen, flaggen und je Zitat entscheiden lassen:
                uebertragen    -> Uebertragung in die Werksprache ersetzt das Original im Lesetext
                                  (chapter-N.json paragraphs + raw_modernized.txt); Original bleibt hier gespeichert
                behalten       -> Satz bleibt in allen Fassungen im Original; 200 setzt am Knoten sprache_satz=<lg>
                                  (310 uebersetzt nicht, 400/500 sprechen in der Originalsprache, 520 prueft nicht)
                kein           -> Fehlalarm, Flag weg
              Laeuft fuer JEDE Fassung (original und modernisiert), nach der Modernisierung.
Erkennung:    satzweise (tools/satzweise), lokal 0 $: lingua (py -3.11 -m pip install lingua-language-detector),
              sonst Ersatzverfahren Funktionswoerter (Hinweis im Gate). Kursivtitel _..._ und Eigennamen zaehlen nicht;
              Mindestlaenge MIN_WOERTER; Schwelle (Wahrscheinlichkeit) als Regler. Aufeinanderfolgende Fundsaetze
              gleicher Sprache im selben Kapitel = EIN Zitat.
Uebertragung: LLM (Modell wie 120), je Zitat ein Aufruf, Saetze nummeriert, Kontext davor/danach; erst wenn das
              Zitat auf "uebertragen" steht (Kosten vorher: kosten_schaetzen). Danach einmal Mensch (annehmen).
Datei:        work/120_fremd.json {version, zitate: [{id, sprache, p, kapitel, stellen [{absatz, text}],
              entscheidung offen|uebertragen|behalten|kein, uebertragung [je Satz], herkunft llm|hand,
              angenommen, wer, wann}]}
Regler (book.json fremd_regler): schwelle (0.5), min_woerter (4), vorgabe einzeln|alle_uebertragen|alle_behalten.
"""
import json
import os
import re

from config import config
from pipeline import manifest, mock

VERSION = 1
SCHWELLE = 0.5
MIN_WOERTER = 4
VORGABEN = ("einzeln", "alle_uebertragen", "alle_behalten")
ENTSCHEIDUNGEN = ("offen", "uebertragen", "behalten", "kein")
SPRACHEN = ("en", "de", "fr", "es", "it", "la", "nl", "pt")
NAME = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "la": "Latin",
        "nl": "Dutch", "pt": "Portuguese"}
_KURSIV = re.compile(r"_[^_]+_|\*[^*]+\*")
_WORT = re.compile(r"[^\W\d_][\w’'-]*", re.UNICODE)
_LEER = re.compile(r"\s+")

# Ersatzverfahren: haeufige Funktionswoerter je Sprache (nur ohne lingua)
_STOP = {
    "en": "the and of to a in that is was he for it with as his on be at by i this had not are but from or have an they "
          "which you were her she there would their we him been has when who will more no if out so said what up its",
    "de": "der die das und in den von zu mit sich des auf für ist im dem nicht ein eine als auch es an werden aus er hat "
          "dass sie nach wird bei einer um am sind noch wie einem über einen so zum war haben nur oder aber vor zur bis",
    "fr": "le la les de des du et à un une en que qui dans pour pas au sur ne se ce il elle sont est avec plus par vous "
          "nous ils son sa ses mais ou où on tout tous leur aux cette été être comme fait faire y d l qu",
    "es": "el la los las de del y en que a un una por con no se su para es al lo como más pero sus le ya o fue este ha "
          "sí porque esta son entre cuando muy sin sobre también me hasta hay donde quien desde todo nos",
    "it": "il lo la i gli le di del della e a in che un una per con non si è al da come più ma sono anche questo ha nel "
          "alla dei delle se o era suo sua cui mi ci tutto",
    "la": "et in est non ut cum ad quod qui quae sed si de ex per sunt nec enim etiam esse quam autem atque ab hoc "
          "ac tamen neque vel aut ita sic nam iam eius sibi",
    "nl": "de het een en van in is dat op te zijn met voor niet aan er die maar om als ook bij nog uit door dan was",
    "pt": "o a os as de do da e em que um uma para com não se por mais ao dos das como mas foi ele ela seu sua ou",
}
_STOP = {k: set(v.split()) for k, v in _STOP.items()}


# ------------------------------------------------------------ Regler / Datei
def regler(roh):
    r = dict((roh or {}).get("fremd_regler") or {})
    out = {"schwelle": float(r.get("schwelle", SCHWELLE)), "min_woerter": int(r.get("min_woerter", MIN_WOERTER)),
           "vorgabe": r.get("vorgabe") or "einzeln"}
    if not 0 < out["schwelle"] < 1 or out["min_woerter"] < 1 or out["vorgabe"] not in VORGABEN:
        raise ValueError(f"fremd_regler ungueltig: {out} (schwelle 0–1, min_woerter >= 1, vorgabe {VORGABEN})")
    return out


def pfad(werk):
    return os.path.join(config.work_dir(werk), "120_fremd.json")


def lesen(werk):
    p = pfad(werk)
    if not os.path.exists(p):
        return {"version": VERSION, "zitate": []}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def schreiben(werk, d):
    manifest.json_atomar(pfad(werk), d, indent=1)


# ------------------------------------------------------------ Erkennung
_LINGUA = {}


def _lingua(sprachen):
    key = tuple(sorted(sprachen))
    if key not in _LINGUA:
        try:
            from lingua import IsoCode639_1, Language, LanguageDetectorBuilder
            ls = [Language.from_iso_code_639_1(getattr(IsoCode639_1, s.upper())) for s in key]
            _LINGUA[key] = LanguageDetectorBuilder.from_languages(*ls).build()
        except Exception:
            _LINGUA[key] = None
    return _LINGUA[key]


def verfahren():
    return "lingua" if _lingua(SPRACHEN) else "funktionswoerter"


def kern(satz):
    """Satz ohne Kursivtitel und Eigennamen (Grossschreibung nicht am Satzanfang) -> Woerter fuer die Erkennung."""
    w = _WORT.findall(_KURSIV.sub(" ", satz))
    return [x for i, x in enumerate(w) if i == 0 or not x[:1].isupper()]


def sprache(satz, quellsprache, ersatz=False):
    """-> (sprache, wahrscheinlichkeit) des Kerns; (quellsprache, 1.0) bei zu wenig Text."""
    woerter = kern(satz)
    if not woerter:
        return quellsprache, 1.0
    text = " ".join(woerter)
    zaehl = {lg: sum(1 for x in woerter if x.lower().strip("’'") in s) for lg, s in _STOP.items()}
    det = None if ersatz else _lingua(set(SPRACHEN) | {quellsprache})
    if det is not None:
        v = det.compute_language_confidence_values(text)
        if v:
            lg, pr = v[0].language.iso_code_639_1.name.lower(), float(v[0].value)
            if lg != quellsprache and zaehl.get(quellsprache, 0) >= max(2, zaehl.get(lg, 0)):
                return quellsprache, 1.0 - pr            # Funktionswoerter der Werksprache ueberwiegen
            return lg, pr
    ges = sum(zaehl.values())
    if not ges:
        return quellsprache, 1.0
    lg = max(zaehl, key=lambda k: (zaehl[k], k == quellsprache))
    if lg != quellsprache and zaehl[lg] < 2:
        return quellsprache, 1.0
    zweit = max([v for k, v in zaehl.items() if k != lg] or [0])
    return lg, zaehl[lg] / (zaehl[lg] + zweit)


def _saetze(absatz, src):
    from tools import satzweise
    gr = [0] + satzweise.satzgrenzen(absatz, src) + [len(absatz)]
    return [absatz[a:b].strip() for a, b in zip(gr, gr[1:]) if absatz[a:b].strip()]


def zid(sprache_, stellen):
    return "z" + manifest.hash_obj({"l": sprache_, "t": [s["text"] for s in stellen]})[:10]


def erkennen(kapitel, src, rg, ersatz=False):
    """kapitel [(titel, absaetze)] (vor Uebertragung) -> Zitate [{id, sprache, p, kapitel, stellen}]."""
    out = []
    for k, (_t, paras) in enumerate(kapitel, 1):
        cur = None
        for a, p in enumerate(paras):
            if not p or not p.strip() or p.startswith("——"):
                cur = None
                continue
            for s in _saetze(p, src):
                lg, pr = ("", 0.0)
                if len(kern(s)) >= rg["min_woerter"]:
                    lg, pr = sprache(s, src, ersatz)
                if lg and lg != src and pr >= rg["schwelle"]:
                    if cur and cur["sprache"] == lg:
                        cur["stellen"].append({"absatz": a, "text": s})
                        cur["p"] = min(cur["p"], round(pr, 3))
                    else:
                        cur = {"sprache": lg, "p": round(pr, 3), "kapitel": k, "stellen": [{"absatz": a, "text": s}]}
                        out.append(cur)
                elif len(kern(s)) >= 2:                  # kurze Einschuebe ("Sun-tse dit :") trennen nicht
                    cur = None
    for z in out:
        z["id"] = zid(z["sprache"], z["stellen"])
    return out


def abgleichen(alt, neu, rg, wer):
    """Entscheidungen aus alt nach id uebernehmen; neue Zitate nach Vorgabe vorbelegen. -> neue Liste."""
    bisher = {z["id"]: z for z in alt.get("zitate") or []}
    out = []
    for z in neu:
        a = bisher.get(z["id"])
        if a:
            z.update({k: a[k] for k in ("entscheidung", "uebertragung", "herkunft", "angenommen", "wer", "wann")
                      if k in a})
        else:
            z["entscheidung"] = {"alle_uebertragen": "uebertragen", "alle_behalten": "behalten"}.get(rg["vorgabe"],
                                                                                                    "offen")
            if z["entscheidung"] != "offen":
                z.update(wer=f"vorgabe:{wer}", wann=manifest.jetzt())
        out.append(z)
    return out


# ------------------------------------------------------------ Entscheidungen (CLI/Monitor)
def entscheiden(d, aenderungen, wer, texte=None, annehmen=None, neu=None):
    """aenderungen ["ID=uebertragen|behalten|kein|offen"], texte ["ID=Satz1 || Satz2"], annehmen [ID|alle],
    neu [ID] (Uebertragung verwerfen, neu anfordern). Aendert d (120_fremd.json) in place."""
    by = {z["id"]: z for z in d.get("zitate") or []}
    jetzt = manifest.jetzt()

    def z_(i):
        if i not in by:
            raise ValueError(f"Fremdsprache: Zitat {i!r} unbekannt")
        return by[i]
    for x in aenderungen or []:
        i, e = (s.strip() for s in x.split("=", 1))
        if e not in ENTSCHEIDUNGEN:
            raise ValueError(f"Fremdsprache {i}: Entscheidung {e!r} ({ENTSCHEIDUNGEN})")
        z = z_(i)
        z.update(entscheidung=e, wer=wer, wann=jetzt)
        if e != "uebertragen":
            z["angenommen"] = False
    for x in texte or []:
        i, t = x.split("=", 1)
        z = z_(i.strip())
        teile = [s.strip() for s in t.split("||")]
        if not any(teile):
            raise ValueError(f"Fremdsprache {i}: Uebertragung leer")
        z.update(entscheidung="uebertragen", uebertragung=teile, herkunft="hand", angenommen=True, wer=wer, wann=jetzt)
    for i in neu or []:
        z = z_(i.strip())
        z.update(uebertragung=None, herkunft=None, angenommen=False, entscheidung="uebertragen", wer=wer, wann=jetzt)
    for i in annehmen or []:
        for z in (d.get("zitate") or []) if i == "alle" else [z_(i.strip())]:
            if z.get("entscheidung") == "uebertragen" and z.get("uebertragung"):
                z.update(angenommen=True, wer=wer, wann=jetzt)
    return d


# ------------------------------------------------------------ Uebertragung (LLM)
_PROMPT = ("You translate a quotation that appears inside a {werk} text written in {ziel}. The quotation is in "
           "{quelle}. Translate it faithfully into natural {ziel} for readers of the book, keeping the tone and "
           "register of the original; keep proper names. Context before and after is given only for meaning - do "
           "not translate it. Return each numbered sentence on its own line as [n] translation, same numbers, same "
           "order, nothing else.\n\nCONTEXT BEFORE: {vor}\nCONTEXT AFTER: {nach}\n\nQUOTATION:\n{saetze}")


def offen_uebertragen(d):
    return [z for z in d.get("zitate") or [] if z.get("entscheidung") == "uebertragen" and not z.get("uebertragung")]


def kosten_schaetzen(zitate, modell):
    p = getattr(config, "PREISE", {}).get(modell) or {}
    z = sum(len(s["text"]) for x in zitate for s in x["stellen"])
    tok_in = (len(_PROMPT) + 1200) * len(zitate) / 4 + z / 4      # Kontext ~2x600 Zeichen je Zitat
    return round((tok_in * p.get("in", 0) + z / 4 * 1.3 * p.get("out", 0)) / 1e6, 4)


def _kontext(kapitel, z, richtung):
    paras = kapitel[z["kapitel"] - 1][1]
    a = z["stellen"][0]["absatz"] if richtung < 0 else z["stellen"][-1]["absatz"]
    for j in range(a + richtung, -1 if richtung < 0 else len(paras), richtung):
        if paras[j] and paras[j].strip() and not paras[j].startswith("——"):
            t = paras[j]
            return t[-600:] if richtung < 0 else t[:600]
    return ""


def uebertragen(d, kapitel, src, aufruf, modell):
    """Fehlende Uebertragungen per LLM. aufruf(prompt, modell) -> Text. -> Anzahl Aufrufe."""
    n = 0
    for z in offen_uebertragen(d):
        saetze = [s["text"] for s in z["stellen"]]
        if mock.aktiv():
            z.update(uebertragung=[f"[MOCK:UEB] {s}" for s in saetze], herkunft="llm", angenommen=False)
            continue
        prompt = _PROMPT.format(werk="book", ziel=NAME.get(src, src), quelle=NAME.get(z["sprache"], z["sprache"]),
                                vor=_kontext(kapitel, z, -1), nach=_kontext(kapitel, z, 1),
                                saetze="\n".join(f"[{i}] {s}" for i, s in enumerate(saetze, 1)))
        raw = aufruf(prompt, modell)
        n += 1
        got = {int(m.group(1)): m.group(2).strip()
               for m in re.finditer(r"\[(\d+)\]\s*(.*?)(?=\n\[\d+\]|\Z)", raw or "", re.S)}
        if all(got.get(i) for i in range(1, len(saetze) + 1)):
            z.update(uebertragung=[got[i] for i in range(1, len(saetze) + 1)], herkunft="llm", angenommen=False)
        else:
            z["fehler"] = "Antwort unvollstaendig"
    return n


# ------------------------------------------------------------ Anwenden
def anwenden(kapitel, d):
    """Uebertragungen in die Absaetze einsetzen. -> neue Kapitelliste [(titel, absaetze)], nicht gefunden [id]."""
    neu = [(t, list(p)) for t, p in kapitel]
    fehlt = []
    for z in d.get("zitate") or []:
        if z.get("entscheidung") != "uebertragen" or not z.get("uebertragung"):
            continue
        paras = neu[z["kapitel"] - 1][1]
        ueb = list(z["uebertragung"])
        if len(ueb) != len(z["stellen"]):                # Handtext mit anderer Satzzahl: ganz an die erste Stelle
            ueb = [" ".join(ueb)] + [""] * (len(z["stellen"]) - 1)
        for s, t in zip(z["stellen"], ueb):
            p = paras[s["absatz"]]
            i = p.find(s["text"])
            if i < 0:
                fehlt.append(z["id"])
                break
            neu_p = p[:i] + t + p[i + len(s["text"]):]
            paras[s["absatz"]] = _LEER.sub(" ", neu_p).strip() if not t else neu_p
    return neu, sorted(set(fehlt))


def offen(d):
    zs = d.get("zitate") or []
    return {"offen": [z["id"] for z in zs if z.get("entscheidung", "offen") == "offen"],
            "unuebertragen": [z["id"] for z in zs if z.get("entscheidung") == "uebertragen" and not z.get("uebertragung")],
            "nicht_angenommen": [z["id"] for z in zs if z.get("entscheidung") == "uebertragen" and z.get("uebertragung")
                                 and not z.get("angenommen")]}


# ------------------------------------------------------------ Kette: 200 markiert "behalten"
def _norm(s):
    return _LEER.sub(" ", _KURSIV.sub(lambda m: m.group(0)[1:-1], s or "")).strip().lower()


def knoten_markieren(werk, content, src):
    """200: Knoten, deren Text ein behaltener Fremdsatz ist (oder ihn enthaelt), bekommen sprache_satz=<lg>.
    -> Anzahl markierter Knoten."""
    d = lesen(werk)
    saetze = [(_norm(s["text"]), z["sprache"]) for z in d.get("zitate") or [] if z.get("entscheidung") == "behalten"
              for s in z["stellen"]]
    n = 0
    for e in content.values():
        if not isinstance(e, dict):
            continue
        e.pop("sprache_satz", None)
        t = _norm(e.get(src))
        if not saetze or len(t.split()) < 2:
            continue
        for s, lg in saetze:
            if t == s or (len(t) >= 12 and (t in s or s in t)):
                e["sprache_satz"] = lg
                n += 1
                break
    return n


def satz_sprache(e, lg_fassung):
    """Folgestufen: Sprache, in der ein Knoten in Fassung lg_fassung gesprochen/geprueft wird."""
    return e.get("sprache_satz") or lg_fassung
