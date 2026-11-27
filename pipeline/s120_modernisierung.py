"""STAGE 120 — Modernisierung (GATE_KATALOG.md Zeile 120 + Befund 120, umgebaut 01.11.2026)
Funktion:     Sanfte Modernisierung des Quelltexts (nur `fassung: modernisiert` aus 115); bei `original`
              wird der Originaltext unveraendert durchgereicht (nur Kapitel-Gate).
Eingang:      Gutenberg: raw.txt (Text zwischen den Gutenberg-Marken, entfasert, Kapitelerkennung);
              ePub: work/modernized/chapter-N.json aus 150 (Original bleibt als chapter-N.original.json).
Ausgabe:      work/modernized/chapter-N.json {title, paragraphs, fassung, quelle_hash, param, fehlend},
              work/modernized/chapter-N.original.json, raw_modernized.txt (###-Marken), work/120_kapitel.json
              (Kapitelbestaetigung).
Gate:         Kapitel-Gate VOR LLM-Aufrufen: erkannte Kapitel + Titel vs. Referenz (Gutenberg:
              Inhaltsverzeichnis in raw.txt; ePub: Kapitelliste aus 150) -> gleich auto, sonst Mensch
              (bestaetigen mit --kapitel-ok). Inhalts-Gate NACH Modernisierung: Absatzabdeckung 100 %
              (1x automatisch nachfordern, danach Luecke -> Stopp); Laenge je Kapitel 0,85-1,20, Absatz-
              Ausreisser (ausserhalb 0,6-1,6) <= 3 %, Eigennamen >= 98 % -> sonst Mensch; Lizenzreste = 0
              -> sonst Stopp (Ruecksprung 100). Stichprobe 5 Absatzpaare als Metrik.
Resume:       Kapitel mit gleichem quelle_hash + Parametern wird uebersprungen; offene Luecken werden
              nachgefordert; geaenderte Quelle/Parameter -> Kapitel neu.
Fremdsprache: (22.11.2026, jede Fassung) pipeline/s120_fremd.py - fremdsprachige Zitate flaggen, je Zitat
              uebertragen | behalten | kein (work/120_fremd.json); uebertragene ersetzen das Original in chapter-N.json
              (Basis in paragraphs_vor_fremd) und raw_modernized.txt; offene/nicht angenommene -> Mensch.
Kosten:       DeepSeek (config.MODELS modernizer, sonst translator), Log Stage 120.
Regler:       --staerke sanft|mittel, --modell, --temperatur, --stueck ZEICHEN, --kapitel N (neu, mehrfach),
              --absatz K:N (Absatz neu, mehrfach), --absatz-text K:N=TEXT (manuell), --kapitel-ok, --force,
              --fremd ID=uebertragen|behalten|kein|offen, --fremd-text ID=SATZ1 || SATZ2, --fremd-annehmen ID|alle,
              --fremd-neu ID, --fremd-schwelle P, --fremd-min N, --fremd-vorgabe einzeln|alle_uebertragen|alle_behalten
Abkuerzungen: (22.11.2026, Teil A2, nur fassung modernisiert) pipeline/s120_abk.py - nach dem Fremdsprache-Schritt
              Abkuerzungen im Lesetext ausschreiben (Tabelle wie 400, Ziffern bleiben), work/120_abk.json;
              --abk ID=WORT (leer = bleibt stehen, offen = zuruecksetzen), --abk-werk LG:ABK=WORT (book.json abk_sprech),
              --abk-lesetext an|aus (book.json abk_lesetext). Offene Befunde -> Mensch.
Aufruf:       python -m pipeline.s120_modernisierung <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch.
"""
import argparse
import datetime
import difflib
import json
import os
import re
import sys

from config import config
from pipeline import bestellung, gate, mock, s080_mandant, usage_log
from pipeline import s120_fremd as fremd_mod
from pipeline import s120_abk as abk_mod
from pipeline import spuren as SP
from pipeline import kapiteltext as epub
from pipeline.manifest import hash_obj, json_atomar

STAGE = "120"
HR = "——HR——"
PROMPT_V = 2
STUECK = 3500
TEMPERATUR = 0.3
LAENGE = (0.85, 1.20)
AUSREISSER = (0.6, 1.6)
AUSREISSER_MAX = 0.03
AUSREISSER_MIN_ZEICHEN = 60
EIGENNAMEN_MIN = 0.98
TITEL_TREFFER_MIN = 0.8
TITEL_AEHNLICH = 0.75          # Schreibvarianten im Verzeichnis ("Manœuvring" / "MANŒUVERING")
KURZ_WOERTER = 100
LIZENZ = re.compile(r"project gutenberg|gutenberg\.org|gutenberg-tm|full license", re.I)

_BASIS = ("You {art} a public-domain English literary text for contemporary readers and language learners. "
          "For each numbered segment: {was} PRESERVE the plot, meaning, narrative voice, tone, and ALL "
          "proper names. Leave passages in other languages (e.g. French or Latin quotations) exactly as they are; "
          "do not translate them. Do not summarize, omit, or add content; keep roughly the same length. Return each "
          "result on its own line, prefixed with the SAME number in the form [n], in the same order. "
          "Output ONLY the numbered lines.")
SYS = {
    "sanft": _BASIS.format(art="gently modernize", was=(
        "break up long, convoluted Victorian sentences into clearer, shorter ones; replace archaic or "
        "obscure vocabulary with natural modern English.")),
    "mittel": _BASIS.format(art="modernize", was=(
        "rewrite long, convoluted sentences into clear modern sentences; replace archaic or obscure "
        "vocabulary, idioms and forms of address with natural modern English; modernize punctuation.")),
}

# Deutsch (22.11.2026, AP Art of War Navarra): Quelltexte in alter Rechtschreibung (ca. 1880-1920)
_BASIS_DE = ("Du {art} einen gemeinfreien deutschen literarischen Text für heutige Leser und Sprachlernende. "
             "Für jedes nummerierte Segment: {was} BEWAHRE Inhalt, Bedeutung, Erzählstimme, Ton und ALLE "
             "Eigennamen in ihrer Schreibung (auch Umschriften wie Suntzu, Wutzu, Lü-mêng, Wên-chou). Fremdsprachige "
             "Passagen (z. B. lateinische oder französische Zitate) unverändert lassen, nicht übersetzen. "
             "Nichts zusammenfassen, weglassen oder hinzufügen; ungefähr gleiche Länge. Verse (Gedichtzeilen) "
             "bleiben Verse: Reim und Versmaß möglichst erhalten. Gib jedes Ergebnis in einer eigenen Zeile aus, "
             "mit DERSELBEN Nummer in der Form [n] davor, in derselben Reihenfolge. Gib NUR die nummerierten Zeilen aus.")
