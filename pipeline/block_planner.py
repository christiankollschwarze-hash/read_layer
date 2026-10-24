"""
READ LAYER — Block-Planer (eigenstaendig, KEIN TTS)
===================================================
Aufgabe: aus den geordneten Tags eines 400_regie.json (oder 200_tagging.json) je
Kapitel BLOECKE bilden, die

  - nur aufeinanderfolgende Erzaehl-/Dialog-Saetze (s/dl) enthalten,
  - bevorzugt auf ABSATZGRENZEN (p-Tags) schneiden,
  - im Korridor BLOCK_MIN..BLOCK_MAX liegen und moeglichst GLEICHMAESSIG sind,
  - NIE BLOCK_MAX ueberschreiten (FA-Drift-Schutz; harte Schranke),
  - BLOCK_MIN nur unterschreiten, wenn es nicht anders geht (weiche Schranke).

Solo-Typen (h, qt, ep, tt ...) brechen den Lauf und werden als Einzelblock
(1 Tag) ausgegeben — genau wie heute schon. p/skip = kein Audio.

Reine Datenarbeit -> gratis, beliebig oft testbar, KEIN Modellaufruf.

CLI:  python block_planner.py <pfad/zu/400_regie.json> [--lang de]
"""

import sys, json, math

# ------------------------------------------------------------------ Korridor
BLOCK_MIN   = 6     # weiche Untergrenze (nur unter Zwang unterschreiten)
BLOCK_MAX   = 10    # HARTE Obergrenze (FA-Schutz, nie ueberschreiten)
BLOCK_IDEAL = 8     # Zielmitte fuer die Gleichverteilung

# Typ-Klassen (vorerst hier; spaeter an config angleichen)
BLOCKABLE   = {"s", "dl"}              # fliessen in Bloecke
PARA_BREAK  = {"p"}                    # Absatzgrenze, KEIN Audio
NO_AUDIO    = {"p", "skip"}            # zaehlen nicht als Audio-Schnipsel
# alles andere mit Audio (h, qt, ep, tt, fn ...) = SOLO


# ============================================================ Balance-Split
def _split_even(n: int, k: int) -> list:
    """n Einheiten auf k Bloecke moeglichst gleich: jeder base oder base+1."""
    base, rest = divmod(n, k)
    return [base + 1 if i < rest else base for i in range(k)]


def _presplit_paragraph(sent_count: int) -> list:
    """Ein einzelner Absatz > BLOCK_MAX muss intern geschnitten werden
    (erzwungen, ohne p-Grenze). Gibt near-equal Teilstuecke <= BLOCK_MAX."""
    if sent_count <= BLOCK_MAX:
        return [sent_count]
    k = math.ceil(sent_count / BLOCK_MAX)
    return _split_even(sent_count, k)


def _partition_units(sizes: list) -> list:
    """DP-Kern: zerlegt die Einheiten-Groessen in zusammenhaengende Bloecke,
    minimiert Abstand zur Mitte + bestraft Korridor-Verletzung, harte Schranke
    = BLOCK_MAX. Gibt Liste von (i, j)-Indexbereichen zurueck.
    EINE Quelle der Wahrheit fuer Report- UND Tag-Pfad."""
    n = len(sizes)
    if n == 0:
        return []
    pref = [0]
    for s in sizes:
        pref.append(pref[-1] + s)

    INF = float("inf")

    def block_cost(i, j):
        size = pref[j] - pref[i]
        if size > BLOCK_MAX:
            return INF                       # harte Schranke
        cost = (size - BLOCK_IDEAL) ** 2     # zieht zur Mitte -> gleichmaessig
        if size < BLOCK_MIN:
            cost += 1000                      # weiche Strafe: nur unter Zwang
        return cost

    best = [INF] * (n + 1)
    back = [-1] * (n + 1)
    best[0] = 0
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            c = block_cost(i, j)
            if c == INF:
                continue
            if best[i] + c < best[j]:
                best[j] = best[i] + c
                back[j] = i

    cuts = []
    j = n
    while j > 0:
        i = back[j]
        cuts.append((i, j))
        j = i
    cuts.reverse()
    return cuts


