#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
librivox_curate.py  -  Solo-Speaker-Kuration fuer LibriVox.

Drei Schritte (Unterbefehle), eine Datei, nur stdlib:

  1) python librivox_curate.py harvest [--sleep 5] [--out cache]
        Zieht den ganzen LibriVox-Katalog (extended) in 100er-Chunks, cached
        jeden Chunk als JSON. Resumebar: vorhandene Chunks werden uebersprungen.
        Laeuft NUR lokal (Container hat keinen Zugriff auf librivox.org).

  2) python librivox_curate.py build [--cache cache] [--lang de,en] [--min-works 1]
        Liest die Cache-Chunks, erkennt Solo-Werke (genau EIN Sprecher ueber
        alle Sektionen), aggregiert nach Sprecher, schreibt:
          - speakers.csv     (Rangliste, fuer Excel/Sichtung)
          - cockpit.html     (Audition-Oberflaeche)
          - speakers.json    (Datenbasis, vom Cockpit geladen)

  3) python librivox_curate.py serve [--port 8765]
        Liefert das Cockpit unter http://localhost:PORT aus und nimmt die
        Hoer-Urteile entgegen. Urteile landen DURABLE in verdicts.csv
        (ueberlebt Neustart -> Kuration ist jederzeit fortsetzbar).