_RECHTSCHREIBUNG_DE = ("bringe die Rechtschreibung auf den heutigen Stand (z. B. dass statt daß, muss statt muß, "
                       "Ue/Ae/Oe am Wortanfang als Ü/Ä/Ö, Tür statt Thür, Intrigen statt Intriguen, Getrennt- und "
                       "Zusammenschreibung nach heutiger Regel); ")
# Franzoesisch (25.11.2026, Testwerk Monte-Cristo): Prosa um 1840-1900; Rechtschreibung ist weitgehend heutig,
# Schwerpunkt Satzbau, veraltete Woerter und Passé simple bleibt (literarische Erzaehlzeit, nicht ersetzen).
_BASIS_FR = ("Tu {art} un texte littéraire français du domaine public pour des lecteurs et apprenants d'aujourd'hui. "
             "Pour chaque segment numéroté : {was} PRÉSERVE l'intrigue, le sens, la voix narrative, le ton et TOUS "
             "les noms propres dans leur graphie. Garde le passé simple et l'imparfait de la narration ainsi que le "
             "vouvoiement des dialogues. Laisse les passages dans d'autres langues (citations latines, italiennes, "
             "anglaises) exactement tels quels, sans les traduire. Ne résume pas, n'omets rien, n'ajoute rien ; "
             "longueur à peu près identique. Les vers restent des vers. Rends chaque résultat sur sa propre ligne, "
             "précédé du MÊME numéro sous la forme [n], dans le même ordre. Ne rends QUE les lignes numérotées.")
SYS_SPRACHE = {
    "en": SYS,
    "fr": {
        "sanft": _BASIS_FR.format(art="modernises avec délicatesse", was=(
            "remplace les mots, tournures et graphies vieillis ou devenus obscurs par un français naturel "
            "d'aujourd'hui ; ne simplifie la syntaxe que pour les phrases très longues et enchevêtrées.")),
        "mittel": _BASIS_FR.format(art="modernises", was=(
            "reformule les phrases longues et enchevêtrées en phrases claires d'aujourd'hui ; remplace les mots, "
            "tournures et formules de politesse vieillis par un français naturel d'aujourd'hui ; modernise la "
            "ponctuation.")),
    },
    "de": {
        "sanft": _BASIS_DE.format(art="modernisierst behutsam", was=(
            _RECHTSCHREIBUNG_DE + "ersetze veraltete oder heute unverständliche Wörter und Wendungen durch "
            "natürliches heutiges Deutsch; den Satzbau nur bei sehr langen, verschachtelten Sätzen glätten.")),
        "mittel": _BASIS_DE.format(art="modernisierst", was=(
            _RECHTSCHREIBUNG_DE + "formuliere lange, verschachtelte Sätze in klare heutige Sätze um; ersetze "
            "veraltete Wörter, Wendungen und Anreden durch natürliches heutiges Deutsch; modernisiere die "
            "Zeichensetzung.")),
    },
}


def _sys(param):
    """System-Prompt je Quellsprache (param['sprache'] fehlt bei en -> Hash englischer Werke unveraendert)."""
    return SYS_SPRACHE.get(param.get("sprache", "en"), SYS)[param["staerke"]]


def mod_dir(werk):
    return os.path.join(config.work_dir(werk), "modernized")


