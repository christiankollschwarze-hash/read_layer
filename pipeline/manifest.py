"""Phase 2, Fundament 3: Hash je Satz/Datei, Abgleich gegen Vorstufe, Checkpoint je Kapitel x Sprache.

Ersetzt Resume nach "Datei existiert"/"ID vorhanden". Regel: Eine Einheit (Satz, Datei, Kapitel x
Sprache) gilt nur als erledigt, wenn ihr gespeicherter Eingangs-Hash dem aktuellen Eingang entspricht.
Geaendert -> automatisch neu.

1) Manifest je Stage (Einheit = Satz/Datei), Datei work/<name>.json:
    m = manifest.Manifest(werk, "500_vertonung")          # bzw. "530_pruefung_de"
    h = manifest.hash_obj({"sprechtext": t, "stimme": sid, "modell": mv})
    if m.braucht_neu(tid, h) or not m.datei_aktuell(tid, wav):
        ... erzeugen ...
        m.setzen(tid, h, datei=wav, dauer=d, pruefung=...)
    m.speichern()                                          # atomar; zwischendurch erlaubt
    abw = m.abgleich({tid: hash_neu, ...})                 # neu / geaendert / verwaist / gleich

2) Checkpoint je Kapitel x Sprache, Ordner work/ckpt/<stage>/<kapitel>__<lg>.json:
    ck = manifest.Checkpoint(werk, "310")
    daten = ck.lesen("c001", "de", h_kap)                  # None = fehlt oder veraltet
    if daten is None:
        daten = uebersetzen(...); ck.schreiben("c001", "de", h_kap, daten)
    alle = ck.sammeln(soll)                                # {(kap, lg): daten} oder KeyError

Hash-Eingaben werden kanonisch serialisiert (sortierte Schluessel, UTF-8). Dateihashes (sha256) werden
ueber Groesse+mtime_ns im Manifest zwischengespeichert, damit grosse WAV-Bestaende schnell bleiben.
Ein Schreiber je Manifest (die Stage); Leser (Cockpit) sehen immer eine vollstaendige Datei.
"""
import hashlib
import json
import os
import time
import unicodedata
from datetime import datetime, timezone

SCHEMA = 1


def jetzt():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- Hashes
def _h(b):
    return hashlib.sha256(b).hexdigest()[:20]


