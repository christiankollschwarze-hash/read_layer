"""READ LAYER — Satzpaket fuer Single-Speaker-Vertonung mit Chatterbox bauen (lokal, keine API).
Aufruf:  python tools/tts_paket.py <book_id> [en|de] [--ref=<stimme_archiv_id>] [--prosodie] [--lora=<name>|--lora=aus] [--lexikon-pflicht]
LoRA (18.10.2026): Standard aus book.json "tts_lora"; schreibt lora, ms_je_zeichen, tempo in jobs.json.
Ergebnis: gpu_tts/<book_id>_<lg>/jobs.json (+ ref.wav, falls --ref; sonst Chatterbox-Standardstimme)

Je Job: id, kap, text (+ ex/cfg mit --prosodie). Der TTS-Text bekommt das freigegebene Aussprache-Lexikon
(work/aussprache_<lg>.json, 17.10.2026) - Eigennamen im Originalklang; Text/EPUB bleiben unveraendert.
--prosodie: Regler je Satz aus work/prosodie_<lg>.json (tools/prosodie_marken.py) -> ex (Ausdruck), cfg (Ruhe/Tempo).
Ich-Erzaehler je Kapitel (22.10.2026, AP4 Spiegelschwestern): hat casting.json plan.erzaehler_je_kapitel und ist <lg> eine
Hoerspiel-Sprache (casting.json hoerspiel_sprachen, Standard = Originalsprache), bekommt jeder Satz die Stimme des
Kapitel-Erzaehlers (refs + stil je Satz, Mechanik wie --stil-refs). Gilt auch fuer cb_neu (ruft schreiben()).
"""
import glob, json, os, re, shutil, sys

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPEN = {"h", "s", "dl", "qt", "ep", "vs"}   # 22.10.2026: ep (Motto/Kopfzeile) wie Gemini mitsprechen

# Prosodie-Klassen -> Chatterbox-Regler (17.10.2026, Startwerte; Mitte = bisheriger Standard 0,5/0,5)
STILE = {
    "ruhig":    {"ex": 0.40, "cfg": 0.50},   # Erzaehlung, Beschreibung
    "lebhaft":  {"ex": 0.60, "cfg": 0.45},   # bewegte Handlung, lebendige Rede
    "gespannt": {"ex": 0.55, "cfg": 0.35},   # Spannung, Andeutung -> etwas langsamer
    "ausruf":   {"ex": 0.75, "cfg": 0.40},   # Ausruf, Aufregung, Zorn
    "leise":    {"ex": 0.35, "cfg": 0.35},   # Fluestern, Trauer, Zaertlichkeit
}


# LoRA-Adapter (18.10.2026): Pruef-Erwartung roh (s/Zeichen) und Tempo-Ausgleich fuer dasselbe Endtempo wie
# Grundmodell mit 0,91. Gemessen Peter Pan c001 (grossmutter_a): Grundmodell 0,051 roh, ramona_v1 ~17 % schneller.
LORA = {"ramona_v1": {"ms_je_zeichen": 0.043, "tempo": "0.76"},
        "mix_v1":    {"ms_je_zeichen": 0.0425, "tempo": "0.76"}}   # 18.10.: Standard DE (config.TTS_LORA)
TEMPO_STANDARD = "0.91"


def lora_extra(werk, lora=None, lg=None):
    """jobs.json-Felder fuer den Adapter: --lora=<name> | book.json tts_lora | config.TTS_LORA[lg] | keiner ("aus")."""
    if lora is None:
        bp = os.path.join(werk, "book.json")
        lora = json.load(open(bp, encoding="utf-8")).get("tts_lora") if os.path.exists(bp) else None
    if lora is None and lg:
        sys.path.insert(0, HIER)
        from config import config
        lora = getattr(config, "TTS_LORA", {}).get(lg)
    if not lora or lora == "aus":
        return {"tempo": TEMPO_STANDARD}
    if lora not in LORA:
        sys.exit(f"[tts_paket] LoRA {lora} unbekannt ({sorted(LORA)})")
    print(f"[tts_paket] LoRA {lora} (Tempo {LORA[lora]['tempo']})")
    return {"lora": lora, **LORA[lora]}


