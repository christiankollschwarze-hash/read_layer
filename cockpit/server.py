"""
READ LAYER — Cockpit (Phase 3, ab 03.11.2026)
=============================================
Nur Standardbibliothek. Start: cockpit_start.bat (oder: py -3.11 cockpit\\server.py)
Browser: http://127.0.0.1:8765  ->  Einzeltitel-Ansicht (cockpit/werk.html, #<book-id>)
         Gate-Monitor je Stage: /monitor#<book-id>/<stage> (cockpit/monitor.html, ab 04.11.2026)

Eine Wahrheit: work/status.json je Werk ueber pipeline.status; Laeufe nur ueber run.py (cockpit/werk_api.py).
Kein eigener Zustand, keine Auftraege, nichts startet beim Serverstart von selbst.
Altes Cockpit (Bulk, FLOW-Schritte, daten/auftraege.json, daten/freigaben.json) eingemottet:
archive/2026-11-03_cockpit_alt/.

Zwei Gleise (23.11.2026): intern (admin/kurator) und Kunde (verlag/autor -> nur /kunde, /api/kunde/...).
Wer fragt, bestimmt der Server (cockpit/anmeldung.py): Sitzungs-Cookie, sonst eigener Rechner = interner
Standardnutzer, sonst 401. Kundensitzungen bekommen auf allen internen Routen 403.
"""
import json
import os
import sys
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, BASE)
from cockpit import werk_api as WERK  # noqa: E402
from cockpit import anmeldung as ANM  # noqa: E402
from cockpit import kunde_api as KUNDE  # noqa: E402
from pipeline import s080_mandant  # noqa: E402

PORT = 8765
MIME = {".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp", ".wav": "audio/wav", ".mp3": "audio/mpeg",
        ".json": "application/json", ".epub": "application/epub+zip", ".log": "text/plain; charset=utf-8",
        ".txt": "text/plain; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".woff2": "font/woff2", ".m4a": "audio/mp4", ".m4b": "audio/mp4",
        ".ogg": "audio/ogg", ".jsonl": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}


