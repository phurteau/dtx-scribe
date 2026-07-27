"""Transcription paths -> (events, barlens, bpm). All produce the same event
structure consumed by dtx.emit_dtx, so no manual notation is ever required."""
import os, re, wave, numpy as np
from fractions import Fraction
from . import dtx

# ---------------- Tab: Songsterr ----------------
def from_songsterr(measures):
    events, barlens = dtx.events_from_tab(measures)
    return events, barlens


# ---------------- Tab: MIDI upload ----------------
def from_midi(path, default_bpm=120):
    """Parse a MIDI drum track (channel 9 / GM percussion) -> events, barlens, bpm."""
    import mido
    mid = mido.MidiFile(path)
    tpb = mid.ticks_per_beat
    # gather tempo + time-sig + drum note-ons on absolute ticks
    tempo = mido.bpm2tempo(default_bpm); bpm = default_bpm
    sig = (4, 4)
    notes = []  # (abs_tick, midi_note)
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type == "set_tempo":
                tempo = msg.tempo; bpm = mido.tempo2bpm(tempo)
            elif msg.type == "time_signature":
                sig = (msg.numerator, msg.denominator)
            elif msg.type == "note_on" and msg.velocity > 0 and getattr(msg, "channel", 9) == 9:
                notes.append((t, msg.note))
    if not notes:
        raise RuntimeError("No GM drum (channel 10) note-ons found in this MIDI.")
    ticks_per_bar = tpb * 4 * sig[0] / sig[1]
    n_bars = int(max(t for t, _ in notes) // ticks_per_bar) + 1
    events = [dict() for _ in range(n_bars)]
    bar_slots = max(1, round(float(Fraction(sig[0], sig[1])) * dtx.GRID))
    for tick, note in notes:
        if note not in dtx.MAP:
            continue
        mi = int(tick // ticks_per_bar)
        frac_in_bar = (tick - mi * ticks_per_bar) / ticks_per_bar  # 0..1
        slot = int(round(frac_in_bar * bar_slots))
        if slot >= bar_slots:
            slot = bar_slots - 1
        ch, lab = dtx.MAP[note]
        events[mi].setdefault(ch, {}).setdefault(Fraction(slot, bar_slots), dtx.LABEL2SLOT[lab])
    barlens = [Fraction(sig[0], sig[1])] * n_bars
    return events, barlens, round(bpm, 3)


# ---------------- Tab: Guitar Pro (.gp3/.gp4/.gp5/.gpx/.gp) ----------------
def from_guitarpro(path):
    """Parse a Guitar Pro file's drum/percussion track -> events, barlens, bpm.
    Percussion tracks store the GM MIDI drum number as note.value, so the same
    GM->lane MAP used for Songsterr applies directly."""
    import guitarpro
    song = guitarpro.parse(path)
    bpm = float(song.tempo or 120)
    # choose the drum track: explicit percussion flag, else GM drum channel (9), else first
    track = None
    for t in song.tracks:
        if getattr(t, "isPercussionTrack", False):
            track = t; break
    if track is None:
        for t in song.tracks:
            ch = getattr(t, "channel", None)
            if ch is not None and getattr(ch, "channel", None) == 9:
                track = t; break
    if track is None:
        track = song.tracks[0]

    events, barlens = [], []
    for m in track.measures:
        ts = m.header.timeSignature
        sig = (ts.numerator, ts.denominator.value)
        nominal = Fraction(sig[0], sig[1])
        bar_slots = max(1, round(float(nominal) * dtx.GRID))
        chan = {}
        # a measure may have multiple voices; merge them onto the same grid
        for v in m.voices:
            cum = Fraction(0)
            for b in v.beats:
                d = b.duration
                dur = Fraction(1, d.value)
                if getattr(d, "isDotted", False):
                    dur *= Fraction(3, 2)
                tup = getattr(d, "tuplet", None)
                if tup is not None and (tup.enters, tup.times) != (1, 1):
                    dur *= Fraction(tup.times, tup.enters)
                status = str(getattr(b, "status", ""))
                if "empty" not in status and "rest" not in status:
                    slot = int(round(float(cum) * dtx.GRID))
                    if slot >= bar_slots:
                        slot = bar_slots - 1
                    pos = Fraction(slot, bar_slots)
                    for n in b.notes:
                        val = getattr(n, "value", None)
                        if val in dtx.MAP:
                            ch, lab = dtx.MAP[val]
                            chan.setdefault(ch, {}).setdefault(pos, dtx.LABEL2SLOT[lab])
                cum += dur
        events.append(chan)
        barlens.append(nominal)
    if not any(events):
        raise RuntimeError("No drum notes found in this Guitar Pro file "
                           "(is there a percussion track?).")
    return events, barlens, round(bpm, 3)


# ---------------- Tab: generic ASCII drum tab ----------------
# maps common ASCII drum-tab row labels -> GM MIDI drum number
_ASCII_LANES = {
    "cc": 49, "c": 49, "cr": 49, "cra": 49, "crash": 49, "cy": 49,
    "rd": 51, "ri": 51, "ride": 51, "r": 51,
    "hh": 42, "h": 42, "hc": 42, "hi-hat": 42, "hihat": 42, "hats": 42, "hat": 42,
    "ho": 46, "oh": 46, "open": 46,
    "hf": 44, "fh": 44, "hhf": 44, "pedal": 44,
    "sd": 38, "s": 38, "sn": 38, "snare": 38, "sr": 38,
    "t1": 48, "t2": 47, "t3": 45, "ht": 48, "mt": 47, "lt": 45,
    "tom": 47, "tt": 48, "rack": 48,
    "ft": 41, "f": 41, "floor": 41, "flt": 41,
    "bd": 36, "b": 36, "k": 36, "kick": 36, "bass": 36, "kd": 36,
}
# characters that count as a hit
_HIT_CHARS = set("xXoOgGdDbBfF#@*")


def from_ascii_tab(text, bpm=120, beats_per_measure=4):
    """Parse a generic ASCII drum tab (rows like 'HH|x-x-x-x-|') into events.
    Groups consecutive labelled rows into staff blocks; each block is one line of
    music read left→right. Column count per block sets the subdivision."""
    lines = text.replace("\r", "").split("\n")
    blocks = []          # list of list[(label,row)]
    cur = []
    for ln in lines:
        mrow = re.match(r"\s*([A-Za-z][A-Za-z0-9#\-]{0,6})\s*[|:]", ln)
        if mrow and "|" in ln:
            label = mrow.group(1).strip().lower().rstrip("-")
            body = ln[ln.index(mrow.group(1)) + len(mrow.group(1)):]
            # take content between first and last bar marker
            body = body[body.index("|") if "|" in body else 0:]
            cur.append((label, body))
        else:
            if cur:
                blocks.append(cur); cur = []
    if cur:
        blocks.append(cur)
    if not blocks:
        raise RuntimeError("No ASCII drum-tab rows found (expected lines like 'HH|x-x-x-x-|').")

    events, barlens = [], []
    nominal = Fraction(beats_per_measure, 4)
    for block in blocks:
        # normalize: strip bar chars, keep hit columns; align to max width
        rows = []
        for label, body in block:
            cells = [c for c in body if c not in " "]
            # split into measures on '|'
            rows.append((label, body))
        # determine columns from the longest row's non-bar length
        # build a merged column timeline using '|' as measure boundaries from first row
        ref = block[0][1]
        # positions of characters that are not bar lines
        # We treat each measure (between |) separately.
        # Build measure segments from ref row.
        def segments(s):
            segs, cur = [], ""
            started = False
            for ch in s:
                if ch == "|":
                    if started:
                        segs.append(cur)
                    cur = ""; started = True
                else:
                    cur += ch
            return [seg for seg in segs if seg.strip("-") != "" or True]
        seg_lists = {label: segments(body) for label, body in block}
        nseg = max(len(v) for v in seg_lists.values())
        for si in range(nseg):
            width = max((len(seg_lists[l][si]) for l in seg_lists if si < len(seg_lists[l])), default=0)
            if width == 0:
                continue
            bar_slots = max(1, round(float(nominal) * dtx.GRID))
            chan = {}
            for label, segs in seg_lists.items():
                if si >= len(segs):
                    continue
                seg = segs[si]
                midi = _ASCII_LANES.get(label)
                if midi is None or midi not in dtx.MAP:
                    continue
                ch, lab = dtx.MAP[midi]
                for col, chx in enumerate(seg):
                    if chx in _HIT_CHARS:
                        frac = col / width
                        slot = int(round(frac * bar_slots))
                        if slot >= bar_slots:
                            slot = bar_slots - 1
                        chan.setdefault(ch, {}).setdefault(Fraction(slot, bar_slots), dtx.LABEL2SLOT[lab])
            events.append(chan)
            barlens.append(nominal)
    if not any(events):
        raise RuntimeError("ASCII tab parsed but no recognizable drum hits were found.")
    return events, barlens, round(float(bpm), 3)


# ---------------- Audio-only (beta) ----------------
def _read_mono(path):
    with wave.open(path, "r") as w:
        sr = w.getframerate(); ch = w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    if ch == 2:
        x = x.reshape(-1, 2).mean(axis=1)
    return x, sr

def _band_envs(x, sr, bands, hop=512, win=2048):
    """One STFT pass -> a positive-spectral-flux onset envelope per frequency band.
    Detecting each drum in its own band lets simultaneous hits (kick+snare+hat on the
    same beat) all register, which a single onset+classify pass cannot do."""
    wnd = np.hanning(win)
    nfr = max(0, (len(x) - win) // hop)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    masks = [(freqs >= lo) & (freqs < hi) for (lo, hi) in bands]
    envs = [np.zeros(nfr) for _ in bands]
    prev = [None] * len(bands)
    for i in range(nfr):
        mag = np.abs(np.fft.rfft(x[i*hop:i*hop+win] * wnd))
        for b, mask in enumerate(masks):
            s = mag[mask]
            if prev[b] is not None:
                d = s - prev[b]
                envs[b][i] = float(d[d > 0].sum())
            prev[b] = s
    for b in range(len(bands)):
        mx = envs[b].max() or 1.0
        envs[b] /= mx
    return envs, sr / hop


# Corpus tempo prior, mined from 8,105 real DTXMania / GITADORA charts across all 31
# mixes through GALAXY WAVE DELTA (files/bpm_prior.py). The charted #BPM distribution:
# median 170, p01 90, p99 280, with 80% of charts in 124-210. Real charts almost never
# live below ~90 or above ~280, and density peaks 170-190. We use this to resolve the
# octave ambiguity autocorrelation is prone to (locking onto a half-time backbeat or a
# double-time pulse): among the octave candidates we prefer the one that lands in the
# corpus's dense region, but only ever move off the detected tempo on real evidence.
_BPM_SANE_LO, _BPM_SANE_HI = 90.0, 280.0     # p01 .. p99 hard bounds
_BPM_DENSE_LO, _BPM_DENSE_HI = 124.0, 210.0  # 80% central mass


def _bpm_prior(bpm):
    """Corpus plausibility of a tempo: 1.0 inside the dense 80% band (124-210),
    tapering linearly to 0 at the p01/p99 hard bounds (90 / 280). A smooth trapezoid,
    not a hard gate, so a slightly-out-of-band real tempo is penalized, not killed."""
    if bpm <= _BPM_SANE_LO or bpm >= _BPM_SANE_HI:
        return 0.0
    if _BPM_DENSE_LO <= bpm <= _BPM_DENSE_HI:
        return 1.0
    if bpm < _BPM_DENSE_LO:
        return (bpm - _BPM_SANE_LO) / (_BPM_DENSE_LO - _BPM_SANE_LO)
    return (_BPM_SANE_HI - bpm) / (_BPM_SANE_HI - _BPM_DENSE_HI)


def _estimate_bpm(onset, fps, lo=70, hi=200):
    env = onset - onset.mean()
    ac = np.correlate(env, env, "full")[len(env)-1:]

    def score(bpm):
        i = int(round(60.0 / bpm * fps))
        return ac[i] if 1 <= i < len(ac) else 0.0

    best = (0.0, None)
    for bpm in np.arange(lo, hi, 0.25):
        s = score(bpm)
        if s > best[0]:
            best = (s, bpm)
    bpm = best[1] or 120.0
    base = best[0] or 1.0

    # Corpus-grounded octave correction. Score each octave candidate {T/2, T, 2T} by
    # how well the onset envelope supports it (autocorrelation, probed even beyond the
    # primary search bounds) times how plausible it is under the real-chart tempo prior.
    # The detected tempo T carries the full support weight, so a clean in-band read wins
    # ties and is never disturbed; a half/double only wins when its faster/slower pulse
    # is genuinely present AND far better supported by the corpus distribution (e.g. a
    # 190 BPM punk song detected at its 95 backbeat, or a 220 song caught at 110). If
    # nothing scores (a genuinely sparse, slow track), the raw pick is kept. A typed BPM
    # overrides all of this upstream.
    winner, win_score = bpm, _bpm_prior(bpm)
    for c in (bpm * 0.5, bpm * 2.0):
        if c < _BPM_SANE_LO or c > _BPM_SANE_HI:
            continue
        sc = (score(c) / base) * _bpm_prior(c) * 0.90  # home bias: move only on evidence
        if sc > win_score:
            winner, win_score = c, sc
    return winner if win_score > 0 else bpm


def _pick(env, fps, min_gap=0.06, thr_rel=0.06, thr_abs=0.08):
    """Local-maxima peak picker over an onset envelope with a moving-average floor
    and a refractory gap so one hit isn't counted twice."""
    nfr = len(env)
    if nfr < 3:
        return []
    win = max(1, int(0.25 * fps))
    mov = np.convolve(env, np.ones(win) / win, mode="same")
    gap = max(1, int(min_gap * fps))
    peaks = []; i = 1
    while i < nfr - 1:
        if (env[i] > env[i-1] and env[i] >= env[i+1]
                and env[i] > mov[i] + thr_rel and env[i] > thr_abs):
            peaks.append(i); i += gap
        else:
            i += 1
    return peaks


def from_audio_drums(drum_wav, bpm=None, progress=None, standardize=True):
    """Transcribe an isolated drum stem by per-band onset detection: kick (low),
    snare (mid), hi-hat/cymbal (high). Bright hits are split into hat vs crash by
    decay length. Beta quality - good groove skeleton, not a note-perfect chart."""
    if progress: progress("Analyzing drum stem (per-band onset detection, beta)...")
    x, sr = _read_mono(drum_wav)
    # (lo, hi) Hz per lane: kick, snare, hats/cymbals
    band_defs = [(30, 120), (200, 1600), (5000, sr / 2)]
    envs, fps = _band_envs(x, sr, band_defs)
    kick_env, snare_env, hat_env = envs
    if bpm is None:
        bpm = _estimate_bpm(kick_env + snare_env, fps)

    hits = []   # (frame_index, GM-midi)
    for p in _pick(kick_env, fps, min_gap=0.09, thr_rel=0.06, thr_abs=0.09):
        hits.append((p, 36))
    for p in _pick(snare_env, fps, min_gap=0.08, thr_rel=0.07, thr_abs=0.10):
        hits.append((p, 38))
    for p in _pick(hat_env, fps, min_gap=0.06, thr_rel=0.05, thr_abs=0.07):
        # hat vs crash: a crash is loud AND keeps ringing; a hat (even open) dies faster.
        # Bias toward hat - a chart peppered with crashes reads wrong.
        tail = hat_env[p + int(0.06 * fps): p + int(0.36 * fps)]
        sustained = tail.size > 0 and float(tail.mean()) > 0.17 and float(hat_env[p]) > 0.34
        hits.append((p, 49 if sustained else 42))

    if not hits:
        return [{}], [Fraction(1)], round(bpm, 3), 0.0

    # Convert frame-index hits to seconds, then standardize (quantize + de-dupe + cap)
    # so the fallback detector's onsets come out grid-locked and playable. When
    # standardize is off, emit the raw first pass (fine 1/64 grid, no voice cap).
    from . import standardize as _std
    sec_hits = [(p / fps, midi) for p, midi in hits]
    if standardize:
        events, barlens, anchor = _std.build_events(sec_hits, bpm, max_hand_voices=2, adaptive=True)
    else:
        events, barlens, anchor = _std.build_events(sec_hits, bpm, grid_div=64, max_hand_voices=999)
    return events, barlens, round(bpm, 3), anchor
