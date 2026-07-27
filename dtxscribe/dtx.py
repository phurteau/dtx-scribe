"""DTX model: GM-drum -> lane mapping, quantized note grid, DTX emit + zip packaging."""
import os, math, re, zipfile
from fractions import Fraction
from functools import reduce

GRID = 64  # slots per whole-note

# GM MIDI drum -> (DTX channel, WAV label)
MAP = {
    36: ("13", "bd"), 35: ("13", "bd"),
    38: ("12", "sd"), 40: ("12", "sd"), 37: ("12", "sd"),
    # Hi-hat bow + Roland edge notes (22 closed edge, 26 open edge) collapse to their bow lane.
    42: ("11", "hh"), 22: ("11", "hh"), 44: ("1B", "lp"), 46: ("18", "ho"), 26: ("18", "ho"),
    48: ("14", "ht"), 50: ("14", "ht"),
    45: ("15", "lt"), 47: ("15", "lt"),
    41: ("17", "ft"), 43: ("17", "ft"),
    49: ("16", "cy"), 57: ("1A", "cy"), 55: ("16", "cy"), 52: ("1A", "cy"),
    51: ("19", "rd"), 59: ("19", "rd"), 53: ("19", "rb"),
}

# WAV slot assignments (2-char labels in DTX). 01 reserved for BGM.
WAV_SLOTS = [
    ("02", "bd"), ("03", "sd"), ("04", "hh"), ("05", "ho"), ("06", "ht"),
    ("07", "lt"), ("08", "ft"), ("09", "cy"), ("0A", "rd"), ("0B", "rb"), ("0C", "lp"),
]
LABEL2SLOT = {lab: slot for slot, lab in WAV_SLOTS}
LANE_ORDER = ["13", "12", "11", "18", "1B", "14", "15", "17", "16", "1A", "19"]

# Human-readable names + the WAV slot a NEWLY-added note on each lane should reference
# (used by the chart editor). Crash and left-crash share the crash sample.
LANE_NAME = {"1A": "LC", "11": "HH", "18": "HO", "1B": "LP", "12": "SD", "14": "HT",
             "13": "BD", "15": "LT", "17": "FT", "16": "CY", "19": "RD"}
LANE_DEFAULT_SLOT = {"13": "02", "12": "03", "11": "04", "18": "05", "14": "06",
                     "15": "07", "17": "08", "16": "09", "1A": "09", "19": "0A", "1B": "0C"}
# Left→right column order for the editor (DTXMania-style drum lane layout).
EDITOR_LANES = ["1A", "11", "18", "1B", "12", "14", "13", "15", "17", "16", "19"]
# Kit one-shot label per lane (lane -> 'bd'/'sd'/…), via the lane's default WAV slot. Used to
# override the built-in synth sample with a real per-song / imported one-shot in the editor.
LANE_LABEL = {lane: dict(WAV_SLOTS)[slot] for lane, slot in LANE_DEFAULT_SLOT.items()}


def chart_to_json(events, barlens, bpm, meta):
    """Serialize the in-memory chart into an editor-friendly JSON dict. Positions are
    sent as an exact fraction {n,d} plus a float for convenient canvas placement."""
    bars = []
    for i, chan in enumerate(events):
        notes = []
        for ch, slots in chan.items():
            for pos, slot in slots.items():
                notes.append({"lane": ch, "n": pos.numerator, "d": pos.denominator,
                              "pos": float(pos), "slot": slot})
        bl = barlens[i] if i < len(barlens) else Fraction(1)
        bars.append({"index": i, "barlen": [bl.numerator, bl.denominator], "notes": notes})
    return {"bpm": round(float(bpm), 3), "bars": bars,
            "lanes": EDITOR_LANES, "laneNames": LANE_NAME,
            "title": meta.get("title", ""), "artist": meta.get("artist", "")}


def events_from_json(bars_json, n_bars):
    """Rebuild (events, barlens) from the editor's edited bar list. Unknown lanes are
    ignored; a note with no slot falls back to the lane's default sample."""
    events = [dict() for _ in range(n_bars)]
    barlens = [Fraction(1)] * n_bars
    for b in bars_json:
        i = int(b.get("index", 0))
        if not (0 <= i < n_bars):
            continue
        bl = b.get("barlen")
        if isinstance(bl, (list, tuple)) and len(bl) == 2 and bl[1]:
            barlens[i] = Fraction(int(bl[0]), int(bl[1]))
        for nt in b.get("notes", []):
            ch = str(nt.get("lane", ""))
            if ch not in LANE_NAME:
                continue
            d = int(nt.get("d", 1)) or 1
            pos = Fraction(int(nt.get("n", 0)), d)
            if pos < 0 or pos >= 1:
                continue
            slot = str(nt.get("slot") or LANE_DEFAULT_SLOT.get(ch, "04"))
            events[i].setdefault(ch, {})[pos] = slot
    return events, barlens


