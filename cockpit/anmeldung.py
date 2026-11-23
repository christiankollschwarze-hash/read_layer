"""
READ LAYER — Anmeldung fuer das Cockpit (AP Kunden-Cockpit, 23.11.2026)
=====================================================================
Zwei Gleise: intern (admin/kurator, wie bisher) und Kunde (verlag/autor, nur /kunde + /api/kunde/...).
Wer eine Anfrage stellt, entscheidet der Server – nie ein Parameter (?wer=) aus dem Browser.

Zugang:   config/rollen.json, je Nutzer "zugang": "pbkdf2$<iter>$<salz-hex>$<hash-hex>"
          setzen:  py -3.11 -m cockpit.anmeldung setzen <nutzer>      (fragt das Kennwort ab)
Sitzung:  Cookie rl_sitzung (HttpOnly, SameSite=Strict), Sitzungen nur im Speicher (Neustart = abgemeldet),
          Ablauf nach SITZUNG_STUNDEN.
Ohne Sitzung: Anfrage vom eigenen Rechner (127.0.0.1/::1) = interner Standardnutzer (wie bisher);
          von aussen = nicht angemeldet (401).
"""
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import s080_mandant  # noqa: E402

COOKIE = "rl_sitzung"
SITZUNG_STUNDEN = 12
ITER = 200_000
_SITZUNGEN = {}          # token -> {"wer": id, "bis": ts}
_LOCK = threading.Lock()


def hash_kennwort(kennwort, salz=None, it=ITER):
    salz = salz or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", kennwort.encode("utf-8"), salz, it)
    return f"pbkdf2${it}${salz.hex()}${h.hex()}"


def pruefe_kennwort(kennwort, gespeichert):
    try:
        art, it, salz, h = (gespeichert or "").split("$")
        if art != "pbkdf2":
            return False
        neu = hashlib.pbkdf2_hmac("sha256", (kennwort or "").encode("utf-8"), bytes.fromhex(salz), int(it))
        return hmac.compare_digest(neu.hex(), h)
    except (ValueError, TypeError):
        return False


def anmelden(wer, kennwort):
    """-> Sitzungstoken oder None. Gleiche Antwort fuer unbekannten Nutzer und falsches Kennwort."""
    e = ((s080_mandant.register().get("nutzer") or {}).get(wer or "")) or {}
    if not e.get("zugang") or not pruefe_kennwort(kennwort, e["zugang"]) or not s080_mandant.rolle(wer):
        hash_kennwort(kennwort or "x", b"0" * 16)          # gleiche Rechenzeit, verraet keine Nutzer-IDs
        return None
    t = secrets.token_urlsafe(32)
    with _LOCK:
        _SITZUNGEN[t] = {"wer": wer, "bis": time.time() + SITZUNG_STUNDEN * 3600}
    return t


def abmelden(token):
    with _LOCK:
        _SITZUNGEN.pop(token or "", None)


def sitzung(token):
    """-> Nutzer-ID der gueltigen Sitzung oder None."""
    if not token:
        return None
    with _LOCK:
        s = _SITZUNGEN.get(token)
        if s and s["bis"] < time.time():
            _SITZUNGEN.pop(token, None)
            s = None
    if not s or not s080_mandant.rolle(s["wer"]):         # Nutzer inzwischen entfernt -> Sitzung ungueltig
        return None
    return s["wer"]


def token_aus_cookie(kopf):
    for teil in (kopf or "").split(";"):
        k, _, v = teil.strip().partition("=")
        if k == COOKIE:
            return v
    return None


def cookie_setzen(token):
    return f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SITZUNG_STUNDEN * 3600}"


def cookie_loeschen():
    return f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"


def zugang_setzen(wer, kennwort):
    p = s080_mandant.register_pfad()
    with open(p, encoding="utf-8") as f:
        reg = json.load(f)
    if wer not in (reg.get("nutzer") or {}):
        raise KeyError(f"Nutzer {wer!r} nicht in {p}")
    reg["nutzer"][wer]["zugang"] = hash_kennwort(kennwort)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if len(a) == 2 and a[0] == "setzen":
        k1 = getpass.getpass("Neues Kennwort: ")
        if len(k1) < 10 or k1 != getpass.getpass("Wiederholen: "):
            print("Abbruch: mindestens 10 Zeichen, beide Eingaben gleich.")
            return 2
        zugang_setzen(a[1], k1)
        print(f"Zugang fuer {a[1]} gesetzt.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
