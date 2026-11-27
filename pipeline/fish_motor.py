"""Fish-Motor (AP Fish-Regie, 25.11.2026): gemeinsame Bausteine fuer 400/410/430/500/510 und Cockpit.

  motor(roh, lg)                 'gemini' | 'fish' aus book.json audio_motor (Text oder {lg: motor}); Standard gemini
  grundhaltung(figur, steckbrief) deterministische Grundhaltung 'voicing <Name EN>: ...' (EN, <= 120 Zeichen)
  fish_id(stimme, lg, anlegen)   privates Fish-Stimmmodell aus stimmen_archiv/<stimme>/klon_<lg>.wav (Register
                                 stimmen_archiv/_fish/fish_ids.json; uebernimmt tools/fish_test/stimmen_fish.json)
  tts_zeitmarken(text, ref_id)   POST /v1/tts/stream/with-timestamp (SSE, drama-3) -> (wav_bytes, woerter, info)
  tts_einfach(text, ref_id)      POST /v1/tts (kurze Hoerproben)
  fix_wav(bytes)                 Fish-Stream-WAV: Platzhalter-Laengen (0xFFFFFFFF) korrigieren
  kosten_usd(text)               Listenpreis $/Byte (config.FISH_USD_JE_MIO_BYTES, Standard 15)

Bis das Modal-Hosting steht, laeuft alles ueber die Fish-API (.env FISH_AUDIO_API). Concurrency <= 3 (API-Limit,
Semaphore prozessweit), Retry bei 429/5xx. Header 'model: drama-3' wird gesetzt und in der Antwort geprueft
(stiller Rueckfall auf s2.1-pro -> Fehler ModellRueckfall).
"""
import base64
import io
import json
import os
import re
import struct
import threading
import time
import wave

from config import config

API = getattr(config, "FISH_API", "https://api.fish.audio")
MODELL = getattr(config, "FISH_MODELL", "drama-3")
MOTOREN = ("gemini", "fish")
SR = 24000
PARALLEL = 3
_SEM = threading.Semaphore(PARALLEL)
GRUNDHALTUNG_MAX = 120


class ModellRueckfall(RuntimeError):
    pass


# ============================================================ Motor-Schalter
def motor(roh, lg):
    """book.json audio_motor: 'fish' | 'gemini' | {lg: motor}. Unbekannt/fehlt -> gemini."""
    m = (roh or {}).get("audio_motor")
    if isinstance(m, dict):
        m = m.get(lg) or m.get("*")
    m = str(m or "gemini").strip().lower()
    return m if m in MOTOREN else "gemini"


def fish_sprachen(roh, sprachen):
    return [lg for lg in sprachen or [] if motor(roh, lg) == "fish"]


# ============================================================ Grundhaltung (410)
_EN_TEMP = {"ruhig": "calm", "nervoes": "high-strung", "cholerisch": "irascible", "melancholisch": "melancholic",
            "verschmitzt": "mischievous", "guetig": "kindly", "streng": "stern", "herablassend": "condescending",
            "aengstlich": "timid", "albern": "giddy, silly", "feierlich": "solemn", "neugierig": "curious",
            "schlaefrig": "drowsy, yawning", "hochmuetig": "haughty", "verwirrt": "bewildered",
            "froehlich": "cheerful"}
_EN_TEMPO = {"langsam": "slow", "schnell": "fast"}
_EN_TON = {"hoch": "high-pitched", "tief": "low-pitched"}
_EN_ALTER = {"kind": "childlike", "alt": "old", "greis": "very old", "jung": "young"}
_EN_SICHER = {"unsicher": "hesitant", "fest": ""}


def _norm(w):
    return str(w or "").strip().lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


def name_en(figur, steckbrief=None):
    """'the March Hare' (uebersetzter Name -> Gattung), 'Alice' (Eigenname = gleicher Name in Uebersetzung)."""
    sb = steckbrief or {}
    lg_name = sb.get("name_de") or sb.get("name_lg") or ""
    lg_name = re.sub(r"^(der|die|das|the)\s+", "", lg_name.strip(), flags=re.I)
    if lg_name and lg_name.casefold() != figur.casefold():
        return f"the {figur}"
    return figur