def lexikon(werk, lg, erzwingen=False):
    lp = os.path.join(werk, "work", f"aussprache_{lg}.json")
    if not os.path.exists(lp):
        return {}
    lex = json.load(open(lp, encoding="utf-8"))
    if not (lex.get("freigegeben") or erzwingen):
        print("[tts_paket] Aussprache-Lexikon vorhanden, aber nicht freigegeben -> nicht angewendet")
        return {}
    return {k: v for k, v in lex.get("ersatz", {}).items() if v and v != k}


def lex_text(text, ers):
    for k in sorted(ers, key=len, reverse=True):
        text = re.sub(r"(?<![\w])" + re.escape(k) + r"(?![\w])", ers[k], text)
    return text


def prosodie(werk, lg):
    p = os.path.join(werk, "work", f"prosodie_{lg}.json")
    return json.load(open(p, encoding="utf-8")).get("stil", {}) if os.path.exists(p) else {}


def jobs_bauen(book_id, lg, tags=None, mit_prosodie=False, lex_erzwingen=False):
    sys.path.insert(0, HIER)
    from config import config
    werk = config.book_dir(book_id)   # auch private Uploads (users/<uid>/works/...)
    d = json.load(open(os.path.join(werk, "work", "400_regie.json"), encoding="utf-8"))["content"]
    jobs = [{"id": t, "kap": t[:4], "text": e[lg].strip()} for t, e in d.items()
            if e.get("type") in TYPEN and (e.get(lg) or "").strip() and (tags is None or t in tags)]
    ers = lexikon(werk, lg, lex_erzwingen)
    from pipeline.sprechtext import sprechtext      # 18.10.2026: Sprechtext-Regeln (z. B. roemische Kapitelnummern)
    for j in jobs:
        j["text"] = lex_text(sprechtext(j["text"], lg, d[j["id"]].get("type")), ers)
    if ers:
        print(f"[tts_paket] Aussprache-Lexikon: {len(ers)} Eintraege angewendet")
    if mit_prosodie:
        st = prosodie(werk, lg)
        n = 0
        for j in jobs:
            s = st.get(j["id"])
            if s in STILE:
                j.update(STILE[s], stil=s)
                n += 1
        print(f"[tts_paket] Prosodie: {n}/{len(jobs)} Saetze mit Stil" if st else "[tts_paket] Prosodie: work/prosodie_%s.json fehlt" % lg)
    return werk, jobs


def erzaehler_refs(book_id, lg, jobs, ziel):
    """Kapitel-Erzaehler -> Archivstimme je Satz (job["stil"] = Stimme, refs[Stimme] = ref_<stimme>.wav). {} wenn nicht zutreffend."""
    sys.path.insert(0, HIER)
    from config import config
    werk = config.book_dir(book_id)
    cp = os.path.join(werk, "work", "casting.json")
    if not os.path.exists(cp):
        return {}
    cast = json.load(open(cp, encoding="utf-8"))
    plan = cast.get("plan") or {}
    erz = plan.get("erzaehler_je_kapitel") or {}
    sprachen = cast.get("hoerspiel_sprachen") or [config.werk_sprachen(book_id)[0]]
    if not erz or lg not in sprachen:
        return {}
    stimme = {e["figur"]: e.get("stimme") for e in plan.get("ensemble", []) if e.get("stimme")}
    if not any(j["id"][:4] in erz for j in jobs):      # z. B. Teaser-Paket: keine Werk-Saetze
        return {}
    refs = {}
    for fig in sorted(set(erz.values())):
        st = stimme.get(fig)
        q = os.path.join(HIER, "stimmen_archiv", st or "-", f"muster_{lg}.wav")
        if not st or not os.path.exists(q):
            sys.exit(f"[tts_paket] Erzaehler {fig}: Stimme {st} ohne muster_{lg}.wav -> Abbruch")
        shutil.copy(q, os.path.join(ziel, f"ref_{st}.wav"))
        refs[st] = f"ref_{st}.wav"
    n = {}
    for j in jobs:
        fig = erz.get(j["id"][:4])
        if fig:
            j["stil"] = stimme[fig]
            n[fig] = n.get(fig, 0) + 1
    print("[tts_paket] Erzaehler je Kapitel: " + ", ".join(f"{f} ({stimme[f]}) {z}" for f, z in n.items()))
    return refs