def norm_text(s):
    """Unicode NFC, Zeilenenden vereinheitlicht, Rand-Leerraum weg. Inhalt sonst unveraendert."""
    return unicodedata.normalize("NFC", (s or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def hash_text(s):
    return _h(norm_text(s).encode("utf-8"))


def hash_obj(o):
    """Kanonischer Hash fuer dict/list/str/Zahlen (z. B. Sprechtext + Stimme + Modellversion)."""
    return _h(json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def hash_datei(pfad, block=1 << 20):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for b in iter(lambda: f.read(block), b""):
            h.update(b)
    return h.hexdigest()[:20]


def _sig(pfad):
    st = os.stat(pfad)
    return [st.st_size, st.st_mtime_ns]


# ---------------------------------------------------------------- atomar schreiben
def json_atomar(pfad, obj, indent=1):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    tmp = f"{pfad}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
        f.flush()
        os.fsync(f.fileno())
    for i in range(20):
        try:
            os.replace(tmp, pfad)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, pfad)


def _work(book_id):
    from config import config
    return config.work_dir(book_id)


# ---------------------------------------------------------------- Manifest
class Manifest:
    """Eintraege je Einheit: {"eingang": hash, "zeit": ..., "datei": relpfad, "datei_hash", "datei_sig", ...}."""

    def __init__(self, book_id, name, stage=None):
        self.book_id, self.name = book_id, name
        self.pfad = os.path.join(_work(book_id), f"{name}.json")
        self.basis = os.path.dirname(os.path.dirname(self.pfad))       # Werkordner
        if os.path.exists(self.pfad):
            with open(self.pfad, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("schema") != SCHEMA or "eintraege" not in d:
                raise RuntimeError(f"{self.pfad}: kein Manifest (Schema {SCHEMA}) – Altdatei? "
                                   f"Stage-Umbau muss sie migrieren oder archivieren.")
        else:
            d = {"schema": SCHEMA, "stage": stage or name.split("_")[0], "angelegt": jetzt(),
                 "meta": {}, "eintraege": {}}
        self.d = d

    @property
    def eintraege(self):
        return self.d["eintraege"]

    @property
    def meta(self):
        return self.d["meta"]

    def get(self, key):
        return self.eintraege.get(str(key))

    def braucht_neu(self, key, eingang_hash):
        e = self.get(key)
        return e is None or e.get("eingang") != eingang_hash

    def _rel(self, pfad):
        try:
            return os.path.relpath(pfad, self.basis).replace("\\", "/")
        except ValueError:
            return pfad

    def _abs(self, rel):
        return rel if os.path.isabs(rel) else os.path.join(self.basis, rel)

    def setzen(self, key, eingang_hash, datei=None, **daten):
        e = {"eingang": eingang_hash, "zeit": jetzt(), **daten}
        if datei:
            e.update(datei=self._rel(datei), datei_hash=hash_datei(datei), datei_sig=_sig(datei))
        self.eintraege[str(key)] = e
        return e

    def datei_hash(self, key):
        """Aktueller Hash der Ausgabedatei (gecacht ueber Groesse+mtime). None = fehlt."""
        e = self.get(key)
        if not e or not e.get("datei"):
            return None
        p = self._abs(e["datei"])
        if not os.path.exists(p):
            return None
        sig = _sig(p)
        if sig == e.get("datei_sig"):
            return e.get("datei_hash")
        h = hash_datei(p)
        if h == e.get("datei_hash"):
            e["datei_sig"] = sig          # nur mtime geaendert (z. B. Kopie)
        return h

    def datei_aktuell(self, key, pfad=None):
        """Datei vorhanden und unveraendert seit setzen()."""
        e = self.get(key)
        if not e or not e.get("datei"):
            return False
        if pfad and self._rel(pfad) != e["datei"]:
            return False
        h = self.datei_hash(key)
        return h is not None and h == e.get("datei_hash")

    def entfernen(self, key):
        return self.eintraege.pop(str(key), None)

    def abgleich(self, aktuell):
        """aktuell: {key: eingang_hash} der Vorstufe -> dict mit Listen neu/geaendert/verwaist/gleich."""
        aktuell = {str(k): v for k, v in aktuell.items()}
        r = {"neu": [], "geaendert": [], "verwaist": [], "gleich": []}
        for k, h in aktuell.items():
            e = self.eintraege.get(k)
            r["neu" if e is None else "gleich" if e.get("eingang") == h else "geaendert"].append(k)
        r["verwaist"] = [k for k in self.eintraege if k not in aktuell]
        return r

    def speichern(self):
        self.d["aktualisiert"] = jetzt()
        json_atomar(self.pfad, self.d)


# ---------------------------------------------------------------- Checkpoint je Kapitel x Sprache
class Checkpoint:
    def __init__(self, book_id, stage):
        self.book_id, self.stage = book_id, str(stage)
        self.ordner = os.path.join(_work(book_id), "ckpt", self.stage)

    def _p(self, kapitel, lg):
        return os.path.join(self.ordner, f"{kapitel}__{lg or '-'}.json")

    def vorhanden(self, kapitel, lg):
        return os.path.exists(self._p(kapitel, lg))

    def eingang(self, kapitel, lg):
        try:
            with open(self._p(kapitel, lg), encoding="utf-8") as f:
                return json.load(f).get("eingang")
        except FileNotFoundError:
            return None

    def lesen(self, kapitel, lg, eingang_hash):
        """Daten nur, wenn Checkpoint vorhanden und Eingang unveraendert; sonst None."""
        try:
            with open(self._p(kapitel, lg), encoding="utf-8") as f:
                c = json.load(f)
        except FileNotFoundError:
            return None
        if c.get("eingang") != eingang_hash:
            return None
        return c.get("daten")

    def schreiben(self, kapitel, lg, eingang_hash, daten, **info):
        json_atomar(self._p(kapitel, lg), {"schema": SCHEMA, "stage": self.stage, "kapitel": kapitel,
                                          "sprache": lg, "eingang": eingang_hash, "zeit": jetzt(),
                                          **info, "daten": daten}, indent=None)

    def liste(self):
        if not os.path.isdir(self.ordner):
            return []
        out = []
        for f in sorted(os.listdir(self.ordner)):
            if f.endswith(".json") and "__" in f:
                k, lg = f[:-5].split("__", 1)
                out.append((k, None if lg == "-" else lg))
        return out

    def sammeln(self, soll):
        """soll: {(kapitel, lg): eingang_hash}. Alle aktuell -> {(kap, lg): daten}, sonst KeyError mit Liste."""
        out, fehlt = {}, []
        for (k, lg), h in soll.items():
            d = self.lesen(k, lg, h)
            if d is None:
                fehlt.append(f"{k}/{lg}")
            else:
                out[(k, lg)] = d
        if fehlt:
            raise KeyError(f"Checkpoint {self.stage}: fehlt/veraltet: {', '.join(fehlt)}")
        return out

    def aufraeumen(self, soll_keys):
        """Checkpoints loeschen, die nicht mehr zur Gliederung gehoeren (Kapitel weg, Sprache abbestellt)."""
        soll = {(k, lg) for k, lg in soll_keys}
        weg = [(k, lg) for k, lg in self.liste() if (k, lg) not in soll]
        for k, lg in weg:
            os.remove(self._p(k, lg))
        return weg