def plan_blocks(paragraphs: list) -> list:
    """paragraphs = Liste von Satzzahlen je Absatz (nur s/dl).
    Gibt Liste von Bloecken (Report-Dicts) zurueck."""
    units = []          # (satzzahl, forced_internal_cut_davor?)
    for p in paragraphs:
        parts = _presplit_paragraph(p)
        for j, part in enumerate(parts):
            units.append((part, j > 0))   # True = dieser Cut sitzt MITTEN im Absatz
    if not units:
        return []
    sizes = [u[0] for u in units]
    blocks = []
    for (i, j) in _partition_units(sizes):
        block_units = units[i:j]
        blocks.append({
            "sentences": sum(u[0] for u in block_units),
            "n_units": len(block_units),
            "forced_internal": any(u[1] for u in block_units),
        })
    return blocks


# ============================================================ 400_regie -> Plan
def _chapter_of(tag_id: str) -> str:
    return tag_id.split("_")[0]


def chapter_paragraph_runs(tags: list):
    """tags = geordnete Liste (tag_id, type) EINES Kapitels.
    Gibt eine Sequenz von Segmenten: ('block', [absatz-satzzahlen]) fuer
    s/dl-Laeufe und ('solo', tag_id) fuer Solo-Audio-Typen, in Reihenfolge."""
    segments = []
    cur_para = 0          # Saetze im aktuellen Absatz
    cur_runs = []         # abgeschlossene Absaetze des laufenden Block-Laufs

    def close_para():
        nonlocal cur_para
        if cur_para > 0:
            cur_runs.append(cur_para)
            cur_para = 0

    def flush_block():
        nonlocal cur_runs
        close_para()
        if cur_runs:
            segments.append(("block", cur_runs))
            cur_runs = []

    for tag_id, typ in tags:
        if typ in BLOCKABLE:
            cur_para += 1
        elif typ in PARA_BREAK:
            close_para()                      # Absatzgrenze
        elif typ in NO_AUDIO:
            pass                              # skip: ignorieren
        else:
            # Solo-Audio-Typ (h, qt, ep, tt ...) -> Lauf beenden, Solo emittieren
            flush_block()
            segments.append(("solo", tag_id))
    flush_block()
    return segments


def plan_from_stage06(data: dict, lang: str = None) -> dict:
    content = data["content"]
    # nach Kapitel gruppieren, Reihenfolge erhalten
    chapters = {}
    for tag_id, entry in content.items():
        ch = _chapter_of(tag_id)
        chapters.setdefault(ch, []).append((tag_id, entry.get("type", "s")))

    report = {}
    for ch, tags in chapters.items():
        segs = chapter_paragraph_runs(tags)
        ch_blocks = []
        for kind, payload in segs:
            if kind == "solo":
                ch_blocks.append({"sentences": 1, "n_units": 1,
                                  "forced_internal": False, "solo": True})
            else:
                for b in plan_blocks(payload):
                    b["solo"] = False
                    ch_blocks.append(b)
        report[ch] = ch_blocks
    return report


# ============================================================ Tag-ID-Pfad (fuer Stage 58)
def _presplit_paragraph_ids(tag_ids: list) -> list:
    """Ein Absatz mit > BLOCK_MAX Saetzen -> near-equal Teil-Listen von tag_ids
    (erzwungene Mid-Absatz-Cuts), parallel zu _presplit_paragraph."""
    n = len(tag_ids)
    if n <= BLOCK_MAX:
        return [tag_ids]
    parts, idx = [], 0
    for sz in _split_even(n, math.ceil(n / BLOCK_MAX)):
        parts.append(tag_ids[idx:idx + sz])
        idx += sz
    return parts