def schreiben(book_id, lg, jobs, ref=None, ref_wav=None, name=None, extra=None):
    ziel = os.path.join(HIER, "gpu_tts", name or f"{book_id}_{lg}")
    os.makedirs(ziel, exist_ok=True)
    extra = dict(extra or {})
    if not extra.get("refs"):
        r = erzaehler_refs(book_id, lg, jobs, ziel)
        if r:
            extra["refs"] = r
    if ref == "chatterbox-standard":       # 22.10.2026: cb_neu reicht den Paket-Wert durch -> Standardstimme, keine Datei
        ref = None
    if ref_wav:
        shutil.copy(ref_wav, os.path.join(ziel, "ref.wav"))
    elif ref:
        shutil.copy(os.path.join(HIER, "stimmen_archiv", ref, f"muster_{lg}.wav"), os.path.join(ziel, "ref.wav"))
    daten = {"werk": book_id, "lang": lg, "ref": ref or "chatterbox-standard", "jobs": jobs}
    daten.update(extra)
    json.dump(daten, open(os.path.join(ziel, "jobs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    kap = sorted({j["kap"] for j in jobs})
    zeichen = sum(len(j["text"]) for j in jobs)
    print(f"[tts_paket] {len(jobs)} Saetze, {len(kap)} Kapitel, {zeichen:,} Zeichen (~{zeichen / 15 / 3600:.1f} h, "
          f"~{zeichen / 50000 * 0.25:.2f} $) -> {ziel}")
    return ziel


def stil_refs(jobs, werk, lg, stimme, ziel):
    """--stil-refs (17.10.2026): je Satz die Stimmungs-Referenz derselben Archivstimme
    (stimmen_archiv/<stimme>/stil_<stil>_<lg>.wav, tools/stimmungs_referenzen.py). Regler bleiben Standard."""
    st = prosodie(werk, lg)
    refs = {}
    for stil in STILE:
        q = os.path.join(HIER, "stimmen_archiv", stimme, f"stil_{stil}_{lg}.wav")
        if os.path.exists(q):
            shutil.copy(q, os.path.join(ziel, f"ref_{stil}.wav"))
            refs[stil] = f"ref_{stil}.wav"
    for j in jobs:
        if st.get(j["id"]) in refs:
            j["stil"] = st[j["id"]]
    print(f"[tts_paket] Stimmungs-Referenzen {sorted(refs)}: {sum(1 for j in jobs if 'stil' in j)}/{len(jobs)} Saetze")
    return refs


def main(book_id, lg="en", ref=None, mit_prosodie=False, name=None, stil_stimme=None, zeichen=False, lora=None,
         lex_pflicht=False):
    werk, jobs = jobs_bauen(book_id, lg, mit_prosodie=mit_prosodie)
    lp = os.path.join(werk, "work", f"aussprache_{lg}.json")
    if lex_pflicht and os.path.exists(lp) and not lexikon(werk, lg):
        sys.exit("[tts_paket] Aussprache-Lexikon nicht freigegeben -> Abbruch (--lexikon-pflicht)")
    extra = {"zeichen": "erhalten"} if zeichen else {}     # --zeichen: Pausen-/Spannungszeichen erhalten (cb_batch.sprech_norm)
    extra.update(lora_extra(werk, lora, lg))
    if stil_stimme:
        ziel = os.path.join(HIER, "gpu_tts", name or f"{book_id}_{lg}")
        os.makedirs(ziel, exist_ok=True)
        extra["refs"] = stil_refs(jobs, werk, lg, stil_stimme, ziel)
    schreiben(book_id, lg, jobs, ref=ref, name=name, extra=extra)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    arg = lambda k: next((x.split("=", 1)[1] for x in sys.argv if x.startswith(f"--{k}=")), None)
    main(a[0], a[1] if len(a) > 1 else "en", arg("ref"), "--prosodie" in sys.argv, arg("name"), arg("stil-refs"), "--zeichen" in sys.argv,
         arg("lora"), "--lexikon-pflicht" in sys.argv)
