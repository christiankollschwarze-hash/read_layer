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

PORT = 8765
MIME = {".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp", ".wav": "audio/wav", ".mp3": "audio/mpeg",
        ".json": "application/json", ".epub": "application/epub+zip", ".log": "text/plain; charset=utf-8",
        ".txt": "text/plain; charset=utf-8", ".js": "text/javascript; charset=utf-8"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)) or body is None:
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _teil(self, pfad):
        return [urllib.parse.unquote(x) for x in pfad[len("/api/werk/"):].split("/")]

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
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
                if len(t) == 3 and t[1] == "monitor":
                    return self._send(200, WERK.monitor(t[0], t[2], q.get("wer", [None])[0] or None))
                if len(t) == 1 and t[0]:
                    return self._send(200, WERK.werk(t[0], q.get("wer", [None])[0] or None))
            if u.path == "/datei":
                p = os.path.normpath(os.path.join(BASE, q.get("p", [""])[0]))
                if not p.startswith(BASE) or not os.path.isfile(p):
                    return self._send(404, {"fehler": "nicht gefunden"})
                with open(p, "rb") as f:
                    return self._send(200, f.read(), MIME.get(os.path.splitext(p)[1].lower(), "application/octet-stream"))
            return self._send(404, {"fehler": "unbekannt (altes Cockpit eingemottet)"})
        except Exception as ex:
            return self._send(500, {"fehler": str(ex)})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/upload":                       # Rohdaten (Datei), Parameter in der URL
            q = urllib.parse.parse_qs(u.query)
            if n > 300 * 1024 * 1024:
                return self._send(413, {"ok": False, "fehler": "Datei > 300 MB"})
            inhalt = self.rfile.read(n)
            meta = {k: q.get(k, [""])[0] for k in ("titel", "autor", "sprache", "todesjahr")}
            return self._send(200, WERK.upload(q.get("art", [""])[0], q.get("name", [""])[0], inhalt,
                                               q.get("wer", [None])[0], meta))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            data = {}
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