def _lesen(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _woerter(paras):
    return sum(len(p.split()) for p in paras if p != HR)


def _zeichen(paras):
    return sum(len(p) for p in paras if p != HR)


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ------------------------------------------------------------ Quelle
def inhaltsverzeichnis(text):
    """Eintraege des Gutenberg-Inhaltsverzeichnisses (erstes Viertel, Zeile 'CONTENTS') oder None."""
    zeilen = text.replace("\r", "").split("\n")
    grenze = max(200, len(zeilen) // 4)
    start = None
    for i, z in enumerate(zeilen[:grenze]):
        if re.fullmatch(r"\s*(table\s+of\s+)?contents\.?\s*", z, re.I):
            start = i
            break
    if start is None:
        return None
    eintraege, leer = [], 0
    for z in zeilen[start + 1:]:
        s = z.strip()
        if not s:
            leer += 1
            if eintraege and leer >= 4:
                break
            continue
        if len(s) > 80:
            break
        if eintraege and leer >= 3 and kapitel_schluessel(s) and \
                kapitel_schluessel(s)[:2] == (kapitel_schluessel(eintraege[0]) or (None, None))[:2]:
            break                                            # Textbeginn nach dem Verzeichnis
        leer = 0
        s = re.sub(r"(\s{2,}|\s*\.{2,}\s*)\d+\s*$", "", s).strip()   # Seitenzahl mit Leerraum/Punktleiste
        if not s:
            continue
        if eintraege and _norm(s) == _norm(eintraege[0]):
            break
        eintraege.append(s)
    return eintraege or None


STRUKTUR = re.compile(r"(volume|vol\.|part|book)\s+([ivxlc]+|\d+|one|two|three|four|five|six|seven|eight|"
                      r"nine|ten|first|second|third|fourth|fifth|the\s+\w+)\.?", re.I)


def ohne_struktur(titel):
    """Gliederungszeilen ohne eigenen Titel (VOLUME I., PART TWO) zaehlen nicht als Kapitel."""
    return [t for t in titel if not STRUKTUR.fullmatch((t or "").strip())]


def _gutenberg_text(werk):
    from tools import s100_anlegen
    rp = config.raw_path(werk)
    if not os.path.exists(rp):
        raise FileNotFoundError(f"raw.txt fehlt: {rp}")
    with open(rp, encoding="utf-8", errors="ignore") as f:
        roh = f.read()
    _s, _e, kern = s100_anlegen.text_rahmen(roh)
    return epub._strip_boilerplate(kern)


_NUMMER = re.compile(r"\s*(chapter|kapitel|book|part|letter|stave)\s+([ivxlc]+|\d+)\b\.?(.*)$", re.I | re.S)
_ROEMISCH = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}


def _zahl(t):
    if t.isdigit():
        return int(t)
    w, vor = 0, 0
    for ch in reversed(t.lower()):
        v = _ROEMISCH[ch]
        w, vor = (w - v, vor) if v < vor else (w + v, v)
    return w


def kapitel_schluessel(s):
    """'Chapter IV. The Flight' -> ('chapter', 4, 'theflight') oder None."""
    m = _NUMMER.match(s or "")
    return (m.group(1).lower(), _zahl(m.group(2)), _norm(m.group(3))) if m else None


def kapitel_nach_referenz(text, ref):
    """Kapitelgrenzen entlang des Inhaltsverzeichnisses: Ueberschrift = Block, der dem naechsten erwarteten
    Eintrag entspricht und dem Fliesstext folgt. -> [(titel, absaetze)] oder None (Referenz nicht gefunden)."""
    soll = [_norm(t) for t in ohne_struktur(ref) if _norm(t)]
    if not soll:
        return None
    blocks = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
    ist_hr = lambda x: bool(re.fullmatch(r"[\*\u2014\-\s]{3,}", x))

    schl = [kapitel_schluessel(t) for t in ohne_struktur(ref) if _norm(t)]

    def passt(x, k):
        bn = _norm(x)
        if len(x) > 120 or not bn:
            return False
        n = soll[k]
        if bn == n or (bn.startswith(n) and len(n) >= 4):
            return True
        a, e = kapitel_schluessel(x), schl[k]          # "CHAPTER IV." passt zu "Chapter IV. The Flight"
        return bool(a and e and a[:2] == e[:2] and (not a[2] or not e[2] or a[2] == e[2]
                                                     or difflib.SequenceMatcher(None, a[2], e[2]).ratio() >= TITEL_AEHNLICH))

    kand = [len(x) <= 120 and any(passt(x, k) for k in range(len(soll))) for x in blocks]

    def text_folgt(i):
        for j in range(i + 1, len(blocks)):
            if kand[j]:
                return False
            if not ist_hr(blocks[j]) and len(blocks[j]) >= 120:
                return True
        return False

    def naechster(i):
        return next((j for j in range(i + 1, len(blocks)) if not ist_hr(blocks[j])), None)

    kap, pos, cur, gliederung = [], 0, None, []
    for i, x in enumerate(blocks):
        j = naechster(i)
        if (pos + 1 < len(soll) and kand[i] and passt(x, pos) and not text_folgt(i) and j is not None
                and passt(blocks[j], pos + 1) and text_folgt(j)):
            gliederung.append(ohne_struktur(ref)[pos])       # Sammelueberschrift ohne eigenen Text
            pos += 1                                          # ("INTRODUCTION" -> "Sun Wu and his Book")
            continue
        if pos < len(soll) and kand[i] and passt(x, pos) and text_folgt(i):
            cur = (epub._titlecase(x), [])
            kap.append(cur)
            pos += 1
        elif cur is None:
            continue
        elif ist_hr(x):
            cur[1].append(HR)
        else:
            cur[1].append(" ".join(z.strip() for z in x.split("\n")))
    return (kap, gliederung) if pos == len(soll) else None


def original_kapitel(werk, b):
    """-> (kapitel [(titel, absaetze)], referenz [titel] | None, herkunft)."""
    from pipeline import s090_eingang
    d = mod_dir(werk)
    if s090_eingang.eingangsart(b.roh)[0] in bestellung.TEXT_EINGANG:
        text = _gutenberg_text(werk)
        flach = epub._rewrap(text)
        kap = epub._split_chapters(flach)
        ref = inhaltsverzeichnis(text)
        if ref and len(ohne_struktur(ref)) != len(ohne_struktur([t for t, _p in kap])):
            r = kapitel_nach_referenz(flach, ref)               # Heuristik weicht ab -> entlang Referenz
            if r:
                kap, gliederung = r
                ref = [t for t in ref if t not in gliederung]    # Sammelueberschriften sind keine Kapitel
        return kap, ref, "raw.txt"          # Front-/Endmatter entfernt _write_marked_source (wie bisher)
    kap, i = [], 1
    while True:
        po, pc = (os.path.join(d, f"chapter-{i}.original.json"), os.path.join(d, f"chapter-{i}.json"))
        if os.path.exists(po):
            k = _lesen(po)
        elif os.path.exists(pc):
            k = _lesen(pc)
            if k.get("fassung") == "modernisiert":
                raise RuntimeError(f"chapter-{i}.json ist modernisiert, Original fehlt -> 150 neu einlesen")
        else:
            break
        kap.append((k.get("title", ""), list(k.get("paragraphs") or [])))
        i += 1
    ref = None
    bp = os.path.join(config.work_dir(werk), "ingest_bericht.json")
    if os.path.exists(bp):
        ref = [k.get("titel", "") for k in (_lesen(bp).get("kapitel") or [])] or None
    return kap, ref, "epub"


# ------------------------------------------------------------ Kapitel-Gate
def struktur_hash(kap):
    return hash_obj([[t, len(p), _woerter(p)] for t, p in kap])


def kapitel_bestaetigt(werk, kap):
    p = os.path.join(config.work_dir(werk), "120_kapitel.json")
    return os.path.exists(p) and _lesen(p).get("struktur") == struktur_hash(kap)


def kapitel_bestaetigen(werk, kap, wer):
    p = os.path.join(config.work_dir(werk), "120_kapitel.json")
    rec = _lesen(p) if os.path.exists(p) else {}
    rec.update({"struktur": struktur_hash(kap), "kapitel": len(kap), "wer": wer,
                "wann": datetime.datetime.now().isoformat(timespec="seconds")})
    json_atomar(p, rec, indent=2)


def titel_treffer(kap, ref):
    if not kap or not ref:
        return 0.0
    rn = [_norm(r) for r in ref if _norm(r)]
    rk = {kapitel_schluessel(r)[:2] for r in ref if kapitel_schluessel(r)}
    hit = 0
    for t, _p in kap:
        n, k = _norm(t), kapitel_schluessel(t)
        if (n and any(n == r or n in r or r in n for r in rn)) or (k and k[:2] in rk):
            hit += 1
    return hit / len(kap)


def kapitel_gate(g, werk, kap, ref, herkunft):
    """Prueft Kapitelstruktur (ohne LLM). -> True, wenn ohne Mensch weiter."""
    g.metrik("kapitel", len(kap))
    g.metrik("kapitel_referenz", len(ref) if ref else None)
    g.metrik("kapitel_herkunft", herkunft)
    g.metrik("kapitel_liste", [f"{i}. {t} ({_woerter(p)} W.)" for i, (t, p) in enumerate(kap, 1)][:60])
    g.pflicht("kapitel_vorhanden", len(kap) >= 1 and _woerter([x for _t, p in kap for x in p]) > 0,
              wert=len(kap), ruecksprung="100" if herkunft == "raw.txt" else "150", text="Kapitel erkannt")
    kurz = [i for i, (_t, p) in enumerate(kap, 1) if _woerter(p) < KURZ_WOERTER]
    g.hinweis("kurze_kapitel", not kurz, wert=kurz[:20],
              text=f"{len(kurz)} Kapitel < {KURZ_WOERTER} Woerter" if kurz else "keine kurzen Kapitel")
    if kapitel_bestaetigt(werk, kap):
        g.hinweis("kapitel_bestaetigt", True, text="Kapitelstruktur manuell bestaetigt (120_kapitel.json)")
        return True
    tt = titel_treffer(kap, ref) if ref else 0.0
    g.metrik("titel_treffer", round(tt, 3))
    if not ref:
        text = "kein Inhaltsverzeichnis als Referenz -> Kapitelliste pruefen, dann --kapitel-ok"
        ok = False
    else:
        nr, nk = len(ohne_struktur(ref)), len(ohne_struktur([t for t, _p in kap]))
        ok = nr == nk and tt >= TITEL_TREFFER_MIN
        text = (f"Referenz {nr} = erkannt {nk}, Titeltreffer {tt:.0%}" if ok else
                f"Referenz {nr} vs. erkannt {nk}, Titeltreffer {tt:.0%} -> pruefen, dann --kapitel-ok")
    g.pruefe("kapitel_referenz", ok, wert=len(kap), schwelle="= Referenz", bei_fehler="mensch",
             ruecksprung="120", text=text)
    return ok


# ------------------------------------------------------------ Modernisierung
def _call_model(prompt, modell=None, temperatur=TEMPERATUR):
    from pipeline import api_layer
    if "modernizer" not in config.MODELS:
        config.MODELS["modernizer"] = config.MODELS.get("translator", "deepseek-flash")
    return api_layer.call_model("modernizer", prompt, temperature=temperatur, modell=modell or None)


def _gruppen(items, stueck):
    gr, cur, size = [], [], 0
    for n, s in items:
        if cur and size + len(s) > stueck:
            gr.append(cur)
            cur, size = [], 0
        cur.append((n, s))
        size += len(s)
    if cur:
        gr.append(cur)
    return gr


def _anfragen(items, param):
    """items [(n, text)] -> {n: modernisiert} (fehlende fehlen)."""
    def eins(grp):                                   # eine Gruppe (Spur innerhalb des Kapitels)
        if mock.aktiv():
            return {n: f"[MOCK:MOD] {s}" for n, s in grp}
        raw = _call_model(_sys(param) + "\n\n" + "\n".join(f"[{n}] {s}" for n, s in grp),
                          param["modell"], param["temperatur"])
        d = {}
        for m in re.finditer(r"\[(\d+)\]\s*(.*?)(?=\n\[\d+\]|\Z)", raw, re.S):
            n, t = int(m.group(1)), m.group(2).strip()
            if t and any(n == x for x, _s in grp):
                d[n] = t
        return d
    erg, _info = SP.parallel(None, STAGE, _gruppen(items, param["stueck"]), eins, SP.anzahl(stage=STAGE),
                             fortschritt_an=False, text=False)
    done = {}
    for d in erg:
        done.update(d)
    return done


def modernisieren(paras, param, nur=None, alt=None):
    """-> (absaetze, fehlend). nur = Indizes, die neu angefragt werden (sonst alle ausser HR);
    fehlende werden 1x einzeln nachgefordert, danach bleibt das Original (Index in fehlend)."""
    out = list(alt) if alt is not None else list(paras)
    ziel = [i for i in (range(len(paras)) if nur is None else nur) if paras[i] != HR and paras[i].strip()]
    done = _anfragen([(i, paras[i]) for i in ziel], param)
    offen = [i for i in ziel if i not in done]
    if offen:
        done.update(_anfragen([(i, paras[i]) for i in offen], dict(param, stueck=1)))
    fehlend = []
    for i in ziel:
        if i in done:
            out[i] = done[i]
        else:
            out[i] = paras[i]
            fehlend.append(i)
    return out, fehlend


# ------------------------------------------------------------ Inhalts-Gate


def eigennamen(text):
    """Grossgeschriebene Woerter, die nicht am Satzanfang stehen."""
    out = set()
    for p in text:
        if p == HR:
            continue
        for m in re.finditer(r"\b([A-Z][a-z]{2,})\b", p):
            vor = p[:m.start()].rstrip()
            if not vor or vor[-1] in ".!?\"“‘(—:;'":
                continue
            out.add(m.group(1))
    return out


def inhalt_pruefen(g, kap_orig, kap_neu, fehlend_gesamt):
    """kap_orig/kap_neu: [(titel, absaetze)]."""
    g.pflicht("abdeckung", fehlend_gesamt == 0, wert=fehlend_gesamt, ruecksprung="120",
              text=f"{fehlend_gesamt} Absaetze nach Nachforderung ohne Modernisierung" if fehlend_gesamt
              else "Absatzabdeckung 100 %")
    laenge_aus, paare, aus, namen_soll, namen_ist, stich = [], 0, [], 0, 0, []
    for k, ((_t, po), (_t2, pn)) in enumerate(zip(kap_orig, kap_neu), 1):
        zo, zn = _zeichen(po), _zeichen(pn)
        r = zn / zo if zo else 1.0
        if not LAENGE[0] <= r <= LAENGE[1]:
            laenge_aus.append(f"{k}: {r:.2f}")
        for i, (a, b) in enumerate(zip(po, pn)):
            if a == HR or len(a) < AUSREISSER_MIN_ZEICHEN:
                continue
            paare += 1
            q = len(b) / len(a)
            if not AUSREISSER[0] <= q <= AUSREISSER[1]:
                aus.append(f"{k}:{i + 1} ({q:.2f})")
        no = eigennamen(po)
        tn = " ".join(pn)
        namen_soll += len(no)
        namen_ist += sum(1 for n in no if n in tn)
    g.pruefe("laenge_kapitel", not laenge_aus, wert=laenge_aus[:20], schwelle=f"{LAENGE[0]}-{LAENGE[1]}",
             bei_fehler="mensch", ruecksprung="120",
             text=f"{len(laenge_aus)} Kapitel ausserhalb {LAENGE[0]}-{LAENGE[1]}" if laenge_aus
             else "Laenge je Kapitel im Rahmen")
    anteil = len(aus) / paare if paare else 0.0
    g.metrik("ausreisser_liste", aus[:30])
    g.pruefe("ausreisser", anteil <= AUSREISSER_MAX, wert=round(anteil, 4), schwelle=f"<= {AUSREISSER_MAX}",
             bei_fehler="mensch", ruecksprung="120",
             text=f"Absatz-Ausreisser {len(aus)}/{paare} ({anteil:.1%})")
    quote = namen_ist / namen_soll if namen_soll else 1.0
    g.pruefe("eigennamen", quote >= EIGENNAMEN_MIN, wert=round(quote, 4), schwelle=f">= {EIGENNAMEN_MIN}",
             bei_fehler="mensch", ruecksprung="120", text=f"Eigennamen erhalten {namen_ist}/{namen_soll}")
    alle = [(k, i, a, b) for k, ((_t, po), (_t2, pn)) in enumerate(zip(kap_orig, kap_neu), 1)
            for i, (a, b) in enumerate(zip(po, pn)) if a != HR and len(a) >= AUSREISSER_MIN_ZEICHEN]
    if alle:
        schritt = max(1, len(alle) // 5)
        stich = [{"stelle": f"{k}:{i + 1}", "original": a[:300], "neu": b[:300]}
                 for k, i, a, b in alle[::schritt][:5]]
    g.metrik("stichprobe", stich)


def lizenz_pruefen(g, kap_neu):
    treffer = [f"{k}:{i + 1}" for k, (_t, ps) in enumerate(kap_neu, 1) for i, p in enumerate(ps)
               if LIZENZ.search(p)]
    g.pflicht("lizenzreste", not treffer, wert=treffer[:10], ruecksprung="100",
              text=f"Lizenzreste in {len(treffer)} Absaetzen" if treffer else "keine Lizenzreste")


# ------------------------------------------------------------ Lauf
def _param(staerke, modell, temperatur, stueck):
    if "modernizer" not in config.MODELS:
        config.MODELS["modernizer"] = config.MODELS.get("translator", "deepseek-flash")
    return {"staerke": staerke or "sanft", "modell": modell or config.MODELS["modernizer"],
            "temperatur": TEMPERATUR if temperatur is None else temperatur,
            "stueck": stueck or STUECK, "prompt_v": PROMPT_V}


ALT_PARAM = {"altbestand": True}


def altbestand(alt, titel, paras, fassung):
    """Kapitel aus dem alten 120 (ohne quelle_hash) mit gleicher Struktur -> uebernehmen statt neu (Kosten)."""
    return (fassung == "modernisiert" and alt and "quelle_hash" not in alt and alt.get("title") == titel
            and len(alt.get("paragraphs") or []) == len(paras))


def altbestand_abweichung(d, kap):
    """Alte Kapitel (ohne quelle_hash) vorhanden, Struktur passt nicht vollstaendig -> Befund, sonst None."""
    alt = {}
    for f in os.listdir(d):
        m = re.fullmatch(r"chapter-(\d+)\.json", f)
        if m:
            alt[int(m.group(1))] = _lesen(os.path.join(d, f))
    if not alt or any("quelle_hash" in a for a in alt.values()):
        return None
    passend = sum(1 for k, (t, p) in enumerate(kap, 1) if altbestand(alt.get(k), t, p, "modernisiert"))
    if len(alt) == len(kap) and passend == len(kap):
        return None
    return {"alt": len(alt), "neu": len(kap), "passend": passend}


def quelle_schreiben(g, werk, d, force):
    """raw_modernized.txt aus den Kapiteln schreiben. Fremd geaendert (Hash != zuletzt von 120 geschrieben,
    Inhalt != neu) -> nicht ueberschreiben (False), ausser --force."""
    pfad = os.path.join(config.book_dir(werk), "raw_modernized.txt")
    neu = _write_marked_source(werk, d, nur_text=True)
    kp = os.path.join(config.work_dir(werk), "120_kapitel.json")
    rec = _lesen(kp) if os.path.exists(kp) else {}
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8") as f:
            ist = f.read()
        if ist == neu:
            g.hinweis("quelle_unveraendert", True, text="raw_modernized.txt unveraendert")
            return True
        if not force and rec.get("quelle_hash") != hash_obj(ist):
            g.pruefe("quelle_fremd", False, bei_fehler="mensch", ruecksprung="120",
                     text="raw_modernized.txt ausserhalb von 120 geaendert -> nicht ueberschrieben")
            return False
    _write_marked_source(werk, d)
    rec["quelle_hash"] = hash_obj(neu)
    json_atomar(kp, rec, indent=2)
    return True


def _kosten(zeichen):
    return getattr(config, "ANGEBOT_USD_100K", {}).get("modernisierung", 0) * zeichen / 100000


def _unveraendert(paras, neu):
    """Altbestand: lange Absaetze, die woertlich dem Original gleichen (alter 120 setzte fehlende [n]
    still als Original ein) -> als Luecke nachfordern."""
    return [i for i, (a, b) in enumerate(zip(paras, neu))
            if a != HR and len(a) >= AUSREISSER_MIN_ZEICHEN and a == b]


def _absatz_ziele(werte, n_kap):
    """['3:12', ...] -> {kapitel: [index0, ...]}"""
    out = {}
    for w in werte or []:
        k, a = w.split(":", 1)
        k, a = int(k), int(a)
        if not 1 <= k <= n_kap:
            raise ValueError(f"--absatz {w}: Kapitel {k} gibt es nicht")
        out.setdefault(k, []).append(a - 1)
    return out


def fremd_schritt(g, werk, b, kap_basis, wer, fremd, modell):
    """Schritt Fremdsprache (jede Fassung). -> Kapitel mit eingesetzten Uebertragungen."""
    fremd = fremd or {}
    rg_neu = {k: v for k, v in (fremd.get("regler") or {}).items() if v is not None}
    if rg_neu:
        r = dict(b.roh.get("fremd_regler") or {})
        r.update(rg_neu)
        fremd_mod.regler({"fremd_regler": r})
        b = bestellung.feld_setzen(werk, fremd_regler=r)
    rg = fremd_mod.regler(b.roh)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    d = fremd_mod.lesen(werk)
    neu = fremd_mod.erkennen(kap_basis, src, rg)
    d = {"version": fremd_mod.VERSION, "verfahren": fremd_mod.verfahren(), "regler": rg,
         "zitate": fremd_mod.abgleichen(d, neu, rg, wer)}
    fremd_mod.entscheiden(d, fremd.get("entscheidung"), wer, fremd.get("text"), fremd.get("annehmen"),
                          fremd.get("neu"))
    zu = fremd_mod.offen_uebertragen(d)
    g.metrik("fremd_kosten_usd", fremd_mod.kosten_schaetzen(zu, modell))
    n = fremd_mod.uebertragen(d, kap_basis, src, lambda p, m: _call_model(p, m), modell) if zu else 0
    g.metrik("fremd_llm_aufrufe", n)
    kap_aus, fehlt = fremd_mod.anwenden(kap_basis, d)
    fremd_mod.schreiben(werk, d)
    zs = d["zitate"]
    g.metrik("fremd_zitate", {e: sum(1 for z in zs if z.get("entscheidung") == e) for e in fremd_mod.ENTSCHEIDUNGEN})
    g.hinweis("fremd_verfahren", d["verfahren"] == "lingua", wert=d["verfahren"],
              text=f"Spracherkennung {d['verfahren']}" + ("" if d["verfahren"] == "lingua" else
                   " (Ersatz; besser: py -3.11 -m pip install lingua-language-detector)"))
    o = fremd_mod.offen(d)
    g.pruefe("fremd_offen", not o["offen"], wert=len(o["offen"]), schwelle="= 0", bei_fehler="mensch",
             ruecksprung="120", text=f"Fremdsprachige Zitate ohne Entscheidung: {len(o['offen'])} von {len(zs)} "
                                     "(Monitor 120: uebertragen | Original behalten | kein Fremdtext)")
    nu = o["unuebertragen"] + o["nicht_angenommen"]
    g.pruefe("fremd_uebertragung", not nu, wert=len(nu), schwelle="= 0", bei_fehler="mensch", ruecksprung="120",
             text=f"Uebertragungen pruefen/annehmen: {len(o['nicht_angenommen'])}"
                  + (f", ohne Uebertragung {len(o['unuebertragen'])}" if o["unuebertragen"] else ""))
    g.pruefe("fremd_einsetzen", not fehlt, wert=fehlt[:10], bei_fehler="mensch", ruecksprung="120",
             text=f"Uebertragung nicht einsetzbar (Satz im Text nicht gefunden): {len(fehlt)}")
    return kap_aus


def abk_schritt(g, werk, b, kap, wer, abk, fassung):
    """Schritt Abkuerzungen (Teil A2, nur fassung modernisiert). -> Kapitel mit ausgeschriebenen Abkuerzungen."""
    abk = abk or {}
    felder = {}
    if abk.get("werk"):
        from pipeline import s400_regie
        felder["abk_sprech"] = s400_regie.abk_werk_setzen(b.roh.get("abk_sprech"), abk["werk"])
    if abk.get("lesetext") is not None:
        felder["abk_lesetext"] = bool(abk["lesetext"])
    if felder:
        b = bestellung.feld_setzen(werk, **felder)
    d = abk_mod.lesen(werk)
    abk_mod.entscheiden(d, abk.get("entscheidung"), wer)
    if not abk_mod.aktiv(b.roh, fassung):
        grund = "fassung original (400 spricht aus)" if fassung != "modernisiert" else "abgeschaltet (abk_lesetext)"
        d.update({"version": abk_mod.VERSION, "aktiv": False, "grund": grund, "stellen": [], "befunde": []})
        abk_mod.schreiben(werk, d)
        g.metrik("abk_ausgeschrieben", 0)
        return kap
    src = b.quellsprache or config.SOURCE_LANGUAGE
    fremd_saetze = [s["text"] for z in fremd_mod.lesen(werk).get("zitate") or []
                    if z.get("entscheidung") == "behalten" for s in z["stellen"]]
    neu = abk_mod.anwenden(kap, src, b.roh.get("abk_sprech"), d, fremd_saetze)
    abk_mod.schreiben(werk, d)
    g.metrik("abk_ausgeschrieben", len(d["stellen"]))
    g.metrik("abk_herkunft", abk_mod.zusammenfassung(d))
    g.pruefe("abk_offen", not d["befunde"], wert=len(d["befunde"]), schwelle="= 0", bei_fehler="mensch",
             ruecksprung="120", text=f"Abkuerzungen ohne passende Regel: {len(d['befunde'])} "
                                     "(Monitor 120: ausschreiben | bleibt stehen | in die Werktabelle)")
    if d.get("verwaist"):
        g.hinweis("abk_verwaist", False, wert=d["verwaist"][:10],
                  text=f"Abkuerzungs-Entscheidungen ohne Stelle im Text: {len(d['verwaist'])} (Text geaendert?)")
    return neu


def run(werk, wer=None, staerke=None, modell=None, temperatur=None, stueck=None, kapitel=None,
        absatz=None, absatz_text=None, kapitel_ok=False, force=False, fremd=None, abk=None):
    """Gate 120. Rueckgabe auto | mensch | stopp.
    fremd = {entscheidung [ID=E], text [ID=T], annehmen [ID|alle], neu [ID], regler {schwelle, min_woerter, vorgabe}}"""
    wer = s080_mandant.nutzer(wer)
    regler = any([staerke, modell, temperatur is not None, stueck, kapitel, absatz, absatz_text, kapitel_ok, force,
                  any((fremd or {}).values()), any(v is not None and v != [] for v in (abk or {}).values())])
    if regler:
        s080_mandant.darf(werk, "bestellen", wer)
    b = bestellung.lesen(werk)
    g = gate.Gate(werk, STAGE, ruecksprung="120", wer=wer)
    usage_log.set_context(werk, STAGE)

    from pipeline import s115_fassung
    fassung = b.fassung or "original"
    g.hinweis("fassung_aus_115", "fassung" not in b.abgeleitet, wert=fassung,
              text=f"fassung {fassung}" + (" (abgeleitet, 115 nicht gelaufen)" if "fassung" in b.abgeleitet else ""))
    if fassung == "modernisiert" and b.quellsprache not in s115_fassung.MODERN_SPRACHEN:
        g.hinweis("prompt_quellsprache", False, wert=b.quellsprache,
                  text=f"kein Modernisierungs-Prompt fuer {b.quellsprache} -> fassung original erzwungen")
        fassung = "original"
    g.metrik("fassung", fassung)

    try:
        kap, ref, herkunft = original_kapitel(werk, b)
    except (FileNotFoundError, RuntimeError) as e:
        from pipeline import s090_eingang
        g.pflicht("quelle", False, wert=str(e),
                  ruecksprung="100" if s090_eingang.eingangsart(b.roh)[0] in bestellung.TEXT_EINGANG else "150",
                  text=str(e))
        e2 = g.entscheide()
        print(g.bericht())
        return e2

    if kapitel_ok:
        kapitel_bestaetigen(werk, kap, wer)
    if not kapitel_gate(g, werk, kap, ref, herkunft):
        e = g.entscheide(mensch_immer=True, mensch_grund="Kapitel-Gate: Kapitelstruktur pruefen "
                         f"(python -m pipeline.s120_modernisierung {werk} --kapitel-ok)")
        print(g.bericht())
        return e

    d = mod_dir(werk)
    os.makedirs(d, exist_ok=True)
    param = _param(staerke, modell, temperatur, stueck)
    if (b.quellsprache or "en") != "en":           # nur Nicht-en: Sprache in param (en-Hash bleibt gleich)
        param["sprache"] = b.quellsprache
    abw = altbestand_abweichung(d, kap) if fassung == "modernisiert" else None
    if abw and not force:
        z = sum(_zeichen(p) for _t, p in kap)
        g.metrik("altbestand_abweichung", abw)
        g.pruefe("altbestand", False, wert=abw, bei_fehler="mensch", ruecksprung="120",
                 text=f"alter modernisierter Text mit anderer Kapitelstruktur ({abw['alt']} -> {abw['neu']} "
                      f"Kapitel, {abw['passend']} uebernehmbar) -> nichts geschrieben")
        e = g.entscheide(mensch_immer=True, mensch_grund=(
            f"Altbestand weicht ab: Neuaufbau mit --force (~{_kosten(z):.2f} $, Folgestufen ab 190 neu) "
            "oder Altstand behalten (120 nicht neu laufen lassen)"))
        print(g.bericht())
        return e
    g.metrik("param", param if fassung == "modernisiert" else None)
    neu_kap = set(kapitel or [])
    ziele = _absatz_ziele(absatz, len(kap))
    texte = {}
    for w in absatz_text or []:
        stelle, t = w.split("=", 1)
        k, a = (int(x) for x in stelle.split(":", 1))
        texte.setdefault(k, {})[a - 1] = t

    param_regler = any([staerke, modell, temperatur is not None, stueck])
    kap_neu, fehlend_gesamt, aufrufe, uebernommen, schreib = [], 0, 0, 0, []
    def kapitel_job(a):
        """Ein Kapitel (eine Spur): Original sichern, Modernisierung (nur offene Absaetze). Zaehler lokal."""
        k, (titel, paras) = a
        z = {"aufrufe": 0, "uebernommen": 0}
        json_atomar(os.path.join(d, f"chapter-{k}.original.json"), {"title": titel, "paragraphs": paras},
                    indent=2)
        pc = os.path.join(d, f"chapter-{k}.json")
        qh = hash_obj({"t": titel, "p": paras})
        alt = _lesen(pc) if os.path.exists(pc) else {}
        if alt.get("paragraphs_vor_fremd"):              # Basis vor eingesetzten Uebertragungen
            alt = dict(alt, paragraphs=alt["paragraphs_vor_fremd"])
        if altbestand(alt, titel, paras, fassung):
            alt = dict(alt, quelle_hash=qh, fassung=fassung, param=ALT_PARAM,
                       fehlend=_unveraendert(paras, alt["paragraphs"]))
            z["uebernommen"] += 1
        gleich = (alt.get("quelle_hash") == qh and alt.get("fassung") == fassung
                  and (fassung == "original" or alt.get("param") == param
                       or (alt.get("param") == ALT_PARAM and not param_regler))
                  and len(alt.get("paragraphs") or []) == len(paras))
        manuell = list(alt.get("manuell") or []) if gleich else []
        if fassung == "original":
            out, fehlend = list(paras), []
        elif gleich and not force and k not in neu_kap:
            nur = sorted(set(alt.get("fehlend") or []) | set(ziele.get(k, [])))
            if nur:
                out, fehlend = modernisieren(paras, param, nur=nur, alt=alt["paragraphs"])
                fehlend = sorted((set(alt.get("fehlend") or []) - set(nur)) | set(fehlend))
                z["aufrufe"] += 1
                manuell = [m for m in manuell if m not in nur]
            else:
                out, fehlend = list(alt["paragraphs"]), list(alt.get("fehlend") or [])
        else:
            out, fehlend = modernisieren(paras, param)
            z["aufrufe"] += 1
            manuell = []
        for i, t in (texte.get(k) or {}).items():
            if not 0 <= i < len(out):
                raise ValueError(f"--absatz-text {k}:{i + 1}: Absatz gibt es nicht")
            out[i] = t
            fehlend = [f for f in fehlend if f != i]
            manuell = sorted(set(manuell) | {i})
        daten = {"title": titel, "paragraphs": out, "fassung": fassung, "quelle_hash": qh,
                 "fehlend": fehlend, "manuell": manuell}
        if fassung == "modernisiert":
            daten["param"] = alt.get("param") if (gleich and not force and k not in neu_kap
                                                  and alt.get("param") == ALT_PARAM) else param
        print(f"  [120] Kapitel {k}/{len(kap)}: {fassung}" + (f", {len(fehlend)} Luecken" if fehlend else ""))
        return (pc, daten, alt), (titel, out), len(fehlend), z


    jobs = list(enumerate(kap, 1))
    n_sp = SP.anzahl(b.roh, "modernisierung_spuren", None, STAGE) if fassung == "modernisiert" else 1
    erg, sp_info = SP.parallel(werk, STAGE, jobs, kapitel_job, n_sp, einheit="Kapitel",
                               gewicht=[sum(len(x) for x in p) for _k, (_t, p) in jobs])
    SP.metriken(g, sp_info)
    for sch, kn, nf, z in erg:                      # feste Reihenfolge
        schreib.append(sch)
        kap_neu.append(kn)
        fehlend_gesamt += nf
        aufrufe += z["aufrufe"]
        uebernommen += z["uebernommen"]
    kap_aus = fremd_schritt(g, werk, b, kap_neu, wer, fremd, param["modell"])
    kap_aus = abk_schritt(g, werk, b, kap_aus, wer, abk, fassung)
    for (pc, daten, alt), (_t, ps) in zip(schreib, kap_aus):
        if ps != daten["paragraphs"]:                   # Basis vor Nachschritten (Fremdsprache, Abkuerzungen)
            daten["paragraphs_vor_fremd"] = daten["paragraphs"]
            daten["paragraphs"] = ps
        alt_roh = _lesen(pc) if os.path.exists(pc) else {}
        if daten != alt_roh:
            json_atomar(pc, daten, indent=2)

    for f in os.listdir(d):                       # verwaiste Kapitel einer alten Struktur
        m = re.fullmatch(r"chapter-(\d+)(\.original)?\.json", f)
        if m and int(m.group(1)) > len(kap):
            os.remove(os.path.join(d, f))
    if not quelle_schreiben(g, werk, d, force):
        e = g.entscheide(mensch_immer=True, mensch_grund=(
            "raw_modernized.txt wurde ausserhalb von 120 geaendert (z. B. tools/drama_vorbereiten) -> "
            "behalten (120 nicht neu) oder mit --force ueberschreiben"))
        print(g.bericht())
        return e

    g.metrik("kapitel_bearbeitet", aufrufe)
    g.metrik("altbestand_uebernommen", uebernommen)
    n_mock = sum(1 for _t, ps in kap_aus for p in ps if mock.ist_text(p))
    g.mock(n_mock)
    lizenz_pruefen(g, kap_aus)
    if fassung == "modernisiert":
        inhalt_pruefen(g, kap, kap_neu, fehlend_gesamt)
    e = g.entscheide()
    print(g.bericht())
    return e


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 120 Modernisierung")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--staerke", choices=tuple(SYS))
    ap.add_argument("--modell")
    ap.add_argument("--temperatur", type=float)
    ap.add_argument("--stueck", type=int, help="Zeichen je Anfrage (Standard 3500)")
    ap.add_argument("--kapitel", type=int, action="append", help="Kapitel N sauber neu erzeugen (mehrfach)")
    ap.add_argument("--absatz", action="append", help="K:N Absatz neu erzeugen (mehrfach)")
    ap.add_argument("--absatz-text", action="append", help="K:N=TEXT Absatz manuell ersetzen")
    ap.add_argument("--kapitel-ok", action="store_true", help="erkannte Kapitelstruktur bestaetigen")
    ap.add_argument("--force", action="store_true", help="alle Kapitel neu")
    ap.add_argument("--fremd", action="append", metavar="ID=E", help="uebertragen|behalten|kein|offen")
    ap.add_argument("--fremd-text", action="append", metavar="ID=TEXT", help="Uebertragung von Hand (Saetze mit ||)")
    ap.add_argument("--fremd-annehmen", action="append", metavar="ID|alle")
    ap.add_argument("--fremd-neu", action="append", metavar="ID", help="Uebertragung neu anfordern")
    ap.add_argument("--fremd-schwelle", type=float)
    ap.add_argument("--fremd-min", type=int)
    ap.add_argument("--fremd-vorgabe", choices=fremd_mod.VORGABEN)
    ap.add_argument("--abk", action="append", metavar="ID=WORT", help="Abkuerzung: Wort (leer = bleibt, offen = zurueck)")
    ap.add_argument("--abk-werk", action="append", metavar="LG:ABK=WORT", help="Werktabelle book.json abk_sprech")
    ap.add_argument("--abk-lesetext", choices=("an", "aus"), help="Abkuerzungen im Lesetext ausschreiben")
    a = ap.parse_args(argv)
    fremd = {"entscheidung": a.fremd, "text": a.fremd_text, "annehmen": a.fremd_annehmen, "neu": a.fremd_neu,
             "regler": {"schwelle": a.fremd_schwelle, "min_woerter": a.fremd_min, "vorgabe": a.fremd_vorgabe}}
    if not any(fremd["regler"].values()):
        fremd["regler"] = None
    try:
        e = run(a.werk, a.wer, a.staerke, a.modell, a.temperatur, a.stueck, a.kapitel, a.absatz,
                a.absatz_text, a.kapitel_ok, a.force, fremd,
                {"entscheidung": a.abk, "werk": a.abk_werk,
                 "lesetext": None if a.abk_lesetext is None else a.abk_lesetext == "an"})
    except ValueError as x:
        print(f"[120] Fehler: {x}")
        return 1
    return gate.EXIT[e]


def _book_title(book_id: str) -> str:
    bp = os.path.join(config.book_dir(book_id), "book.json")
    if os.path.exists(bp):
        try:
            b = json.load(open(bp, encoding="utf-8"))
            return b.get("titel_original") or b.get("title") or book_id
        except Exception:
            pass
    return book_id


def _author_name(book_id: str) -> str:
    """author.json (Gutenberg, wie bisher), sonst book.json autor_name (ePub-Weg 150)."""
    try:
        slug = config.author_of(book_id)
        ap = os.path.join(config.author_dir(slug), "author.json")
        n = json.load(open(ap, encoding="utf-8")).get("name_display", "")
        if n:
            return n
    except Exception:
        pass
    try:
        bp = os.path.join(config.book_dir(book_id), "book.json")
        return json.load(open(bp, encoding="utf-8")).get("autor_name") or ""
    except Exception:
        return ""


def _write_marked_source(book_id: str, mod_dir: str, nur_text: bool = False) -> str:
    """Schreibt aus den Kapitel-Checkpoints EINE kanonische Volltextdatei
    raw_modernized.txt mit ###TITLE###/###AUTHOR###/###CHAPTER###-Marken.
    Diese Datei ist die EINE englische Wahrheit -- EPUB UND Tagger (Audio)
    lesen perspektivisch daraus. Robust auch bei Resume (liest von Platte)."""
    M = config.MARKERS
    files = [f for f in os.listdir(mod_dir) if re.fullmatch(r"chapter-\d+\.json", f)]
    files.sort(key=lambda f: int(re.search(r"\d+", f).group()))

    book_title  = _book_title(book_id)
    author_name = _author_name(book_id)
    lines = [f'{M["title"]} {book_title}',
             f'{M["author"]} {author_name}', ""]
    for idx, f in enumerate(files):
        d = json.load(open(os.path.join(mod_dir, f), encoding="utf-8"))
        paras = [p for p in d.get("paragraphs", []) if p and p != "\u2014\u2014HR\u2014\u2014"]
        if idx == 0:
            before = len(paras)
            paras = epub.strip_leading_front_matter(paras, book_title, author_name)
            if len(paras) < before:
                print(f"[120] Front-Matter entfernt: {before - len(paras)} "
                      f"Vorspann-Absaetze (Titelblock) aus Kapitel 1.")
        if idx == len(files) - 1:
            paras = epub.strip_trailing_end_marker(paras)
        lines.append(f'{M["chapter"]} {d.get("title", "").strip()}')
        lines.append("")
        for p in paras:
            lines.append(p)
            lines.append("")
    if nur_text:
        return "\n".join(lines).strip() + "\n"
    out_path = os.path.join(config.book_dir(book_id), "raw_modernized.txt")
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    os.replace(tmp, out_path)
    return out_path


if __name__ == "__main__":
    sys.exit(main())