def _chapter_tag_runs(tags: list) -> list:
    """Wie chapter_paragraph_runs, aber Absaetze tragen die tag_ids mit.
    Gibt Segmente: ('block', [[tag_id,...] je Absatz]) und ('solo', tag_id)."""
    segments = []
    cur_para, cur_runs = [], []

    def close_para():
        nonlocal cur_para
        if cur_para:
            cur_runs.append(cur_para)
            cur_para = []

    def flush_block():
        nonlocal cur_runs
        close_para()
        if cur_runs:
            segments.append(("block", cur_runs))
            cur_runs = []

    for tag_id, typ in tags:
        if typ in BLOCKABLE:
            cur_para.append(tag_id)
        elif typ in PARA_BREAK:
            close_para()
        elif typ in NO_AUDIO:
            pass
        else:
            flush_block()
            segments.append(("solo", tag_id))
    flush_block()
    return segments


def plan_tag_blocks(tags: list) -> list:
    """DIE Schnittstelle fuer Stage 58. tags = geordnete (tag_id, type) eines
    GANZEN Buches (oder Kapitels). Gibt eine geordnete Liste zurueck:
        {"kind": "block", "tag_ids": [...], "forced_internal": bool}
        {"kind": "solo",  "tag_ids": [tag_id]}
    Bloecke = balancierte, absatzrespektierende s/dl-Gruppen (6-10, nie >10).
    Solo = h/qt/ep/tt ... (1 Tag, wie heute einzeln vertont)."""
    # nach Kapitel gruppieren, Reihenfolge erhalten
    chapters = {}
    for tag_id, typ in tags:
        chapters.setdefault(_chapter_of(tag_id), []).append((tag_id, typ))

    out = []
    for ch in chapters:                       # dict erhaelt Einfuegereihenfolge
        for kind, payload in _chapter_tag_runs(chapters[ch]):
            if kind == "solo":
                out.append({"kind": "solo", "tag_ids": [payload],
                            "forced_internal": False})
                continue
            # payload = Liste von Absaetzen (je Liste von tag_ids)
            units = []                        # (tag_id_liste, forced_internal?)
            for para in payload:
                for j, part in enumerate(_presplit_paragraph_ids(para)):
                    units.append((part, j > 0))
            sizes = [len(u[0]) for u in units]
            for (i, j) in _partition_units(sizes):
                ids = [t for u in units[i:j] for t in u[0]]
                forced = any(u[1] for u in units[i:j])
                out.append({"kind": "block", "tag_ids": ids,
                            "forced_internal": forced})
    return out


# ============================================================ Report-Druck
def print_report(report: dict):
    all_block_sizes = []
    forced = 0
    solo = 0
    under = 0
    over = 0
    for ch in sorted(report):
        blocks = report[ch]
        sizes = [b["sentences"] for b in blocks if not b["solo"]]
        line_sizes = " ".join(
            (f"[{b['sentences']}!]" if b["forced_internal"] else
             (f"({b['sentences']}s)" if b["solo"] else f"{b['sentences']}"))
            for b in blocks
        )
        print(f"  {ch}: {line_sizes}")
        for b in blocks:
            if b["solo"]:
                solo += 1
                continue
            all_block_sizes.append(b["sentences"])
            if b["forced_internal"]:
                forced += 1
            if b["sentences"] < BLOCK_MIN:
                under += 1
            if b["sentences"] > BLOCK_MAX:
                over += 1

    n = len(all_block_sizes)
    print("\n  ---- Zusammenfassung ----")
    if n:
        print(f"  Fliessbloecke:     {n}")
        print(f"  Groesse min/max:   {min(all_block_sizes)} / {max(all_block_sizes)}")
        print(f"  Groesse Schnitt:   {sum(all_block_sizes)/n:.2f}  (Ziel {BLOCK_IDEAL})")
        print(f"  im Korridor 6-10:  {n - under - over}/{n}")
        print(f"  unter {BLOCK_MIN} (Zwang): {under}")
        print(f"  ueber {BLOCK_MAX} (DARF NICHT >0): {over}")
        print(f"  mit Mid-Absatz-Cut '!': {forced}")
    print(f"  Solo-Tags (h/qt/...): {solo}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else None
    lang = None
    if "--lang" in sys.argv:
        lang = sys.argv[sys.argv.index("--lang") + 1]
    if not path:
        print("Aufruf: python block_planner.py <400_regie.json> [--lang de]")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rep = plan_from_stage06(data, lang)
    print(f"[block_planner] {path}")
    print_report(rep)