# Lane-grouping folds: each maps a source drum channel onto a destination lane, matching the
# editor's "Group voices" folds and DTXMania's standard combined lanes. The moved note takes
# the destination lane's default sample. A tick already occupied on the destination wins (no
# duplicate). This is chart-data folding (it changes the emitted chart) - the "9-lane"/"11-lane"
# choice at generation and the editor bulk folds share this exact behavior.
GROUP_FOLDS = {
    "ride":    ("19", "16"),   # ride  -> right cymbal (CY)
    "openhat": ("18", "11"),   # open hi-hat -> closed hi-hat (one HH lane)
    "lp":      ("1B", "13"),   # left pedal  -> bass drum (BD)
}
# Preset -> which folds are active. "custom" is resolved from explicit flags by the caller.
GROUP_PRESETS = {
    "full":     (),                         # 11 lanes: nothing folded
    "standard": ("ride", "openhat"),        # 9 lanes: ride+open-hat folded, LP kept separate
}


def group_lanes(events, folds):
    """Fold drum lanes in-place per ``folds`` (an iterable of GROUP_FOLDS keys). Returns the
    number of notes moved. Idempotent and order-independent; safe to run on any chart."""
    active = [GROUP_FOLDS[f] for f in folds if f in GROUP_FOLDS]
    if not active:
        return 0
    moved = 0
    for bar in events:
        for src, dst in active:
            srcmap = bar.get(src)
            if not srcmap:
                continue
            dstmap = bar.setdefault(dst, {})
            dslot = LANE_DEFAULT_SLOT.get(dst, "04")
            for pos in list(srcmap.keys()):
                if pos not in dstmap:
                    dstmap[pos] = dslot
                moved += 1
            bar.pop(src, None)
    return moved


def folds_from_opts(preset, ride=False, openhat=False, lp=False):
    """Resolve a grouping preset (full/standard/custom) + custom flags into a fold-key list."""
    p = str(preset or "full").strip().lower()
    if p in GROUP_PRESETS:
        return list(GROUP_PRESETS[p])
    folds = []                                   # custom
    if ride: folds.append("ride")
    if openhat: folds.append("openhat")
    if lp: folds.append("lp")
    return folds



# DTXMania / GITADORA difficulty tiers, keyed by the 0.00-9.99 auto-difficulty score.
# Each: (key, .dtx filename, set.def label, set.def Ln slot, low, high)  -- range is [low, high)
DIFF_TIERS = [
    ("basic",    "bsc.dtx",  "BASIC",    1, 0.00, 3.00),
    ("advanced", "adv.dtx",  "ADVANCED", 2, 3.00, 6.00),
    ("extreme",  "ext.dtx",  "EXTREME",  3, 6.00, 8.50),
    ("master",   "mstr.dtx", "MASTER",   4, 8.50, 10.01),
]
_TIER_BY_KEY = {t[0]: t for t in DIFF_TIERS}


def tier_from_score(score):
    """Map a 0.00-9.99 difficulty score to a tier key (basic/advanced/extreme/master)."""
    s = max(0.0, min(9.99, float(score)))
    for key, _fn, _lbl, _slot, lo, hi in DIFF_TIERS:
        if lo <= s < hi:
            return key
    return "master"


def tier_info(key):
    """Return (dtx_filename, set.def label, set.def slot) for a tier key."""
    t = _TIER_BY_KEY.get(str(key).lower(), _TIER_BY_KEY["extreme"])
    return t[1], t[2], t[3]

def _lcm(a, b): return a * b // math.gcd(a, b)


def events_from_tab(measures):
    """Songsterr drum measures -> (events, barlens) with forced true meter +
    grid quantization so phantom overflow notes merge and tempo stays locked."""
    events, barlens = [], []
    cur_sig = (4, 4)
    for m in measures:
        s = m.get("signature")
        if s:
            cur_sig = (int(s[0]), int(s[1]))
        nominal = Fraction(cur_sig[0], cur_sig[1])
        bar_slots = max(1, round(float(nominal) * GRID))
        chan = {}
        for v in m.get("voices", []):
            cum = Fraction(0)
            for b in v.get("beats", []):
                d = b.get("duration"); dur = Fraction(d[0], d[1]) if d else Fraction(0)
                if not b.get("rest"):
                    slot = int(round(float(cum) * GRID))
                    if slot >= bar_slots:
                        slot = bar_slots - 1
                    pos = Fraction(slot, bar_slots)
                    for n in b.get("notes", []):
                        if n.get("rest"):
                            continue
                        fr = n.get("fret")
                        if fr in MAP:
                            ch, lab = MAP[fr]
                            chan.setdefault(ch, {}).setdefault(pos, LABEL2SLOT[lab])
                cum += dur
        events.append(chan)
        barlens.append(nominal)
    return events, barlens