def grundhaltung(figur, steckbrief=None):
    """Deterministisch aus Steckbrief-Merkmalen: 'voicing <Name>: <temperament>, <tempo>, <tonlage/alter>'."""
    m = (steckbrief or {}).get("merkmale") or {}
    teile = []
    for t in m.get("temperament") or []:
        x = _EN_TEMP.get(_norm(t))
        if x and x not in teile:
            teile.append(x)
        if len(teile) >= 3:
            break
    for k, tab in (("tempo", _EN_TEMPO), ("tonlage", _EN_TON), ("alter", _EN_ALTER), ("sicherheit", _EN_SICHER)):
        x = tab.get(_norm(m.get(k)))
        if x:
            teile.append(x)
    kopf = f"voicing {name_en(figur, steckbrief)}"
    out = kopf + (": " + ", ".join(teile) if teile else "")
    while len(out) > GRUNDHALTUNG_MAX and teile:
        teile.pop()
        out = kopf + (": " + ", ".join(teile) if teile else "")
    return out[:GRUNDHALTUNG_MAX]


def grundhaltung_ok(t):
    t = (t or "").strip()
    return bool(t) and len(t) <= GRUNDHALTUNG_MAX and "[" not in t and "]" not in t and ";" not in t


# ============================================================ API-Grundlagen
def api_key():
    k = os.environ.get("FISH_AUDIO_API") or os.environ.get("FISH_API_KEY")
    if k:
        return k.strip()
    env = os.path.join(config.BASE_DIR, ".env")
    if os.path.exists(env):
        with open(env, encoding="utf-8-sig", errors="ignore") as f:
            for z in f:
                m = re.match(r"\s*(?:export\s+)?FISH[A-Z_]*\s*[=:]\s*(.+)", z, re.I)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    raise RuntimeError("Fish-API-Key fehlt (.env FISH_AUDIO_API)")


def _kopf(json_body=True):
    h = {"Authorization": f"Bearer {api_key()}", "model": MODELL}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def kosten_usd(text):
    preis = float(getattr(config, "FISH_USD_JE_MIO_BYTES", 15.0))
    return round(len((text or "").encode("utf-8")) / 1e6 * preis, 6)


def fix_wav(b):
    """Fish-Stream-WAV: RIFF-/data-Laengen sind Platzhalter -> korrekte Werte."""
    d = bytearray(b)
    i = d.find(b"data")
    if d[:4] != b"RIFF" or i < 0:
        return bytes(d)
    d[4:8] = struct.pack("<I", len(d) - 8)
    d[i + 4:i + 8] = struct.pack("<I", len(d) - (i + 8))
    return bytes(d)


def pcm_aus_wav(b):
    """-> (pcm_bytes int16 mono, sr)."""
    with wave.open(io.BytesIO(fix_wav(b))) as w:
        return w.readframes(w.getnframes()), w.getframerate()


def _modell_pruefen(headers):
    """Antwort-Header mit 'model' im Namen; wenn vorhanden, muss drama-3 drinstehen."""
    werte = {k: v for k, v in (headers or {}).items() if "model" in k.lower()}
    if werte and not any(MODELL in str(v) for v in werte.values()):
        raise ModellRueckfall(f"Fish antwortet mit {werte} statt {MODELL}")
    return werte


def _post(pfad, versuche=6, **kw):
    import requests
    letzte = None
    for v in range(versuche):
        with _SEM:
            try:
                r = requests.post(f"{API}{pfad}", timeout=kw.pop("timeout", 600), **kw)
            except requests.RequestException as e:
                letzte = e
                r = None
        if r is not None and r.status_code < 300:
            return r
        if r is not None and r.status_code not in (429, 500, 502, 503, 504):
            raise RuntimeError(f"Fish {pfad}: {r.status_code} {r.text[:300]}")
        letzte = letzte or RuntimeError(f"Fish {pfad}: {r.status_code if r is not None else '-'}")
        time.sleep(3 + 3 * v)
    raise RuntimeError(f"Fish {pfad}: nach {versuche} Versuchen ({letzte})")


def tts_einfach(text, ref_id, sr=SR):
    """Kurze Probe ohne Zeitmarken -> (wav_bytes, info)."""
    body = {"text": text, "reference_id": ref_id, "format": "wav", "sample_rate": sr, "latency": "normal",
            "normalize": True}
    r = _post("/v1/tts", headers=_kopf(), data=json.dumps(body), timeout=300)
    return fix_wav(r.content), {"modell_header": _modell_pruefen(r.headers), "bytes": len(text.encode("utf-8"))}


