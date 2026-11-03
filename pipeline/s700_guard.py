"""STAGE 700 — Auslieferungs-Vertrag (Umbau Phase 2, GATE_KATALOG.md Zeile 700, 03.11.2026)
Funktion:      Vertrag vor jeder Auslieferung (710): je bestelltem Produkt x Sprache x Kanal muessen alle
               Pflicht-Artefakte vorhanden, ihr Gate frei und ihr Hash aktuell sein. Keine API, keine Kosten.
Wirkungsweise: Einmal je Werk ueber alle Produkte der Bestellung (book.json). Je Produkt-Scope
               "<lg>:<inhalt>[-<stufe>]:<kanal>" (status.json teile) ein Gate:
                 Text           Text 330 (ohne Uebersetzung: Gate 190), Anker 340 (Zielsprache, TAELLA)
                 Audio          Endfassung 530 (audio_final bzw. hoerspiel_final, Datei aktuell) + Wortzeiten 520
                                (beide Spuren, TAELLA)
                 Klappentext 600, Cover-Variante 615 (text / audio / quadrat), Teaser 640 (TAELLA),
                 ePub 620/630 (text / audio), Hoerbuch 650 (Profil epub / extern)
               Hash aktuell = Artefakt unveraendert seit dem Gate der Stage (Ausgabe-Hash bzw. Datei-Hash wie in
               der Stage berechnet) und Gate nicht aelter als das Gate seiner Eingangs-Stage.
               Werkweit: ID-Deckung ueber alle bestellten Sprachen (Quelle 330), Mock = 0 (Live-Lauf).
               Hoerbuch Premium / Hoerspiel (Gemini-Audio) nur an Kanaele aus config.GEMINI_AUDIO_KANAELE.
               Alles gruen -> auto; Mandant verlag -> immer Mensch (Endabnahme, gilt bei gleichem ausgabe_hash);
               sonst Stopp mit Ruecksprung auf die Stage des Befunds. Regler: Produkt/Kanal einzeln zurueckhalten
               (Teil 'entfaellt', Rest wird ausgeliefert); sonst nur Admin-Override (pipeline.status --override).
Komponenten:   pipeline/s700_guard.py
Eingang:       book.json (Bestellung, quellsprache, Mandant), status.json (Gates aller bestellten Stages), Manifeste/
               Ausgaben work/330, 340, 520, 525, 530_pruefung_<lg>, 600, 615_cover_final, 620_epub, 640_teaser,
               650_hoerbuch_<lg>, 400_regie (Hoerreihenfolge), Dateien unter fassungen/<lg>/.
Ausgabe:       work/700_guard.json (je Produkt-Scope: Artefakte mit Stage, Datei, Gate, Hash, Befund, Ruecksprung;
               liefern ja/nein), Gate je Scope in status.json; Regler work/700_entscheidungen.json.
Abnehmer:      s710 Auslieferung (startet nur bei freiem Gate 700, liefert nur lieferbar()).
Aufruf:        python -m pipeline.s700_guard <werk> [--trocken] [--zurueckhalten SCOPE --grund TEXT] [--liefern SCOPE]
Kosten:        0 $ (CPU).
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, manifest, mock, status

STAGE = "700"
VERSION = 1
AUDIO = ("hoerbuch", "hoerspiel")


def gemini_kanaele():
    return tuple(getattr(config, "GEMINI_AUDIO_KANAELE", ("taella",)))


def pfad(werk):
    return config.work_path(werk, "700_guard")


def entscheidungen_pfad(werk):
    return config.work_path(werk, "700_entscheidungen")


def _kt_saetze(blurb, lg):
    """Klappentext-Saetze einer Sprache. 600 schreibt blurb {koeder, einordnung, autor: [{lg: satz}]};
    aeltere Ablagen {lg: text} gelten weiter."""
    if isinstance(blurb.get(lg), str):
        return [blurb[lg]]
    return [str(s.get(lg)).strip() for blk in ("koeder", "einordnung", "autor")
            for s in (blurb.get(blk) or []) if isinstance(s, dict) and s.get(lg)]


def _kt_text(blurb, lg):
    return " ".join(_kt_saetze(blurb, lg))


def _json(p, leer=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def entscheidungen(werk):
    return _json(entscheidungen_pfad(werk), {}) or {}


def scope_name(p, kanal):
    return f"{p['sprache']}:{p['inhalt']}{'-' + p['stufe'] if p['stufe'] else ''}:{kanal}"


def scopes(b):
    """[(scope, produkt, kanal)] laut Bestellung, Reihenfolge der Bestellung."""
    out, gesehen = [], set()
    for p in b.produkte:
        for k in p["kanaele"]:
            s = scope_name(p, k)
            if s not in gesehen:
                gesehen.add(s)
                out.append((s, p, k))
    return out


# ------------------------------------------------------------------ Artefakt-Pruefung
class Pruefer:
    """Prueft Artefakte einmal je Werk (Cache), Ergebnis je Artefakt:
    {stage, scope, name, datei, gate, hash, befunde[], mock, ruecksprung}."""

    def __init__(self, werk, b, laeuft):
        self.werk, self.b, self.laeuft = werk, b, set(laeuft)
        self.d = status.laden(werk)
        self.src = b.quellsprache
        self.cache, self.daten = {}, {}

    # ---- Hilfen
    def _lade(self, name):
        if name not in self.daten:
            self.daten[name] = _json(config.work_path(self.werk, name))
        return self.daten[name]

    def _teil(self, stage, scope=None):
        st = self.d["stages"].get(stage) or {}
        return st if scope is None else (st.get("teile") or {}).get(str(scope)) or {}

    def _rel(self, p):
        try:
            return os.path.relpath(p, config.book_dir(self.werk)).replace("\\", "/")
        except ValueError:
            return p

    def _abs(self, rel):
        return rel if os.path.isabs(rel) else os.path.join(config.book_dir(self.werk), rel)

    def _art(self, stage, name, scope=None, datei=None):
        return {"stage": stage, "scope": scope, "name": name, "datei": datei, "gate": None, "hash": None,
                "befunde": [], "mock": 0, "ruecksprung": stage}

    def _gate(self, a, nach=()):
        """Gate frei, Mock-Lauf, Frische gegen Eingangs-Gates."""
        stage, scope = a["stage"], a["scope"]
        z = status.zustand(self.werk, stage, scope=scope, d=self.d)
        a["gate"] = z
        if z not in status.FREI:
            a["befunde"].append(f"Gate {stage}{'/' + scope if scope else ''} nicht frei ({z})")
        t = self._teil(stage, scope)
        if not mock.aktiv() and (t.get("metriken") or {}).get("modus") == "mock":
            a["mock"] += 1
            a["befunde"].append(f"Gate {stage}{'/' + scope if scope else ''} im Mock-Lauf erzeugt")
        selbst = (t.get("gate") or {}).get("wann")
        for vs, vscope in nach:
            if vs not in self.laeuft:
                continue
            vw = (self._teil(vs, vscope).get("gate") or {}).get("wann")
            if selbst and vw and vw > selbst:
                a["befunde"].append(f"veraltet: Gate {vs}{'/' + vscope if vscope else ''} neuer ({vw[:16]}) "
                                    f"als Gate {stage} ({selbst[:16]})")
        return a

    def _status_hash(self, a, h, feld="ausgabe_hash"):
        soll = (self._teil(a["stage"], a["scope"]).get("metriken") or {}).get(feld)
        if soll is None:
            a["befunde"].append(f"Gate {a['stage']} ohne {feld} (Lauf vor Umbau) – Stage neu ausfuehren")
        elif soll != h:
            a["befunde"].append(f"{a['name']}: Inhalt geaendert seit Gate {a['stage']} ({feld})")

    def pruefe(self, key, fn, *args):
        if key not in self.cache:
            self.cache[key] = fn(*args)
        return self.cache[key]

    # ---- Text
    def text(self, lg):
        if "330" not in self.laeuft:          # nur Ausgangssprache: Text aus 190
            a = self._art("190", "text_190", datei="work/modernized")
            if not os.path.isdir(os.path.join(config.work_dir(self.werk), "modernized")):
                a["befunde"].append("work/modernized fehlt")
            return self._gate(a)
        return self.pruefe(("330",), self._text330)

    def _text330(self):
        a = self._art("330", "text_330", datei="work/330_rueckuebersetzung.json")
        data = self._lade("330_rueckuebersetzung")
        if not data:
            a["befunde"].append("330_rueckuebersetzung.json fehlt")
            return self._gate(a)
        c = data.get("content") or {}
        ziele = [z for z in self.b.zielsprachen if z != self.src]
        ids = [t for t, e in c.items() if isinstance(e, dict)]
        flags = ((data.get("meta") or {}).get("quality_report") or {}).get("flagged")
        h = manifest.hash_obj({lg: {t: (c[t] or {}).get(lg) for t in ids} for lg in ziele} | {"_flags": flags})
        a["hash"] = h
        self._status_hash(a, h)
        if mock.ist_obj(c):
            a["mock"] += 1
            if not mock.aktiv():
                a["befunde"].append("Mock-Text in 330")
        return self._gate(a, [("320", None)])

    def anker(self, lg):
        return self.pruefe(("340",), self._anker340)

    def _anker340(self):
        a = self._art("340", "anker_340", datei="work/340_wortalignment.json")
        data = self._lade("340_wortalignment")
        if not data:
            a["befunde"].append("340_wortalignment.json fehlt")
            return self._gate(a)
        c = data.get("content") or {}
        ziele = [lg for lg in self.b.zielsprachen if lg != self.src and self.b.hat(sprache=lg, kanal="taella")]
        ids = [t for t, e in c.items() if isinstance(e, dict)]
        for lg in ziele:
            if not any((c[t] or {}).get(f"align_{lg}") for t in ids):
                a["befunde"].append(f"keine Anker align_{lg}")
        h = manifest.hash_obj({lg: {t: (c[t] or {}).get(f"align_{lg}") for t in ids} for lg in ziele})
        a["hash"] = h
        self._status_hash(a, h)
        # Text in 340 = Text 330 (sonst 340 auf altem Stand)
        c330 = (self._lade("330_rueckuebersetzung") or {}).get("content") or {}
        abw = [t for t in ids if t in c330 and any((c[t] or {}).get(lg) != (c330[t] or {}).get(lg) for lg in ziele)]
        if abw:
            a["befunde"].append(f"Text in 340 weicht von 330 ab ({len(abw)} Saetze, z. B. {abw[0]})")
        return self._gate(a, [("330", None)])

    # ---- Audio
    def endfassung(self, lg, spur):
        return self.pruefe(("530", lg, spur), self._end530, lg, spur)

    def _end530(self, lg, spur):
        a = self._art("530", f"endfassung_{spur}_{lg}", datei=f"work/530_pruefung_{lg}.json")
        if not os.path.exists(config.work_path(self.werk, f"530_pruefung_{lg}")):
            a["befunde"].append(f"530_pruefung_{lg}.json fehlt")
            return self._gate(a)
        try:
            m = manifest.Manifest(self.werk, f"530_pruefung_{lg}", stage="530")
        except RuntimeError as e:
            a["befunde"].append(str(e))
            return self._gate(a)
        if spur == "hoerbuch":
            from pipeline import s500_vertonung_gemini as s500
            d400 = self._lade("400_regie")
            if not d400:
                a["befunde"].append("400_regie.json fehlt")
                a["ruecksprung"] = "400"
                return self._gate(a)
            keys = [f"hoerbuch/{u['id']}" for u in s500.einheiten(d400, lg)[0]]
        else:
            keys = [k for k in m.eintraege if k.startswith("hoerspiel/")]
            if not keys:
                a["befunde"].append(f"keine Hoerspiel-Endfassung {lg}")
        fehlt, mocks, hs = [], [], {}
        for k in keys:
            e = m.get(k)
            if not e or not m.datei_aktuell(k):
                fehlt.append(k.split("/", 1)[1])
                continue
            hs[k] = e.get("datei_hash")
            if mock.ist_datei(m._abs(e["datei"])):
                mocks.append(k)
        if fehlt:
            a["befunde"].append(f"Endfassung {spur} {lg}: {len(fehlt)}/{len(keys)} fehlen/veraendert "
                                f"(z. B. {', '.join(fehlt[:3])})")
        a["mock"] += len(mocks)
        if mocks and not mock.aktiv():
            a["befunde"].append(f"Mock-Audio {len(mocks)} (z. B. {mocks[0]})")
            a["ruecksprung"] = "500"
        a["hash"] = manifest.hash_obj(hs)
        nach = [("400", None), ("500", None)] + ([("510", None)] if spur == "hoerspiel" else [])
        return self._gate(a, nach)

    def wortzeiten(self, lg, spur):
        a = self._art("520", f"wortzeiten_{spur}_{lg}")
        from pipeline import s520_wortzeiten as s520
        p = s520.pfad(self.werk, lg, spur)
        a["datei"] = self._rel(p)
        d = _json(p)
        if not d or not d.get("tags"):
            a["befunde"].append(f"Wortzeiten {spur} {lg} fehlen")
        h = self.pruefe(("520",), self._hash520)
        a["hash"] = manifest.hash_obj((d or {}).get("tags"))
        if h is None:
            a["befunde"].append("Wortzeiten 520 unvollstaendig")
        else:
            self._status_hash(a, h)
        return self._gate(a, [("530", None), ("340", None)])

    def _hash520(self):
        from pipeline import s520_wortzeiten as s520
        aus = {}
        for lg, spuren in s520._spuren(self.b).items():
            for spur in spuren:
                d = _json(s520.pfad(self.werk, lg, spur))
                if d is None:
                    return None
                aus[f"{lg}/{spur}"] = d.get("tags")
        br = self._lade("525_wortbruecke")
        if "340" in self.laeuft and br is not None:
            aus["525"] = {lg: x.get("tags") for lg, x in (br.get("je_ziel") or {}).items()}
        return manifest.hash_obj(aus)

    # ---- Begleitmaterial
    def klappentext(self, lg):
        return self.pruefe(("600", lg), self._kt600, lg)

    def _kt600(self, lg):
        a = self._art("600", f"klappentext_{lg}", datei="work/600_klappentext.json")
        d = self._lade("600_klappentext")
        if not d:
            a["befunde"].append("600_klappentext.json fehlt")
            return self._gate(a)
        blurb, meta = d.get("blurb") or {}, d.get("meta") or {}
        if not _kt_text(blurb, lg):
            a["befunde"].append(f"Klappentext {lg} fehlt")
        h = manifest.hash_obj({"b": blurb, "v": d.get("vermerke"),
                               "m": {k: meta.get(k) for k in ("genre", "hauptfigur_geschlecht", "ton")}})
        a["hash"] = h
        self._status_hash(a, h)
        if mock.ist_obj(_kt_saetze(blurb, lg)):
            a["mock"] += 1
            if not mock.aktiv():
                a["befunde"].append(f"Mock-Klappentext {lg}")
        return self._gate(a, [("330", None), ("190", None)])

    def cover(self, lg, var):
        return self.pruefe(("615", lg, var), self._cover615, lg, var)

    def _cover615(self, lg, var):
        sc = f"{lg}:{var}"
        a = self._art("615", f"cover_{var}_{lg}", scope=sc)
        e = ((self._lade("615_cover_final") or {}).get("varianten") or {}).get(sc)
        if not e:
            a["befunde"].append(f"Cover {sc} nicht im Manifest 615")
            return self._gate(a)
        p = self._abs(e["datei"])
        a["datei"] = self._rel(p)
        if not os.path.exists(p):
            a["befunde"].append(f"Cover-Datei fehlt: {a['datei']}")
            return self._gate(a)
        with open(p, "rb") as f:
            data = f.read()
        h = hashlib.sha256(data).hexdigest()
        a["hash"] = h
        if h != e.get("ausgabe_hash"):
            a["befunde"].append(f"Cover {sc} veraendert seit 615")
        self._status_hash(a, h)
        if mock.ist_bytes(data):
            a["mock"] += 1
        nach = [("610", None), ("600", None)] + ([("410", None)] if var != "text" else [])
        return self._gate(a, nach)

    def teaser(self, lg):
        return self.pruefe(("640", lg), self._teaser640, lg)

    def _teaser640(self, lg):
        a = self._art("640", f"teaser_{lg}", scope=lg, datei="work/640_teaser.json")
        if not os.path.exists(config.work_path(self.werk, "640_teaser")):
            a["befunde"].append("640_teaser.json fehlt")
            return self._gate(a)
        try:
            m = manifest.Manifest(self.werk, "640_teaser", stage="640")
        except RuntimeError as e:
            a["befunde"].append(str(e))
            return self._gate(a)
        keys = sorted(k for k in m.eintraege if k.startswith(f"{lg}/"))
        if not keys:
            a["befunde"].append(f"keine Teaser {lg}")
        bj = os.path.join(config.book_dir(self.werk), "fassungen", lg, "blurb", "text", "blurb.json")
        if not os.path.exists(bj):
            a["befunde"].append(f"blurb.json {lg} fehlt")
        alt = [k for k in keys if not m.datei_aktuell(k)]
        if alt:
            a["befunde"].append(f"Teaser-Audio fehlt/veraendert: {', '.join(alt[:3])}")
        mocks = [k for k in keys if k not in alt and mock.ist_datei(m._abs(m.get(k)["datei"]))]
        a["mock"] += len(mocks)
        if mocks and not mock.aktiv():
            a["befunde"].append(f"Mock-Teaser {len(mocks)}")
        h = manifest.hash_obj(sorted((k.split("/", 1)[1], m.get(k).get("datei_hash")) for k in keys))
        a["hash"] = h
        self._status_hash(a, h)
        return self._gate(a, [("600", None), ("410", None)])

    def epub(self, lg, var):
        return self.pruefe(("620", lg, var), self._epub620, lg, var)

    def _epub620(self, lg, var):
        stage = "620" if lg == self.src else "630"
        sc = f"{lg}:{var}"
        a = self._art(stage, f"epub_{var}_{lg}", scope=sc)
        e = ((self._lade("620_epub") or {}).get("varianten") or {}).get(sc)
        if not e:
            a["befunde"].append(f"ePub {sc} nicht im Manifest 620")
            return self._gate(a)
        p = self._abs(e["datei"])
        a["datei"] = self._rel(p)
        if not os.path.exists(p):
            a["befunde"].append(f"ePub-Datei fehlt: {a['datei']}")
            return self._gate(a)
        h = manifest.hash_datei(p)
        a["hash"] = h
        if h != e.get("ausgabe_hash"):
            a["befunde"].append(f"ePub {sc} veraendert seit {stage}")
        self._status_hash(a, e.get("eingang_hash"), feld="eingang_hash")
        nach = [("615", f"{lg}:{'audio' if var == 'audio' else 'text'}"), ("600", None)]
        nach += [("650", lg)] if var == "audio" else []
        nach += [("330", None)] if stage == "630" else [("190", None)]
        return self._gate(a, nach)

    def hoerbuch(self, lg, profil):
        a = self._art("650", f"hoerbuch_{profil}_{lg}", scope=lg, datei=f"work/650_hoerbuch_{lg}.json")
        d = self.pruefe(("650", lg), _json, config.work_path(self.werk, f"650_hoerbuch_{lg}"))
        if not d:
            a["befunde"].append(f"650_hoerbuch_{lg}.json fehlt")
            return self._gate(a)
        prof = d.get("profile") or {}
        kap = (prof.get(profil) or {}).get("kapitel") or []
        if not kap:
            a["befunde"].append(f"Hoerbuch {lg} ohne Profil {profil}")
        geaendert, mocks = [], 0
        for e in kap:
            p = self._abs(e.get("datei") or "")
            if not os.path.exists(p) or manifest.hash_datei(p) != e.get("datei_hash"):
                geaendert.append(e.get("kapitel"))
            elif mock.ist_datei(p):
                mocks += 1
        m4b = (prof.get("extern") or {}).get("m4b") if profil == "extern" else None
        if m4b and not os.path.exists(self._abs(m4b.get("datei") or "")):
            geaendert.append("m4b")
        if geaendert:
            a["befunde"].append(f"Kapiteldateien fehlen/veraendert: {', '.join(map(str, geaendert[:4]))}")
        a["mock"] += mocks
        h = manifest.hash_obj({p: [e["datei_hash"] for e in (x.get("kapitel") or [])] for p, x in prof.items()}
                              | {"m4b": ((prof.get("extern") or {}).get("m4b") or {}).get("eingang_hash")})
        a["hash"] = h
        self._status_hash(a, h)
        nach = [("530", None), ("400", None)] + ([("615", f"{lg}:quadrat")] if profil == "extern" else [])
        return self._gate(a, nach)

    # ---- Werk
    def id_deckung(self):
        """{ok, quelle, ids, fehlt {lg: [ids]}}; Quelle 330 ueber alle bestellten Sprachen."""
        if "330" not in self.laeuft:
            return {"ok": True, "quelle": None, "ids": None, "fehlt": {},
                    "hinweis": "keine Uebersetzung bestellt (nur Ausgangssprache)"}
        c = (self._lade("330_rueckuebersetzung") or {}).get("content") or {}
        ids = [t for t, e in c.items() if isinstance(e, dict) and e.get("type") not in config.NO_AUDIO_TYPES
               and str(e.get(self.src) or "").strip()]
        fehlt = {}
        for lg in self.b.sprachen:
            f = [t for t in ids if not str(c[t].get(lg) or "").strip()]
            if f:
                fehlt[lg] = f
        return {"ok": bool(ids) and not fehlt, "quelle": "330", "ids": len(ids), "fehlt": fehlt}


# ------------------------------------------------------------------ Vertrag je Produkt
def artefakte(pr, p, kanal):
    """Pflicht-Artefakte eines Produkts in einem Kanal -> Liste von Pruefergebnissen."""
    lg, inh, stufe = p["sprache"], p["inhalt"], p["stufe"]
    b = pr.b
    out = [pr.text(lg)]
    ziel = lg != b.quellsprache
    if kanal == "taella":
        if ziel:
            out.append(pr.anker(lg))
        if inh in AUDIO:
            out += [pr.endfassung(lg, "hoerbuch"), pr.wortzeiten(lg, "hoerbuch")]
            if inh == "hoerspiel":
                out += [pr.endfassung(lg, "hoerspiel"), pr.wortzeiten(lg, "hoerspiel")]
        out += [pr.klappentext(lg), pr.cover(lg, "audio" if inh in AUDIO else "text"), pr.teaser(lg)]
    elif kanal == "epub":
        if inh == "text":
            out += [pr.klappentext(lg), pr.cover(lg, "text"), pr.epub(lg, "text")]
        else:
            out += [pr.endfassung(lg, "hoerbuch"), pr.hoerbuch(lg, "epub"), pr.klappentext(lg),
                    pr.cover(lg, "audio"), pr.epub(lg, "audio")]
    elif kanal == "extern":
        out += [pr.endfassung(lg, "hoerbuch"), pr.cover(lg, "quadrat")]
        if stufe == "basic":
            out.append(pr.hoerbuch(lg, "extern"))
    return out


def run(werk, wer=None, trocken=False):
    """-> Liste der Gates (je Produkt-Scope)."""
    from pipeline import kette
    wer = wer or "pipeline"
    b = bestellung.lesen(werk)
    fehler = b.fehler()
    if fehler:
        g = gate.Gate(werk, STAGE, ruecksprung="095", wer=wer)
        g.pflicht("bestellung", False, ruecksprung="095", text="Bestellung ungueltig: " + "; ".join(fehler))
        g.entscheide(schreiben=not trocken)
        return [g]
    laeuft = kette.bedarf(b)
    if not trocken:
        status.start(werk, STAGE, wer=wer)
    pr = Pruefer(werk, b, laeuft)
    idd = pr.id_deckung()
    ents = entscheidungen(werk)
    halt = ents.get("zurueckhalten") or {}
    verlag = b.mandant_art == "verlag"
    st_alt = (pr.d["stages"].get(STAGE) or {}).get("teile") or {}
    gates, produkte = [], {}

    for sc, p, kanal in scopes(b):
        g = gate.Gate(werk, STAGE, scope=sc, ruecksprung="700", wer=wer)
        arts = artefakte(pr, p, kanal)
        if p["inhalt"] in AUDIO and p["stufe"] in ("premium", "drama"):
            g.pflicht("gemini_kanal", kanal in gemini_kanaele(), ruecksprung="095",
                      text=f"Gemini-Audio ({p['inhalt']} {p['stufe']}) im Kanal {kanal} "
                           f"{'zugelassen' if kanal in gemini_kanaele() else 'nicht zugelassen'} "
                           f"(config.GEMINI_AUDIO_KANAELE {list(gemini_kanaele())})")
        if idd["quelle"]:
            f = idd["fehlt"]
            g.pflicht("id_deckung", idd["ok"], wert=sum(len(v) for v in f.values()), ruecksprung="310",
                      text=f"ID-Deckung {idd['ids']} Knoten ueber {'/'.join(b.sprachen)} (Quelle 330)"
                      + "".join(f"; {lg} fehlt {len(v)} ({', '.join(v[:3])})" for lg, v in f.items()))
        for a in arts:
            g.pflicht(a["name"], not a["befunde"], ruecksprung=a["ruecksprung"],
                      text=f"{a['stage']} {a['name']}: " + ("; ".join(a["befunde"]) or f"ok ({a['gate']})"))
        n_mock = sum(a["mock"] for a in arts)
        g.mock(n_mock, [a["name"] for a in arts if a["mock"]][:3], ruecksprung="700")
        ausgabe_hash = manifest.hash_obj({f"{a['stage']}/{a['name']}": a["hash"] for a in arts})
        g.metrik("artefakte", len(arts))
        g.metrik("ausgabe_hash", ausgabe_hash)
        alt = st_alt.get(sc) or {}
        mensch_gilt = alt.get("zustand") == "frei" and (alt.get("gate") or {}).get("ergebnis") == "mensch" \
            and (alt.get("metriken") or {}).get("ausgabe_hash") == ausgabe_hash
        h = halt.get(sc)
        if h:
            e = g.entscheide(schreiben=False)
            if not trocken:
                status.entfaellt(werk, STAGE, f"zurueckgehalten von {h.get('wer')}: {h.get('grund')}", wer=wer,
                                 scope=sc)
        else:
            e = g.entscheide(mensch_immer=verlag and not mensch_gilt,
                             mensch_grund="Mandant verlag: Endabnahme vor Auslieferung "
                                          f"(python -m pipeline.status {werk} --entscheiden 700 frei --scope {sc} ...)",
                             schreiben=not trocken)
        produkte[sc] = {"sprache": p["sprache"], "inhalt": p["inhalt"], "stufe": p["stufe"], "kanal": kanal,
                        "ergebnis": e, "zurueckgehalten": h or None, "liefern": (not h) and e == "auto",
                        "gruende": g.ergebnis["gruende"], "hinweise": g.ergebnis["hinweise"],
                        "ruecksprung": g.ergebnis["ruecksprung"], "ausgabe_hash": ausgabe_hash,
                        "artefakte": [{k: a[k] for k in ("stage", "scope", "name", "datei", "gate", "hash",
                                                          "befunde", "ruecksprung")} for a in arts]}
        g.zurueckgehalten = bool(h)
        gates.append(g)

    if not trocken:
        for sc in st_alt:
            if sc not in produkte and st_alt[sc].get("zustand") != "entfaellt":
                status.entfaellt(werk, STAGE, "nicht mehr bestellt", wer=wer, scope=sc)
        manifest.json_atomar(pfad(werk), {
            "schema": 1, "stage": STAGE, "version": VERSION, "werk": werk, "zeit": manifest.jetzt(),
            "mandant": b.mandant, "quellsprache": b.quellsprache, "sprachen": b.sprachen,
            "id_deckung": {k: (v if k != "fehlt" else {lg: x[:20] for lg, x in v.items()}) for k, v in idd.items()},
            "ergebnis": gate.gesamt([g.ergebnis["ergebnis"] for g in gates if not g.zurueckgehalten] or ["auto"]),
            "produkte": produkte}, indent=1)
    return gates


# ------------------------------------------------------------------ Abnehmer 710
def lieferbar(werk, lg=None, kanal=None):
    """Produkt-Scopes, die 710 ausliefern darf: Gate 700 je Scope frei (nicht zurueckgehalten/entfallen)."""
    d = _json(pfad(werk)) or {}
    teile = (status.laden(werk)["stages"].get(STAGE) or {}).get("teile") or {}
    out = []
    for sc, x in (d.get("produkte") or {}).items():
        if (lg and x.get("sprache") != lg) or (kanal and x.get("kanal") != kanal):
            continue
        if (teile.get(sc) or {}).get("zustand") == "frei" and not x.get("zurueckgehalten"):
            out.append(sc)
    return out


def zurueckhalten(werk, sc, wer, grund):
    if not grund:
        raise ValueError("--grund ist Pflicht")
    b = bestellung.lesen(werk)
    if sc not in [s for s, _, _ in scopes(b)]:
        raise ValueError(f"Scope {sc!r} nicht bestellt: {[s for s, _, _ in scopes(b)]}")
    e = entscheidungen(werk)
    e.setdefault("zurueckhalten", {})[sc] = {"wer": wer, "grund": grund, "wann": manifest.jetzt()}
    manifest.json_atomar(entscheidungen_pfad(werk), e, indent=1)


def liefern(werk, sc, wer):
    e = entscheidungen(werk)
    if (e.get("zurueckhalten") or {}).pop(sc, None) is None:
        raise ValueError(f"Scope {sc!r} ist nicht zurueckgehalten")
    e.setdefault("protokoll", []).append({"wer": wer, "aktion": "liefern", "scope": sc, "wann": manifest.jetzt()})
    manifest.json_atomar(entscheidungen_pfad(werk), e, indent=1)
    status.zuruecksetzen(werk, STAGE, wer=wer, grund="Zurueckhalten aufgehoben", scope=sc)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 700 Auslieferungs-Vertrag")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--trocken", action="store_true", help="nur pruefen, nichts schreiben")
    ap.add_argument("--zurueckhalten", metavar="SCOPE", help="Produkt/Kanal zurueckhalten, z. B. de:hoerbuch-basic:extern")
    ap.add_argument("--liefern", metavar="SCOPE", help="Zurueckhalten aufheben")
    ap.add_argument("--grund")
    a = ap.parse_args(argv)
    wer = a.wer or "pipeline"
    try:
        if a.zurueckhalten:
            zurueckhalten(a.werk, a.zurueckhalten, wer, a.grund)
            print(f"[700] {a.zurueckhalten} zurueckgehalten")
        if a.liefern:
            liefern(a.werk, a.liefern, wer)
            print(f"[700] {a.liefern} wieder freigegeben zur Pruefung")
        gates = run(a.werk, wer, a.trocken)
    except ValueError as e:
        print(f"[700] {e}")
        return 1
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    for g in gates:
        print(g.bericht() + ("  [zurueckgehalten]" if getattr(g, "zurueckgehalten", False) else ""))
    return gate.EXIT[gate.gesamt([g.ergebnis["ergebnis"] for g in gates
                                  if not getattr(g, "zurueckgehalten", False)] or ["auto"])]


if __name__ == "__main__":
    sys.exit(main())