def _chan_line(mi, ch, slotmap):
    positions = list(slotmap.keys())
    denoms = [p.denominator for p in positions if p != 0] or [1]
    N = max(reduce(_lcm, denoms, 1), 1)
    cells = ["00"] * N
    for p, lab in slotmap.items():
        idx = int(p * N)
        if 0 <= idx < N:
            cells[idx] = lab
    return f"#{mi:03d}{ch}: " + "".join(cells)


def _hdr(v):
    """Sanitize a value going into a single-line ``#TAG: value`` header. Newlines and other
    control characters are collapsed to a space so a multi-line title/artist/comment can't
    inject extra #DIRECTIVES (e.g. a fake #DLEVEL) into the chart body."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(v)).strip()


def emit_dtx(events, barlens, meta):
    """Render the .dtx text. meta: dict(title, artist, bpm, dlevel, comment, bgm, preimage)."""
    L = ["; DTXMania chart -- generated by DTXScribe"]
    L += [f"#TITLE: {_hdr(meta['title'])}", f"#ARTIST: {_hdr(meta['artist'])}",
          f"#COMMENT: {_hdr(meta.get('comment',''))}", f"#DLEVEL: {meta.get('dlevel',50)}"]
    if meta.get("preimage"):
        L.append(f"#PREIMAGE: {_hdr(meta['preimage'])}")      # song-select jacket image
    L += [f"#BPM: {meta['bpm']}", ""]
    L.append(f"#WAV01: {meta['bgm']}")
    for slot, lab in WAV_SLOTS:
        L.append(f"#WAV{slot}: {lab}.wav")
    L.append("")
    for slot, lab in WAV_SLOTS:
        L.append(f"#VOLUME{slot}: {meta.get('sample_volume',85)}")
    L += ["", "; ---- body ----", "#00001: 01"]
    for i, bl in enumerate(barlens):
        if bl != Fraction(1):
            L.append(f"#{i:03d}02: {float(bl):g}")
    L.append("")
    for i, chan in enumerate(events):
        wrote = False
        for ch in LANE_ORDER:
            if chan.get(ch):
                L.append(_chan_line(i, ch, chan[ch])); wrote = True
        if wrote:
            L.append("")
    return "\n".join(L) + "\n"


def count_chips(events):
    return sum(len(sm) for ch in events for sm in ch.values())


# DTX drum channels this editor understands. The CHANNEL identifies the lane (the DTX spec:
# 11=hi-hat, 12=snare, ...), independent of which WAV slot a note references, so import keys
# off the channel and re-assigns this app's own default slot per lane. 1C (2nd bass pedal)
# has no dedicated editor lane, so its notes fold into the kick.
_IMPORT_LANE = {ch: ch for ch in LANE_NAME}      # 11..19, 1A, 1B -> themselves
_IMPORT_LANE["1C"] = "13"                          # left bass drum -> kick


def parse_dtx(text):
    """Parse a DTXMania .dtx into (events, barlens, bpm, meta) - the inverse of emit_dtx.

    Only drum channels are read (guitar/bass/BGA/etc. are ignored). Each note is keyed by its
    channel to a lane and assigned this app's default WAV slot for that lane, so an imported
    chart edits and re-packages through the built-in kit exactly like a generated one. meta
    carries title/artist/bpm/dlevel/comment plus the referenced bgm filename and preimage
    (for the caller to wire audio + jacket)."""
    import re
    from collections import Counter
    title = artist = comment = preimage = bgm = ""
    bpm = None
    dlevel = 50
    wav_defs = {}      # slot -> referenced wav filename (from #WAVxx headers)
    lane_src = {}      # lane -> Counter of the source WAV slots its notes referenced
    bar_notes = {}     # bar -> {lane -> {Fraction pos: slot}}
    bar_len = {}       # bar -> Fraction
    max_bar = 0

    body_re = re.compile(r"^#(\d{3})([0-9A-Za-z]{2}):?\s*(\S+)")
    head_re = re.compile(r"^#([A-Za-z][A-Za-z0-9]*):?\s*(.*)$")

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or not line.startswith("#"):
            continue
        mb = body_re.match(line)
        if mb:
            bar = int(mb.group(1)); ch = mb.group(2).upper(); data = mb.group(3)
            max_bar = max(max_bar, bar)
            if ch == "01":
                continue                                   # BGM auto-play row
            if ch == "02":                                 # bar-length change
                try:
                    bar_len[bar] = Fraction(data)
                except (ValueError, ZeroDivisionError):
                    pass
                continue
            lane = _IMPORT_LANE.get(ch)
            if not lane:
                continue                                   # non-drum / unsupported channel
            cells = re.sub(r"[^0-9A-Za-z]", "", data)
            n = len(cells) // 2
            if n <= 0:
                continue
            slot = LANE_DEFAULT_SLOT.get(lane, "04")
            cellmap = bar_notes.setdefault(bar, {}).setdefault(lane, {})
            srccnt = lane_src.setdefault(lane, Counter())
            for k in range(n):
                tok = cells[2 * k:2 * k + 2]
                if tok != "00":
                    cellmap[Fraction(k, n)] = slot
                    srccnt[tok.upper()] += 1
            continue
        mh = head_re.match(line)
        if mh:
            key = mh.group(1).upper(); val = mh.group(2).strip()
            if key == "TITLE": title = val
            elif key == "ARTIST": artist = val
            elif key == "COMMENT": comment = val
            elif key == "PREIMAGE": preimage = val
            elif key == "BPM" and bpm is None:             # base tempo only (ignore #BPMxx)
                try: bpm = float(val)
                except ValueError: pass
            elif key == "DLEVEL":
                m = re.search(r"\d+", val)
                if m: dlevel = int(m.group(0))
            elif key.startswith("WAV") and len(key) == 5:
                slot2 = key[3:5].upper()
                wav_defs[slot2] = val
                if slot2 == "01":
                    bgm = val

    n_bars = max_bar + 1
    events = [dict() for _ in range(n_bars)]
    barlens = [Fraction(1)] * n_bars
    for bar in range(n_bars):
        barlens[bar] = bar_len.get(bar, Fraction(1))
        for lane, cellmap in bar_notes.get(bar, {}).items():
            for pos, slot in cellmap.items():
                events[bar].setdefault(lane, {})[pos] = slot

    lane_slot = {lane: cnt.most_common(1)[0][0] for lane, cnt in lane_src.items() if cnt}
    meta = dict(title=title, artist=artist, comment=comment, dlevel=dlevel,
                bpm=round(float(bpm), 3) if bpm else 120.0, bgm=bgm, preimage=preimage,
                wav_defs=wav_defs, lane_slot=lane_slot)
    return events, barlens, meta["bpm"], meta


def package(out_dir, song_name, dtx_text, bgm_src, kit_dir, kit_files,
            dtx_name="chart.dtx", set_label="Drums", set_slot=1, image_src=None):
    """Write folder <out_dir>/<song_name>/ with dtx + bgm + kit wavs (+ optional jacket
    image), then zip it. dtx_name / set_label / set_slot follow the DTXMania difficulty-tier
    convention (e.g. ext.dtx in set.def slot L3 labelled EXTREME)."""
    import shutil
    folder = os.path.join(out_dir, song_name)
    os.makedirs(folder, exist_ok=True)
    for f in os.listdir(folder):
        try: os.remove(os.path.join(folder, f))
        except OSError: pass
    with open(os.path.join(folder, dtx_name), "w", encoding="shift_jis", errors="replace") as fh:
        fh.write(dtx_text)
    # set.def -- place the chart in its difficulty slot with the tier label
    with open(os.path.join(folder, "set.def"), "w", encoding="shift_jis", errors="replace") as fh:
        fh.write(f"#TITLE {song_name}\n#L{set_slot}LABEL {set_label}\n#L{set_slot}FILE {dtx_name}\n")
    # bgm
    shutil.copy2(bgm_src, os.path.join(folder, os.path.basename(bgm_src)))
    # jacket image (optional -- referenced by #PREIMAGE)
    if image_src and os.path.exists(image_src):
        shutil.copy2(image_src, os.path.join(folder, os.path.basename(image_src)))
    # kit
    for lab, fn in kit_files.items():
        shutil.copy2(os.path.join(kit_dir, fn), os.path.join(folder, fn))
    # zip
    zpath = os.path.join(out_dir, song_name + ".zip")
    if os.path.exists(zpath):
        try: os.remove(zpath)
        except OSError: pass
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(folder)):
            z.write(os.path.join(folder, f), os.path.join(song_name, f))
    return folder, zpath