def sse_parsen(roh):
    """SSE-Strom (bytes, UTF-8) -> (pcm_bytes, woerter[{w,a,b}], sr, chunks).
    Je Event: audio_base64, alignment.segments, chunk_seq, chunk_audio_offset_sec. Alignment je chunk_seq ersetzen
    (nicht anhaengen), Offset addieren."""
    text = roh.decode("utf-8", errors="replace") if isinstance(roh, (bytes, bytearray)) else roh
    audio, align, sr = [], {}, SR
    for block in re.split(r"\r?\n\r?\n", text):
        daten = "".join(z[5:].lstrip() for z in block.splitlines() if z.startswith("data:"))
        if not daten or daten.strip() == "[DONE]":
            continue
        try:
            ev = json.loads(daten)
        except ValueError:
            continue
        if ev.get("audio_base64"):
            audio.append(base64.b64decode(ev["audio_base64"]))
        al = ev.get("alignment") or {}
        segs = al.get("segments") if isinstance(al, dict) else None
        if segs is not None:
            seq = ev.get("chunk_seq", len(align))
            off = float(ev.get("chunk_audio_offset_sec") or 0)
            align[seq] = [{"w": s.get("text") or s.get("word") or "", "a": round(off + float(s.get("start", 0)), 3),
                           "b": round(off + float(s.get("end", 0)), 3)} for s in segs]
    roh_audio = b"".join(audio)
    if roh_audio[:4] == b"RIFF":                      # erstes Stueck mit Header, Rest roh
        pcm, sr = pcm_aus_wav(roh_audio)
    else:
        pcm = roh_audio
    woerter = [w for k in sorted(align) for w in align[k] if w["w"].strip()]
    return pcm, woerter, sr, len(align)


def tts_zeitmarken(text, ref_id, sr=SR):
    """Block-Vertonung mit Wort-Zeitmarken -> (wav_bytes 16 bit mono, woerter, info)."""
    body = {"text": text, "reference_id": ref_id, "format": "wav", "sample_rate": sr, "latency": "normal",
            "normalize": True}
    r = _post("/v1/tts/stream/with-timestamp", headers=_kopf(), data=json.dumps(body), timeout=900)
    info = {"modell_header": _modell_pruefen(r.headers), "bytes": len(text.encode("utf-8"))}
    pcm, woerter, sr2, n = sse_parsen(r.content)
    info.update(chunks=n, sr=sr2)
    return wav_bytes(pcm, sr2), woerter, info


def wav_bytes(pcm, sr=SR):
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return bio.getvalue()


# ============================================================ Stimm-Register
def register_pfad():
    from pipeline import voice_registry as vr
    return os.path.join(vr.STIMMEN_DIR, "_fish", "fish_ids.json")