ABBRUCH = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)
LOKAL = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
OFFEN = ("/kunde", "/api/anmelden", "/api/abmelden")        # ohne Anmeldung erreichbar (+ /vendor/)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", kopf=None):
        if isinstance(body, (dict, list)) or body is None:
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (kopf or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except ABBRUCH:                      # Browser hat die Anfrage abgebrochen (Seitenwechsel, Neuladen)
            self.close_connection = True

    def _teil(self, pfad, vor="/api/werk/"):
        return [urllib.parse.unquote(x) for x in pfad[len(vor):].split("/")]

    # ------------------------------------------------------------ Wer fragt? (Server entscheidet)
    def _wer(self):
        """-> (wer, art): art 'sitzung' (angemeldet), 'lokal' (eigener Rechner, ohne Sitzung), 'fremd'."""
        w = ANM.sitzung(ANM.token_aus_cookie(self.headers.get("Cookie")))
        if w:
            return w, "sitzung"
        if self.client_address[0] in LOKAL:
            return None, "lokal"
        return None, "fremd"

    def _schranke(self, pfad):
        """Sperre vor jeder Route. -> (wer, kunde, antwort_gesendet)."""
        wer, art = self._wer()
        kunde = art == "sitzung" and s080_mandant.ist_kunde(wer)
        if pfad in OFFEN or pfad.startswith("/vendor/"):
            return wer, kunde, False
        if pfad.startswith("/api/kunde/"):
            if kunde:
                return wer, True, False
            als = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("als", [None])[0]
            intern = wer if art == "sitzung" else (s080_mandant.nutzer() if art == "lokal" else None)
            if intern and s080_mandant.rolle(intern) == "admin" and als and s080_mandant.ist_kunde(als):
                return als, True, False                           # admin: Kundensicht als <kunde> pruefen
            self._send(401 if art == "fremd" else 403, {"fehler": "Bitte melden Sie sich an."})
            return wer, kunde, True
        if kunde:
            self._send(403, {"fehler": "kein Zugriff"})
            return wer, kunde, True
        if art == "fremd":
            self._send(401, {"fehler": "nicht angemeldet"})
            return wer, kunde, True
        return wer, kunde, False

    def _kunde_get(self, pfad, wer):
        if pfad == "/api/kunde/ich":
            return self._send(200, KUNDE.ich(wer))
        if pfad == "/api/kunde/werke":
            return self._send(200, KUNDE.werke(wer))
        t = self._teil(pfad, "/api/kunde/werk/")
        if pfad.startswith("/api/kunde/werk/") and len(t) == 1 and t[0]:
            try:
                return self._send(200, KUNDE.werk(t[0], wer))
            except (KUNDE.KeinZugriff, KeyError):
                return self._send(404, {"fehler": "nicht gefunden"})
        return self._send(404, {"fehler": "nicht gefunden"})

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            wer, kunde, fertig = self._schranke(u.path)
            if fertig:
                return
            if u.path == "/kunde":
                with open(os.path.join(HERE, "kunde.html"), "rb") as f:
                    return self._send(200, f.read(), MIME[".html"])
            if u.path.startswith("/api/kunde/"):
                return self._kunde_get(u.path, wer)
            if wer:                                     # angemeldet: Nutzer aus der Sitzung, nicht aus ?wer=
                q["wer"] = [wer]
            if u.path in ("/", "/index.html", "/start"):
                with open(os.path.join(HERE, "start.html"), "rb") as f:
                    return self._send(200, f.read(), MIME[".html"])
            if u.path == "/werk":
                with open(os.path.join(HERE, "werk.html"), "rb") as f:
                    return self._send(200, f.read(), MIME[".html"])
            if u.path == "/monitor":
                with open(os.path.join(HERE, "monitor.html"), "rb") as f:
                    return self._send(200, f.read(), MIME[".html"])
            if u.path.startswith("/vendor/"):
                p = os.path.normpath(os.path.join(HERE, "vendor", os.path.basename(u.path)))
                if not os.path.isfile(p):
                    return self._send(404, {"fehler": "nicht gefunden"})
                with open(p, "rb") as f:
                    return self._send(200, f.read(), MIME.get(os.path.splitext(p)[1].lower(), "application/octet-stream"))
            if u.path == "/api/hilfe":
                return self._send(200, WERK.hilfe())
            if u.path == "/api/werkliste":
                return self._send(200, WERK.werke_liste())
            if u.path == "/api/upload":
                return self._send(200, WERK.upload_stand())
            if u.path == "/api/werke":
                return self._send(200, WERK.werke())
            if u.path == "/api/nutzer":
                return self._send(200, WERK.nutzer_liste())
            if u.path == "/api/ampel":
                return self._send(200, WERK.ampel_alle())
            if u.path.startswith("/api/werk/"):
                t = self._teil(u.path)
                if len(t) == 2 and t[1] == "ampel":
                    return self._send(200, WERK.ampel(t[0]))
                if len(t) == 2 and t[1] == "lauf":
                    return self._send(200, WERK.LAEUFE.state(t[0]))
                if len(t) == 2 and t[1] == "rohtext":
                    return self._send(200, WERK.rohtext(t[0]), MIME[".txt"])
                if len(t) == 3 and t[1] == "ergebnis":
                    return self._send(200, WERK.ergebnis(t[0], t[2]))
                if len(t) == 3 and t[1] == "monitor":
                    return self._send(200, WERK.monitor(t[0], t[2], q.get("wer", [None])[0] or None))
                if len(t) == 4 and t[1] == "monitor" and t[3] == "teil":
                    return self._send(200, WERK.monitor_teil(t[0], t[2], {k: v[0] for k, v in q.items()}))
                if len(t) == 1 and t[0]:
                    return self._send(200, WERK.werk(t[0], q.get("wer", [None])[0] or None))
            if u.path == "/paket.zip":                    # Ordner als ZIP (Monitor 710: Plattform-Paket)
                import io, zipfile
                p = os.path.normpath(os.path.join(BASE, q.get("p", [""])[0]))
                if not p.startswith(BASE) or not os.path.isdir(p):
                    return self._send(404, {"fehler": "nicht gefunden"})
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
                    for wurzel, _, dateien in os.walk(p):
                        for d in sorted(dateien):
                            f = os.path.join(wurzel, d)
                            z.write(f, os.path.relpath(f, p))
                return self._send(200, buf.getvalue(), "application/zip")
            if u.path == "/datei":
                p = os.path.normpath(os.path.join(BASE, q.get("p", [""])[0]))
                if not p.startswith(BASE) or not os.path.isfile(p):
                    return self._send(404, {"fehler": "nicht gefunden"})
                with open(p, "rb") as f:
                    return self._send(200, f.read(), MIME.get(os.path.splitext(p)[1].lower(), "application/octet-stream"))
            return self._send(404, {"fehler": "unbekannt (altes Cockpit eingemottet)"})
        except ABBRUCH:
            self.close_connection = True
        except Exception as ex:
            return self._send(500, {"fehler": "Interner Fehler"} if self._ist_kunde() else {"fehler": str(ex)})

    def _ist_kunde(self):
        try:
            w, art = self._wer()
            return art == "sitzung" and s080_mandant.ist_kunde(w)
        except Exception:
            return True

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        u = urllib.parse.urlparse(self.path)
        if n > 300 * 1024 * 1024:
            return self._send(413, {"ok": False, "fehler": "Datei > 300 MB"})
        wer, kunde, fertig = self._schranke(u.path)
        if fertig:
            return
        if u.path == "/api/anmelden":
            try:
                d = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                d = {}
            t = ANM.anmelden(str(d.get("nutzer") or ""), str(d.get("kennwort") or ""))
            if not t:
                return self._send(401, {"ok": False, "fehler": "Anmeldung fehlgeschlagen."})
            w = ANM.sitzung(t)
            return self._send(200, {"ok": True, "kunde": s080_mandant.ist_kunde(w)},
                              kopf={"Set-Cookie": ANM.cookie_setzen(t)})
        if u.path == "/api/abmelden":
            ANM.abmelden(ANM.token_aus_cookie(self.headers.get("Cookie")))
            return self._send(200, {"ok": True}, kopf={"Set-Cookie": ANM.cookie_loeschen()})
        if u.path.startswith("/api/kunde/"):
            return self._send(404, {"fehler": "nicht gefunden"})     # Freigaben folgen (Punkt 5)
        if u.path == "/api/upload":                       # Rohdaten (Datei), Parameter in der URL
            q = urllib.parse.parse_qs(u.query)
            if wer:
                q["wer"] = [wer]
            inhalt = self.rfile.read(n)
            meta = {k: q.get(k, [""])[0] for k in ("titel", "autor", "sprache", "todesjahr")}
            return self._send(200, WERK.upload(q.get("art", [""])[0], q.get("name", [""])[0], inhalt,
                                               q.get("wer", [None])[0], meta))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            data = {}
        if wer and isinstance(data, dict):              # angemeldet: Nutzer aus der Sitzung, nicht aus dem Formular
            data["wer"] = wer
        try:
            if self.path.startswith("/api/werk/"):
                t = self._teil(self.path)
                if len(t) == 3 and t[1] == "monitor":
                    return self._send(200, WERK.monitor_speichern(t[0], t[2], data, data.get("wer")))
                if len(t) == 2:
                    w, was = t
                    if was == "aktion":
                        return self._send(200, WERK.aktion(w, data.get("art"), data.get("stage"), data.get("wer"),
                                                           data.get("grund"), data.get("scope"), data.get("nach")))
                    if was == "lauf":
                        return self._send(200, WERK.lauf(w, data.get("modus"), data.get("wer"), data.get("von"),
                                                         bool(data.get("live"))))
                    if was == "regler":
                        return self._send(200, WERK.regler(w, data.get("stage"), data.get("werte"), data.get("wer"),
                                                           bool(data.get("nur_vorschau"))))
                    if was == "stop":
                        return self._send(200, {"ok": WERK.LAEUFE.stop(w)})
            return self._send(404, {"fehler": "unbekannt (altes Cockpit eingemottet)"})
        except ABBRUCH:
            self.close_connection = True
        except Exception as ex:
            return self._send(500, {"fehler": str(ex)})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"READ LAYER Cockpit: http://127.0.0.1:{PORT}   (Strg+C beendet)")
    print(f"Python fuer Pipeline-Laeufe: {sys.executable}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