Das Cockpit ist UPSTREAM von Stage 58b: es entscheidet, WELCHE Aufnahmen
ueberhaupt in die Pipeline duerfen. Maschine liefert die Fleiss-Rangliste,
das Ohr setzt das Qualitaets-Haekchen.
"""

import sys, os, json, csv, time, urllib.request, urllib.error, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_DATEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "daten")
os.makedirs(_DATEN, exist_ok=True)

API = "https://librivox.org/api/feed/audiobooks/"
CHUNK = 100

# Hoerprobe: in eine repraesentative Mittelpassage springen (Sek.), nie 0:00
# (dort steht der LibriVox-Disclaimer). Klemmgrenzen unten/oben.
SEEK_FRACTION = 0.40
SEEK_MIN, SEEK_MAX = 30, 120


# ---------------------------------------------------------------- harvest ----
def harvest(out_dir="cache", sleep=5.0):
    os.makedirs(out_dir, exist_ok=True)
    offset = 0
    while True:
        path = os.path.join(out_dir, f"chunk_{offset:06d}.json")
        if os.path.exists(path):
            print(f"[harvest] uebersprungen (cache): offset {offset}")
            offset += CHUNK
            continue
        url = API + "?" + urllib.parse.urlencode(
            {"extended": 1, "format": "json", "limit": CHUNK, "offset": offset})
        books = _get_with_retry(url)
        if books is None:
            print(f"[harvest] ABBRUCH bei offset {offset} (keine Antwort).")
            return
        if not books:
            print(f"[harvest] fertig. Letzter Offset ohne Daten: {offset}.")
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(books, f, ensure_ascii=False)
        print(f"[harvest] offset {offset}: {len(books)} Buecher -> {path}")
        offset += CHUNK
        time.sleep(sleep)  # hoeflich gegen den Server


def _get_with_retry(url, tries=4, backoff=3.0):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "lv-curate/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            return data.get("books", []) if isinstance(data, dict) else []
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            wait = backoff * (i + 1)
            print(f"[harvest] Fehler ({e}); Retry in {wait:.0f}s ...")
            time.sleep(wait)
    return None


# ------------------------------------------------------------------ build ----
def _iter_books(cache_dir):
    files = sorted(f for f in os.listdir(cache_dir) if f.endswith(".json"))
    for fn in files:
        with open(os.path.join(cache_dir, fn), encoding="utf-8") as f:
            for b in json.load(f):
                yield b


def _solo_reader(book):
    """Gibt (reader_id, display_name) zurueck, wenn das Werk solo ist, sonst None.
    Solo = ueber ALLE Sektionen genau ein distinkter reader_id, und jede
    Sektion wird allein von ihm gelesen."""
    secs = book.get("sections") or []
    if not secs:
        return None
    ids, name = set(), None
    for s in secs:
        rs = s.get("readers") or []
        if len(rs) != 1:          # Sektion mit 0 oder >1 Lesern -> nicht solo
            return None
        rid = rs[0].get("reader_id")
        if not rid:
            return None
        ids.add(rid)
        name = rs[0].get("display_name") or name
    if len(ids) != 1:
        return None
    return next(iter(ids)), (name or "?")


def _sample(book):
    """Repraesentative Sektion (Mitte) + Sprungmarke in Sekunden."""
    secs = book.get("sections") or []
    if not secs:
        return None, 0
    mid = secs[len(secs) // 2]
    url = mid.get("listen_url")
    try:
        pt = int(float(mid.get("playtime") or 0))
    except (TypeError, ValueError):
        pt = 0
    seek = int(min(SEEK_MAX, max(SEEK_MIN, pt * SEEK_FRACTION))) if pt else SEEK_MIN
    return url, seek


# LibriVox fuehrt volle Sprachnamen ("German"), nicht ISO-Codes. Mapping, damit
# "--lang de,en" wie in der Pipeline gewohnt funktioniert. Volle Namen gehen auch.
_LANG = {"de": "german", "en": "english", "fr": "french", "es": "spanish",
         "it": "italian", "pt": "portuguese", "nl": "dutch", "ru": "russian",
         "la": "latin", "el": "greek", "pl": "polish", "sv": "swedish"}


def build(cache_dir="cache", langs=None, min_works=1):
    if not os.path.isdir(cache_dir):
        print(f"[build] Kein Cache-Ordner '{cache_dir}'. Erst harvest laufen lassen.")
        return
    want = None
    if langs:
        want = set()
        for l in langs.split(","):
            l = l.strip().lower()
            want.add(_LANG.get(l, l))   # ISO -> Name, sonst unveraendert

    spk = {}          # reader_id -> aggregat
    n_books = n_solo = n_skipped = 0
    for b in _iter_books(cache_dir):
        n_books += 1
        sr = _solo_reader(b)
        if not sr:
            n_skipped += 1
            continue
        lang = (b.get("language") or "").strip().lower()
        if want and lang not in want:
            continue
        n_solo += 1
        rid, name = sr
        try:
            secs = int(float(b.get("totaltimesecs") or 0))
        except (TypeError, ValueError):
            secs = 0
        e = spk.setdefault(rid, {
            "reader_id": rid, "name": name, "works": [],
            "total_secs": 0, "langs": set()})
        url, seek = _sample(b)
        e["works"].append({
            "title": b.get("title") or "?",
            "lang": b.get("language") or "?",
            "secs": secs,
            "librivox": b.get("url_librivox") or "",
            "archive": b.get("url_iarchive") or "",
            "sample_url": url or "",
            "sample_seek": seek,
        })
        e["total_secs"] += secs
        if b.get("language"):
            e["langs"].add(b["language"])

    rows = []
    for e in spk.values():
        if len(e["works"]) < min_works:
            continue
        # repraesentative Probe = laengstes Werk des Sprechers (traegt am ehesten)
        rep = max(e["works"], key=lambda w: w["secs"]) if e["works"] else None
        rows.append({
            "reader_id": e["reader_id"],
            "name": e["name"],
            "solo_works": len(e["works"]),
            "total_hours": round(e["total_secs"] / 3600, 1),
            "langs": ", ".join(sorted(e["langs"])),
            "sample_url": (rep or {}).get("sample_url", ""),
            "sample_seek": (rep or {}).get("sample_seek", SEEK_MIN),
            "works": e["works"],
        })
    rows.sort(key=lambda r: (-r["solo_works"], -r["total_hours"]))

    # speakers.csv (schlank, fuer Sichtung)
    with open(os.path.join(_DATEN, "speakers.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["reader_id", "name", "solo_works", "total_hours", "langs"])
        for r in rows:
            w.writerow([r["reader_id"], r["name"], r["solo_works"],
                        r["total_hours"], r["langs"]])

    with open(os.path.join(_DATEN, "speakers.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)

    with open(os.path.join(_DATEN, "cockpit.html"), "w", encoding="utf-8") as f:
        f.write(_COCKPIT)

    print(f"[build] {n_books} Buecher gelesen | {n_solo} Solo-Werke | "
          f"{n_skipped} nicht-solo/leer uebersprungen")
    print(f"[build] {len(rows)} Solo-Sprecher -> speakers.csv / speakers.json / cockpit.html")
    if rows:
        print("[build] Top 5:")
        for r in rows[:5]:
            print(f"        {r['solo_works']:>3} Werke  {r['total_hours']:>6}h  "
                  f"{r['langs']:<20} {r['name']}")


# ------------------------------------------------------------------ serve ----
VERDICTS = os.path.join(_DATEN, "verdicts.csv")


def _load_verdicts():
    out = {}
    if os.path.exists(VERDICTS):
        with open(VERDICTS, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out[row["reader_id"]] = row["verdict"]
    return out


def _save_verdict(reader_id, name, verdict):
    data = _load_verdicts()
    data[reader_id] = verdict
    # Namen fuer Lesbarkeit mitfuehren
    names = {}
    if os.path.exists(VERDICTS):
        with open(VERDICTS, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                names[row["reader_id"]] = row.get("name", "")
    names[reader_id] = name
    with open(VERDICTS, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["reader_id", "name", "verdict"])
        for rid, v in data.items():
            w.writerow([rid, names.get(rid, ""), v])
        f.flush()
        os.fsync(f.fileno())   # garantiert auf Platte


def serve(port=8765):
    global VERDICTS
    VERDICTS = os.path.abspath(VERDICTS)   # cwd-unabhaengig, kein verlorenes Urteil
    for need in (os.path.join(_DATEN, "cockpit.html"), os.path.join(_DATEN, "speakers.json")):
        if not os.path.exists(need):
            print(f"[serve] '{need}' fehlt. Erst build laufen lassen.")
            return

    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            b = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path in ("/", "/cockpit.html"):
                self._send(200, open(os.path.join(_DATEN, "cockpit.html"), "rb").read(), "text/html; charset=utf-8")
            elif self.path == "/speakers.json":
                self._send(200, open(os.path.join(_DATEN, "speakers.json"), "rb").read())
            elif self.path == "/verdicts":
                self._send(200, json.dumps(_load_verdicts()))
            else:
                self._send(404, "{}")

        def do_POST(self):
            if self.path != "/verdict":
                return self._send(404, "{}")
            n = int(self.headers.get("Content-Length", 0))
            try:
                d = json.loads(self.rfile.read(n).decode("utf-8"))
                _save_verdict(str(d["reader_id"]), d.get("name", ""), d["verdict"])
                self._send(200, '{"ok":true}')
            except Exception as e:
                self._send(400, json.dumps({"ok": False, "error": str(e)}))

        def log_message(self, *a):
            pass  # still

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"[serve] Cockpit: http://localhost:{port}   (Strg+C beendet)")
    print(f"[serve] Urteile -> {os.path.abspath(VERDICTS)}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] beendet.")


# --------------------------------------------------------------- cockpit -----
_COCKPIT = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LibriVox Solo-Speaker Kuration</title>
<style>
 :root{--bg:#faf8f4;--ink:#23201b;--mut:#7a736a;--line:#e3ddd2;
       --gut:#2e7d4f;--mit:#b78900;--raus:#b23b3b;--accent:#3b5b8c}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);
      font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
        padding:12px 16px;z-index:5}
 h1{font-size:16px;margin:0 0 6px}
 .bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:13px;color:var(--mut)}
 .bar input,.bar select{font:inherit;padding:4px 8px;border:1px solid var(--line);
        border-radius:6px;background:#fff}
 .counts b{color:var(--ink)}
 table{width:100%;border-collapse:collapse}
 th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:middle}
 th{font-size:12px;color:var(--mut);font-weight:600;cursor:pointer;user-select:none}
 td.num{font-variant-numeric:tabular-nums;color:var(--mut)}
 .name{font-weight:600}
 .langs{font-size:12px;color:var(--mut)}
 .play{border:1px solid var(--line);background:#fff;border-radius:6px;padding:5px 10px;
       cursor:pointer;font:inherit}
 .play.on{background:var(--accent);color:#fff;border-color:var(--accent)}
 .verdict{display:flex;gap:4px}
 .v{border:1px solid var(--line);background:#fff;border-radius:6px;padding:5px 9px;
    cursor:pointer;font:inherit;min-width:34px;text-align:center}
 .v.gut.sel{background:var(--gut);color:#fff;border-color:var(--gut)}
 .v.mit.sel{background:var(--mit);color:#fff;border-color:var(--mit)}
 .v.raus.sel{background:var(--raus);color:#fff;border-color:var(--raus)}
 tr.done{opacity:.55}
 a{color:var(--accent);font-size:12px;text-decoration:none}
 .links{white-space:nowrap}
</style></head>
<body>
<header>
 <h1>LibriVox · Solo-Speaker Kuration</h1>
 <div class="bar">
   <input id="q" placeholder="Sprecher suchen…">
   <select id="lf"><option value="">alle Sprachen</option></select>
   <select id="vf">
     <option value="">alle</option>
     <option value="none">unklassifiziert</option>
     <option value="gut">gut</option><option value="mit">mittel</option><option value="raus">raus</option>
   </select>
   <span class="counts" id="counts"></span>
 </div>
</header>
<audio id="player" preload="none"></audio>
<table>
 <thead><tr>
   <th data-k="solo_works">Werke</th><th data-k="total_hours">Std.</th>
   <th data-k="name">Sprecher</th><th>Sprachen</th><th>Probe</th>
   <th>Urteil</th><th>Links</th>
 </tr></thead>
 <tbody id="rows"></tbody>
</table>
<script>
let DATA=[], V={}, sortK="solo_works", asc=false, playingId=null;
const player=document.getElementById('player');

async function boot(){
  DATA=await (await fetch('speakers.json')).json();
  V=await (await fetch('verdicts')).json();
  const langs=[...new Set(DATA.flatMap(r=>r.langs.split(',').map(s=>s.trim()).filter(Boolean)))].sort();
  const lf=document.getElementById('lf');
  langs.forEach(l=>{const o=document.createElement('option');o.value=l;o.textContent=l;lf.appendChild(o)});
  ['q','lf','vf'].forEach(id=>document.getElementById(id).addEventListener('input',render));
  document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k; asc=(sortK===k)?!asc:false; sortK=k; render();});
  render();
}
function key(r){return String(r.reader_id)}
function verdictOf(r){return V[key(r)]||''}

function filtered(){
  const q=document.getElementById('q').value.toLowerCase();
  const lf=document.getElementById('lf').value;
  const vf=document.getElementById('vf').value;
  let rows=DATA.filter(r=>{
    if(q && !r.name.toLowerCase().includes(q)) return false;
    if(lf && !r.langs.includes(lf)) return false;
    const v=verdictOf(r);
    if(vf==='none' && v) return false;
    if(vf && vf!=='none' && v!==vf) return false;
    return true;
  });
  rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];
    if(typeof x==='string'){x=x.toLowerCase();y=y.toLowerCase();}
    return (x<y?-1:x>y?1:0)*(asc?1:-1);});
  return rows;
}
function render(){
  const rows=filtered(), tb=document.getElementById('rows'); tb.innerHTML='';
  for(const r of rows){
    const v=verdictOf(r), tr=document.createElement('tr'); if(v)tr.className='done';
    tr.innerHTML=`
      <td class="num">${r.solo_works}</td>
      <td class="num">${r.total_hours}</td>
      <td class="name">${esc(r.name)}</td>
      <td class="langs">${esc(r.langs)}</td>
      <td><button class="play" data-id="${key(r)}">▶ anhören</button></td>
      <td><div class="verdict">
        ${vbtn(r,'gut','gut')}${vbtn(r,'mit','mittel')}${vbtn(r,'raus','raus')}
      </div></td>
      <td class="links">${r.works[0]?`<a href="${r.works[0].librivox||r.works[0].archive}" target="_blank">LibriVox ↗</a>`:''}</td>`;
    tb.appendChild(tr);
  }
  tb.querySelectorAll('.play').forEach(b=>b.onclick=()=>play(b.dataset.id));
  tb.querySelectorAll('.v').forEach(b=>b.onclick=()=>setV(b.dataset.id,b.dataset.v,b.dataset.name));
  const tot=DATA.length, done=Object.keys(V).length;
  document.getElementById('counts').innerHTML=
    `<b>${rows.length}</b> sichtbar · <b>${done}</b>/<b>${tot}</b> klassifiziert`;
}
function vbtn(r,cls,label){
  const sel=verdictOf(r)===cls?'sel':'';
  return `<button class="v ${cls} ${sel}" data-id="${key(r)}" data-v="${cls}"
          data-name="${escAttr(r.name)}">${label}</button>`;
}
function play(id){
  const r=DATA.find(x=>key(x)===id); if(!r||!r.sample_url){alert('Keine Hörprobe für diesen Sprecher.');return;}
  document.querySelectorAll('.play').forEach(b=>b.classList.toggle('on',b.dataset.id===id&&playingId!==id));
  if(playingId===id && !player.paused){player.pause();playingId=null;
    document.querySelectorAll('.play').forEach(b=>b.classList.remove('on'));return;}
  playingId=id;
  player.src=r.sample_url;
  const seek=r.sample_seek||30;
  player.onloadedmetadata=()=>{ // in repräsentative Mittelpassage springen (Disclaimer überspringen)
    try{player.currentTime=Math.min(seek, (player.duration||seek)-3);}catch(e){}
    player.play();
  };
  player.load();
}
async function setV(id,v,name){
  const cur=V[id];
  if(cur===v){delete V[id]; v='';}   // nochmal klicken = zurücknehmen
  else V[id]=v;
  render();
  try{await fetch('verdict',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({reader_id:id,name:name,verdict:V[id]||''})});}
  catch(e){console.warn('Speichern fehlgeschlagen',e);}
}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function escAttr(s){return esc(s).replace(/"/g,'&quot;')}
boot();
</script>
</body></html>
"""


# ------------------------------------------------------------------- cli -----
def _main(argv):
    if not argv:
        print(__doc__); return
    cmd, rest = argv[0], argv[1:]
    opt = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            k = rest[i][2:]
            v = rest[i + 1] if i + 1 < len(rest) and not rest[i + 1].startswith("--") else "1"
            opt[k] = v
            i += 2
        else:
            i += 1
    if cmd == "harvest":
        harvest(opt.get("out", "cache"), float(opt.get("sleep", 5)))
    elif cmd == "build":
        build(opt.get("cache", "cache"), opt.get("lang"), int(opt.get("min-works", 1)))
    elif cmd == "serve":
        serve(int(opt.get("port", 8765)))
    else:
        print(f"Unbekannter Befehl: {cmd}\n"); print(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