def register_laden():
    p = register_pfad()
    reg = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            reg = json.load(f)
    else:                                              # einmalig aus dem Prototyp uebernehmen
        alt = os.path.join(config.BASE_DIR, "tools", "fish_test", "stimmen_fish.json")
        if os.path.exists(alt):
            with open(alt, encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    reg[k] = {"fish_id": v["fish_id"], "clip": v.get("clip"), "quelle": "fish_test"}
    return reg


def _register_schreiben(reg):
    from pipeline import manifest
    p = register_pfad()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    manifest.json_atomar(p, reg, indent=1)


_REG_LOCK = threading.Lock()


def klon_clip(stimme, lg):
    from pipeline import legacy_tor
    return legacy_tor.ref_clip(stimme, lg)


def fish_id(stimme, lg, anlegen=False):
    """Fish-Modell-ID der Archivstimme (Register); anlegen=True legt sie per API an (fast, privat)."""
    k = f"{stimme}_{lg}"
    with _REG_LOCK:
        reg = register_laden()
        if k in reg:
            return reg[k]["fish_id"]
        if not anlegen:
            return None
        wav = klon_clip(stimme, lg)
        if not wav:
            raise RuntimeError(f"{stimme}: kein klon_{lg}.wav im Archiv")
        from pipeline import voice_registry as vr
        texte = os.path.join(vr.STIMMEN_DIR, "_texte", "nordwind.json")
        text = ""
        steck = os.path.join(os.path.dirname(wav), "steckbrief.json")   # Qwen-Stimmen: Transkript des Auszugs
        if os.path.basename(wav) == f"klon_{lg}.wav" and os.path.exists(steck):
            with open(steck, encoding="utf-8") as f:
                text = ((json.load(f).get("referenzen") or {}).get(lg) or {}).get("text") or ""
        if not text and os.path.exists(texte):
            with open(texte, encoding="utf-8") as f:
                t = json.load(f).get(lg) or ""
            text = " ".join(t) if isinstance(t, list) else t
        with open(wav, "rb") as fh:
            r = _post("/model", headers={"Authorization": f"Bearer {api_key()}"}, timeout=300,
                      data={"type": "tts", "train_mode": "fast", "visibility": "private",
                            "title": f"RL {stimme} {lg}", "texts": text, "enhance_audio_quality": "false"},
                      files={"voices": (os.path.basename(wav), fh, "audio/wav")})
        reg[k] = {"fish_id": r.json()["_id"], "clip": os.path.relpath(wav, config.BASE_DIR).replace(os.sep, "/"),
                  "quelle": "api", "angelegt": time.strftime("%Y-%m-%d %H:%M:%S")}
        _register_schreiben(reg)
        return reg[k]["fish_id"]


# ============================================================ Weiche api | modal | auto (AP Fish-Modal 25.11.2026)
WEGE = ("api", "modal", "auto")


def weg_roh(roh, lg):
    """book.json fish_weg: 'api'|'modal'|'auto' oder {lg: weg}; fehlt/unbekannt -> auto."""
    w = (roh or {}).get("fish_weg")
    if isinstance(w, dict):
        w = w.get(lg) or w.get("*")
    return w if w in WEGE else "auto"


def ist_kundenwerk(b):
    return getattr(b, "mandant_art", "somnio") != "somnio"


def weg(b, lg, zeichen=0, einzel=False):
    """Entscheidung je Werk x Sprache -> {weg, grund, wahl, stopp}. stopp = Text, wenn kein Weg zulaessig ist.
    Kundenwerk -> modal (Datenschutz); Einzelaktion -> api; auto: zeichen < FISH_MODAL_AB_ZEICHEN -> api, sonst modal.
    Solange config.FISH_MODAL_FREI False: modal -> api mit Hinweis, Kundenwerk -> Stopp."""
    wahl = weg_roh(getattr(b, "roh", None), lg)
    schwelle = int(getattr(config, "FISH_MODAL_AB_ZEICHEN", 60000))
    frei = bool(getattr(config, "FISH_MODAL_FREI", False))
    if ist_kundenwerk(b):
        w, grund = "modal", "Kundenwerk (Datenschutz)" + (" – Wahl api uebergangen" if wahl == "api" else "")
    elif einzel:
        w, grund = "api", "Einzelaktion (kein Kaltstart)"
    elif wahl != "auto":
        w, grund = wahl, "manuell (book.json fish_weg)"
    elif zeichen < schwelle:
        w, grund = "api", f"auto: {zeichen} < {schwelle} Zeichen"
    else:
        w, grund = "modal", f"auto: {zeichen} >= {schwelle} Zeichen"
    out = {"weg": w, "grund": grund, "wahl": wahl, "zeichen": int(zeichen), "stopp": None}
    if w == "modal" and not frei:
        if ist_kundenwerk(b):
            out["stopp"] = "Kundenwerk braucht Modal, Self-Hosting noch nicht freigegeben (config.FISH_MODAL_FREI)"
        else:
            out.update(weg="api", grund=grund + " – Modal noch nicht freigegeben, Fallback api")
    return out


def modal_preis_h(gpu=None):
    g = (gpu or getattr(config, "FISH_MODAL_GPU", "H100")).upper()
    return float(getattr(config, f"MODAL_{g}_USD_H", 3.95))


def modal_schaetzung(zeichen, gpu=None):
    """Zeichen -> {audio_s, gpu_s, usd, kaltstart_s, kaltstart_usd} (Schaetzung aus config)."""
    audio_s = zeichen / float(getattr(config, "FISH_ZEICHEN_JE_AUDIO_S", 16.7))
    gpu_s = audio_s * float(getattr(config, "FISH_MODAL_RTF", 0.25))
    kalt = float(getattr(config, "FISH_MODAL_KALTSTART_S", 300))
    p = modal_preis_h(gpu)
    return {"audio_s": round(audio_s), "gpu_s": round(gpu_s), "usd": round(gpu_s / 3600 * p, 4),
            "kaltstart_s": round(kalt), "kaltstart_usd": round(kalt / 3600 * p, 4), "gpu": gpu or config.FISH_MODAL_GPU}


def klon_text(lg):
    """Transkript des Klon-Clips (Nordwind-Text der Sprache) – Referenztext fuer Self-Hosting."""
    from pipeline import voice_registry as vr
    p = os.path.join(vr.STIMMEN_DIR, "_texte", "nordwind.json")
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        t = json.load(f).get(lg) or ""
    return " ".join(t) if isinstance(t, list) else t

