"""Full-kit audio transcription (beta).

Separates an isolated drum stem into per-instrument sub-stems with a neural model,
then onset-detects each sub-stem and sub-classifies toms (by pitch) and cymbals
(crash/ride/hat) into DTX lanes. This recovers toms and ride - which the single
band-heuristic path (transcribe.from_audio_drums) cannot.

Engines:
  * 'inagoy'  - DrumSep HDemucs, 4 stems (kick/snare/toms/cymbals; hats live in the
                cymbals stem). ~160 MB, loads via the demucs library we already ship.
  * 'larsnet' - 5 stems (kick/snare/toms/hihat/cymbals). ~562 MB, vendored U-Nets.

Model weights are downloaded on first use to %LOCALAPPDATA%/DTXScribe/models - they
are NOT bundled or redistributed. Licenses: inagoy DrumSep (unstated; personal use),
LarsNet (CC BY-NC 4.0).
"""
import os, wave, urllib.request, numpy as np
from fractions import Fraction
from . import dtx, transcribe as T


# ----------------------------------------------------------------------------- paths
def models_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    d = os.path.join(base, "DTXScribe", "models")
    os.makedirs(d, exist_ok=True)
    return d


def _download(url, dst, progress=None, label="model"):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    if progress:
        progress(f"Downloading {label} (first use only)...")
    req = urllib.request.Request(url, headers={"User-Agent": "DTXScribe"})
    with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        got = 0; next_mark = 20 * 1024 * 1024
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk); got += len(chunk)
            if progress and got >= next_mark:
                pct = f" ({got*100//total}%)" if total else ""
                progress(f"  {label}: {got//(1024*1024)} MB{pct}")
                next_mark += 20 * 1024 * 1024
    os.replace(tmp, dst)
    if progress:
        progress(f"  {label}: download complete ({got//(1024*1024)} MB).")
    return dst


# ----------------------------------------------------------------------------- audio io
def _read_stereo(path, target_sr=44100):
    """Return (channels=2, samples) float32 at native rate; caller assumes 44100."""
    with wave.open(path, "r") as w:
        sr = w.getframerate(); ch = w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    x = x.reshape(-1, ch).T if ch > 1 else x.reshape(1, -1)
    if x.shape[0] == 1:
        x = np.vstack([x, x])
    return x, sr


# Cymbal precision guard (Option A). GITADORA charts use ONLY the crash lane (the ride lane
# 19 is unused across the corpus), so every cymbal-stem onset is charted as a crash. Crashes
# are accents that survive downstream de-confliction, so to avoid charting the heavy bleed in
# the separated cymbals stem as phantom crashes, an onset is kept only if it lands on a
# musical accent -- coincident with a kick/snare hit -- OR is a prominent transient. Real
# crashes accent the beat; bleed rings between the hits. (Tuned on real GITADORA charts.)
_CRASH_COINC = 0.045      # kick/snare coincidence window (s)
_CRASH_PROM_Q = 0.88      # keep an isolated onset only above this onset-peak quantile (loud crash)
_CRASH_LED_RATIO = 1.5    # if cymbal onsets exceed hi-hat onsets by this, cymbals ARE the
                          # groove (a ride/crash timekeeper) -> keep them all, skip the guard


# ----------------------------------------------------------------------------- engine: inagoy
INAGOY_URL = ("https://github.com/ZFTurbo/Music-Source-Separation-Training/"
              "releases/download/v1.0.5/model_drumsep.th")
# the checkpoint labels its sources in Spanish
INAGOY_SRCMAP = {"bombo": "kick", "redoblante": "snare", "platillos": "cymbals", "toms": "toms"}


def _separate_inagoy(drum_wav, progress=None):
    import torch
    from demucs.states import load_model
    from demucs.apply import apply_model
    path = os.path.join(models_dir(), "inagoy", "model_drumsep.th")
    if not os.path.exists(path):
        _download(INAGOY_URL, path, progress, "inagoy DrumSep model (~160 MB)")
    if progress:
        progress("Loading inagoy DrumSep...")
    model = load_model(path); model.eval()
    x, sr = _read_stereo(drum_wav)
    mix = torch.from_numpy(x).unsqueeze(0)
    if progress:
        progress("Separating kick / snare / toms / cymbals...")
    with torch.no_grad():
        out = apply_model(model, mix, shifts=1, split=True, overlap=0.25, progress=False)[0]
    stems = {}
    for i, name in enumerate(model.sources):
        canon = INAGOY_SRCMAP.get(str(name).lower(), str(name).lower())
        stems[canon] = out[i].mean(0).cpu().numpy()          # mono
    return stems, sr, False        # has_isolated_hat = False (hats are inside 'cymbals')


# ----------------------------------------------------------------------------- engine: larsnet
def _separate_larsnet(drum_wav, progress=None):
    from . import larsnet_engine
    return larsnet_engine.separate(drum_wav, models_dir(), _download, _read_stereo, progress)


ENGINES = {
    "inagoy": _separate_inagoy,
    "larsnet": _separate_larsnet,
}


# ----------------------------------------------------------------------------- onset + classify
def _onset_times(x, sr, min_gap=0.06, thr_rel=0.05, thr_abs=0.06):
    """Broadband spectral-flux onsets on an isolated sub-stem -> list of (time_s, peak)."""
    envs, fps = T._band_envs(x, sr, [(20, sr / 2)])
    env = envs[0]
    peaks = T._pick(env, fps, min_gap=min_gap, thr_rel=thr_rel, thr_abs=thr_abs)
    return [(p / fps, env[p]) for p in peaks], env, fps


def _fundamental(seg, sr, lo=45, hi=400):
    """Autocorrelation pitch estimate (Hz) for a tom hit; 0 if unclear."""
    seg = seg - seg.mean()
    if len(seg) < 64:
        return 0.0
    ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
    lo_lag = max(1, int(sr / hi)); hi_lag = min(len(ac) - 1, int(sr / lo))
    if hi_lag <= lo_lag:
        return 0.0
    i = int(np.argmax(ac[lo_lag:hi_lag])) + lo_lag
    return sr / i if i > 0 else 0.0


def _tom_lane(freq):
    """Fundamental Hz -> GM tom: floor(41) / low-mid(47) / high(48)."""
    if freq <= 0:
        return 47
    if freq < 110:
        return 41
    if freq < 190:
        return 47
    return 48


_TOM_PITCH_RANK = {41: 0, 47: 1, 48: 2}             # floor < low-mid < high


def _interp_zeros(freqs):
    """Fill unclear (0 Hz) pitch estimates by linear interpolation between the nearest
    resolved neighbours so a single dropped read does not break a fill's contour."""
    n = len(freqs)
    f = [float(v) for v in freqs]
    known = [i for i in range(n) if f[i] > 0]
    if not known:
        return f
    for i in range(n):
        if f[i] > 0:
            continue
        left = max((k for k in known if k < i), default=None)
        right = min((k for k in known if k > i), default=None)
        if left is None:
            f[i] = f[right]
        elif right is None:
            f[i] = f[left]
        else:
            span = right - left
            f[i] = f[left] + (f[right] - f[left]) * (i - left) / span
    return f


def _pava(y):
    """Pool-adjacent-violators: least-squares best NON-DECREASING fit to y."""
    val, wt, ln = [], [], []
    for v in y:
        v = float(v); w = 1.0; length = 1
        while val and val[-1] > v:                   # order violation -> merge blocks
            pv = val.pop(); pw = wt.pop(); pl = ln.pop()
            v = (v * w + pv * pw) / (w + pw); w += pw; length += pl
        val.append(v); wt.append(w); ln.append(length)
    out = []
    for v, length in zip(val, ln):
        out.extend([v] * length)
    return out


def _monotone_fit(f):
    """Best monotone fit to pitch sequence f -> (fit, residual): whichever of the best
    non-decreasing (ascending) or non-increasing (descending) staircase has the smaller
    least-squares residual. Direction follows the detected pitch trend, so a real
    ascending fill stays ascending and a descending one stays descending; only the
    per-hit pitch noise around that trend is smoothed out."""
    inc = _pava(f)
    dec = [-v for v in _pava([-v for v in f])]       # best non-increasing
    res_inc = sum((a - b) ** 2 for a, b in zip(f, inc))
    res_dec = sum((a - b) ** 2 for a, b in zip(f, dec))
    if res_inc <= res_dec:
        return inc, res_inc
    return dec, res_dec


def _revoice_run(seg_freqs, base_lanes, resid_ratio=0.5):
    """Given one tom run's per-hit pitches and its baseline lanes, return a cleaned
    lane list. If the run is clearly monotone (a real descending/ascending fill buried
    under per-hit pitch noise), snap it to a clean staircase using exactly the same set
    of toms the baseline used. Repeated single-tom runs, genuine alternation and true
    scatter fail the monotone test and are returned unchanged."""
    k = len(set(base_lanes))
    if k < 2:
        return base_lanes                            # repeated single tom -> leave
    f = _interp_zeros(seg_freqs)
    mean = sum(f) / len(f)
    raw_var = sum((v - mean) ** 2 for v in f)
    if raw_var < 1e-6:
        return base_lanes                            # flat pitch -> not directional
    fit, resid = _monotone_fit(f)
    if resid / raw_var > resid_ratio:
        return base_lanes                            # not monotone (scatter/alternation)
    present = sorted(set(base_lanes), key=lambda L: _TOM_PITCH_RANK[L])   # low..high pitch
    thresholds = [np.percentile(fit, 100.0 * b / k) for b in range(1, k)]
    out = []
    for v in fit:
        band = sum(1 for th in thresholds if v > th)
        out.append(present[min(band, k - 1)])
    return out


def _tom_contour_pass(cands, out, gap=0.30, min_len=3):
    """Re-voice tom FILLS toward an idiomatic contour without moving any onset.
    A fill = >=min_len consecutive toms each within `gap` seconds. Corpus grounding:
    ~62% of real GITADORA tom fills are descending/mostly-descending, so a directional
    run scrambled by noisy per-hit pitch is snapped clean; non-directional runs (single
    tom, alternation, genuine scatter) are left exactly as detected."""
    n = len(out)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and cands[j + 1][0] - cands[j][0] <= gap:
            j += 1
        if j - i + 1 >= min_len:
            seg_freqs = [f for _, f in cands[i:j + 1]]
            base_lanes = [lane for _, lane in out[i:j + 1]]
            new_lanes = _revoice_run(seg_freqs, base_lanes)
            for idx, lane in enumerate(new_lanes):
                out[i + idx] = (out[i + idx][0], lane)
        i = j + 1
    return out


def _assign_toms(cands):
    """Toms are isolated so onsets are reliable, but absolute pitch varies by kit.
    Split high/low/floor adaptively by the terciles of THIS song's tom fundamentals;
    if the pitch spread is too small (really one tom), keep them all on low-mid tom.
    A final contour pass re-voices fills toward the idiomatic descending shape."""
    if not cands:
        return []
    freqs = [f for _, f in cands if f > 0]
    if len(freqs) < 6 or (max(freqs) - min(freqs) < 45):
        return [(t, 47) for t, _ in cands]          # not enough spread -> single tom
    lo = float(np.percentile(freqs, 33)); hi = float(np.percentile(freqs, 66))
    out = []
    for t, f in cands:
        if f <= 0:
            lane = 47
        elif f < lo:
            lane = 41                                # lowest pitch -> floor tom
        elif f < hi:
            lane = 47                                # low-mid tom
        else:
            lane = 48                                # highest pitch -> high tom
        out.append((t, lane))
    return _tom_contour_pass(cands, out)


def _spectral(seg, sr):
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) if len(seg) >= 32 else np.array([1.0])
    freqs = np.fft.rfftfreq(len(seg), 1 / sr) if len(seg) >= 32 else np.array([0.0])
    tot = X.sum() + 1e-9
    centroid = float((freqs * X).sum() / tot)
    return centroid


def _classify_cymbal(x, sr, p_time, isolated_hat):
    """Classify one cymbal-stem hit into a GM midi number.

    isolated_hat=True  (LarsNet): the hi-hat lives in its own stem, so this stem is
        crash + ride only -> split crash (long wash) vs ride (shorter metallic ping).
    isolated_hat=False (inagoy): this stem is hi-hat + crash + ride mixed. We can only
        reliably pull out the loud, long crashes; the rest read as closed hi-hat.
        Ride is NOT separable here (documented limitation of the lite engine)."""
    s0 = int(p_time * sr)
    seg = x[s0:s0 + int(0.05 * sr)]
    if len(seg) < 32:
        return 42 if not isolated_hat else 49
    tail = x[s0 + int(0.08 * sr): s0 + int(0.40 * sr)]
    peak = float(np.max(np.abs(x[s0:s0 + int(0.03 * sr)])) or 1e-9)
    sustain = float(np.sqrt((tail ** 2).mean())) / peak if tail.size else 0.0
    if isolated_hat:
        # GITADORA charts use only the crash lane (the ride lane is unused across the whole
        # corpus), so a cymbal-stem onset is charted as a crash rather than split to ride.
        return 49                       # crash
    # inagoy combined stem: conservative crash gate (from First Date feature analysis:
    # sustain>0.35 & peak>0.08 -> ~4% of hits, matching real crash frequency).
    if sustain > 0.35 and peak > 0.08:
        return 49                       # crash
    return 42                           # closed hi-hat


def _add_cymbals(stems, sr, hits, has_isolated_hat):
    """Detect cymbal-stem onsets and append the ones that pass the precision guard as
    crashes. The separated cymbals stem carries heavy bleed (other cymbals ringing, metallic
    hi-hat, snare spill) -- ~3x more onsets than real crashes -- and since crashes are
    preserved downstream, charting them all would inflate the cymbal lane. Real crashes accent
    the beat (they co-occur with a kick or snare), so an onset is kept only when it is
    coincident with a kick/snare hit OR is a loud isolated transient (top ``_CRASH_PROM_Q``
    onset-peak quantile). Mutates ``hits``; returns notes kept."""
    import bisect
    x = stems.get("cymbals")
    if x is None or not np.any(x):
        return 0
    ons, _, _ = _onset_times(x, sr, min_gap=0.06, thr_rel=0.06, thr_abs=0.09)
    if not ons:
        return 0
    ks = sorted(t for t, m in hits if m in (35, 36, 38))     # kick + snare accents
    hat_n = sum(1 for _t, m in hits if m in (42, 46))        # detected hi-hat onsets
    # When cymbals outnumber the hi-hat they ARE the timekeeper (a ride/crash groove), not
    # bleed -- keep them all, since the accent guard would wrongly thin a real cymbal
    # timekeeping line (e.g. Meikyou Shisui: 436 cymbals vs 19 hi-hats).
    cymbal_led = len(ons) > max(hat_n, 1) * _CRASH_LED_RATIO
    peaks = [pk for _t, pk in ons]
    prom = float(np.quantile(peaks, _CRASH_PROM_Q)) if peaks else 0.0
    kept = 0
    for t, pk in ons:
        if not cymbal_led:
            coincident = False
            if ks:
                j = bisect.bisect_left(ks, t)
                for k in (j - 1, j):
                    if 0 <= k < len(ks) and abs(ks[k] - t) <= _CRASH_COINC:
                        coincident = True
                        break
            if not (coincident or pk >= prom):
                continue
        hits.append((t, _classify_cymbal(x, sr, t, has_isolated_hat)))
        kept += 1
    return kept


# --------------------------------------------------------------- per-song kit sampling
# One-shot lengths per lane (seconds), mirroring the synthesized fallback kit.
_SAMPLE_DUR = {"bd": 0.30, "sd": 0.22, "ht": 0.34, "lt": 0.35, "ft": 0.40,
               "hh": 0.09, "ho": 0.30, "cy": 0.85, "rd": 0.48}
_SAMPLE_MIN_HITS = 2        # need at least this many detected hits to trust a lane
_SAMPLE_PEAK_FLOOR = 0.0003 # only rejects a digitally-silent/empty stem; separated stems
                            # are quiet in absolute terms, and every slice is normalized,
                            # so absolute loudness is NOT a quality signal here.
_SAMPLE_ATTACK_MIN = 1.4    # THE quality gate: the peak must rise this sharply over the
                            # 6 ms before it. A real hit (even a soft, sparse tom) clears
                            # ~1.5; pure bleed/noise/silence stays near 1.0. Density-
                            # agnostic, so a fast lane is never penalized for close hits.

_SAMPLE_DEBUG = os.environ.get("DTX_SAMPLE_DEBUG")


def _stem_for_midi(m, has_isolated_hat):
    """Which separated stem a GM-midi hit was detected in (mirrors transcribe_stems)."""
    if m in (35, 36): return "kick"
    if m in (37, 38, 40): return "snare"
    if m in (41, 43, 45, 47, 48, 50): return "toms"
    if m in (42, 44, 46): return "hihat" if has_isolated_hat else "cymbals"
    return "cymbals"                                    # crash / ride / bell


def _pick_cleanest(times, x, sr):
    """Among candidate onset times pick the loudest, most time-isolated instance (largest
    gap before it -> the slice won't start mid-decay of a previous hit). Returns
    (isolation, peak_index, peak_amp, attack) or None. `attack` (peak over the 6 ms just
    before the transient) measures onset crispness and is used only for the quality gate."""
    best = None
    for t in times[:80]:
        c = int(t * sr)
        a = max(0, c - int(0.003 * sr)); b = min(len(x), c + int(0.012 * sr))
        if b <= a:
            continue
        pk = a + int(np.argmax(np.abs(x[a:b]))); peak = float(abs(x[pk]))
        l0 = max(0, pk - int(0.040 * sr)); l1 = max(0, pk - int(0.005 * sr))
        lead = float(np.sqrt((x[l0:l1] ** 2).mean())) if l1 > l0 else 0.0
        a0 = max(0, pk - int(0.006 * sr)); a1 = max(0, pk - int(0.001 * sr))
        atk_pre = float(np.sqrt((x[a0:a1] ** 2).mean())) if a1 > a0 else 0.0
        isolation = peak / (lead + 1e-4)
        attack = peak / (atk_pre + 1e-4)
        if best is None or isolation > best[0]:
            best = (isolation, pk, peak, attack)
    return best


def extract_kit_samples(stems, sr, hits, has_isolated_hat):
    """Slice a clean one-shot per lane straight from this song's isolated stems (so toms,
    snare, etc. sound like the real kit). Hybrid: only lanes with a confidently crisp,
    loud hit are returned; the caller keeps the synth sample for every other lane."""
    from collections import defaultdict
    by_lane = defaultdict(list)
    for t, m in hits:
        lab = dtx.MAP.get(m, (None, None))[1]
        if lab not in _SAMPLE_DUR:
            continue
        by_lane[lab].append((t, _stem_for_midi(m, has_isolated_hat)))
    samples = {}
    for lab, cand in by_lane.items():
        n_hits = len(cand)
        x = stems.get(cand[0][1]) if cand else None
        best = _pick_cleanest([t for t, _ in cand], x, sr) if (x is not None and np.any(x)) else None
        passed = False
        if best is not None and n_hits >= _SAMPLE_MIN_HITS:
            isolation, pk, peak, attack = best
            if peak >= _SAMPLE_PEAK_FLOOR and attack >= _SAMPLE_ATTACK_MIN:
                dn = int(_SAMPLE_DUR[lab] * sr)
                start = max(0, pk - int(0.002 * sr))
                seg = x[start:start + dn].astype(np.float64).copy()
                if len(seg) >= int(0.02 * sr):
                    fi = max(1, int(0.0015 * sr)); seg[:fi] *= np.linspace(0, 1, fi)
                    fo = max(1, int(len(seg) * 0.30)); seg[-fo:] *= np.linspace(1, 0, fo) ** 1.5
                    mx = float(np.max(np.abs(seg))) or 1.0
                    samples[lab] = seg / mx * 0.9
                    passed = True
        if _SAMPLE_DEBUG:
            if best is not None:
                iso, _pk, pk_a, atk = best
                print(f"[sample] {lab}: hits={n_hits} peak={pk_a:.3f} attack={atk:.2f} "
                      f"iso={iso:.2f} -> {'SAMPLE' if passed else 'synth'}", flush=True)
            else:
                print(f"[sample] {lab}: hits={n_hits} (no usable stem) -> synth", flush=True)
    return samples


def save_oneshot(path, seg, sr=44100):
    """Write a float one-shot as 44.1k/16-bit mono WAV (same format as the synth kit)."""
    data = (np.clip(np.asarray(seg, dtype=np.float64), -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(sr))
        w.writeframes(data.tobytes())


def transcribe_stems(stems, sr, bpm=None, progress=None, has_isolated_hat=False, standardize=True):
    """Per-stem onset detection + sub-classification -> (events, barlens, bpm, anchor).
    Same event structure as transcribe.from_audio_drums so the pipeline is unchanged."""
    hits = []   # (time_s, GM-midi)
    tom_cands = []   # (time_s, fundamental_hz) resolved to lanes after collection

    def add(stem, midi_fixed=None, kind=None):
        x = stems.get(stem)
        if x is None or not np.any(x):
            return
        # refractory gap + detection floor per stem. Toms and cymbals bleed from the
        # louder drums, so they get a longer refractory and a higher floor to suppress
        # phantom hits (the "impossible tom run" cause) before standardize runs.
        gaps = {"kick": 0.09, "snare": 0.08, "toms": 0.11, "hihat": 0.05, "cymbals": 0.06}
        thr = {"toms": (0.07, 0.10), "cymbals": (0.06, 0.09), "hihat": (0.05, 0.07)}
        tr, ta = thr.get(stem, (0.05, 0.06))
        ons, _, _ = _onset_times(x, sr, min_gap=gaps.get(stem, 0.06), thr_rel=tr, thr_abs=ta)
        for t, _pk in ons:
            if kind == "tom":
                s0 = int(t * sr); seg = x[s0:s0 + int(0.06 * sr)]
                tom_cands.append((t, _fundamental(seg, sr)))
            elif kind == "hihat":
                s0 = int(t * sr)
                tail = x[s0 + int(0.06 * sr): s0 + int(0.30 * sr)]
                peak = float(np.max(np.abs(x[s0:s0 + int(0.03 * sr)])) or 1e-9)
                sus = float(np.sqrt((tail ** 2).mean())) / peak if tail.size else 0.0
                hits.append((t, 46 if sus > 0.35 else 42))     # open vs closed
            else:
                hits.append((t, midi_fixed))

    if progress:
        progress("Detecting onsets per instrument...")
    add("kick", midi_fixed=36)
    add("snare", midi_fixed=38)
    add("toms", kind="tom")
    for t, midi in _assign_toms(tom_cands):
        hits.append((t, midi))
    if has_isolated_hat:
        add("hihat", kind="hihat")
    _add_cymbals(stems, sr, hits, has_isolated_hat)

    if not hits:
        return [{}], [Fraction(1)], round(bpm or 120.0, 3), 0.0, {}, []

    # tempo from the kick+snare backbone if not supplied
    if bpm is None:
        kx = stems.get("kick"); sx = stems.get("snare")
        ref = None
        for a in (kx, sx):
            if a is not None and np.any(a):
                e, fps = T._band_envs(a, sr, [(20, sr / 2)])
                ref = e[0] if ref is None else ref + e[0]
        bpm = T._estimate_bpm(ref, fps) if ref is not None else 120.0

    # Per-song drum voicing: slice a clean one-shot per lane from the isolated stems so
    # the chart plays this song's actual drums (hybrid - synth fallback per missing lane).
    samples = extract_kit_samples(stems, sr, hits, has_isolated_hat)

    # Standardize (default): quantize to a musical 1/16 grid, de-dupe, and cap
    # simultaneous voices so the raw onsets become a clean, playable chart. When
    # standardize is off, emit exactly what was heard on the fine 1/64 grid with no
    # voice cap - the raw first-pass transcription.
    from . import standardize as _std
    if standardize:
        events, barlens, anchor = _std.build_events(hits, bpm, max_hand_voices=2, adaptive=True)
    else:
        events, barlens, anchor = _std.build_events(hits, bpm, grid_div=64, max_hand_voices=999)
    onsets = _std.map_onsets(hits, bpm, anchor)
    return events, barlens, round(bpm, 3), anchor, samples, onsets


def from_audio_fullkit(drum_wav, bpm=None, progress=None, standardize=True):
    """Automatic dual-engine full-kit transcription - no user selection.

    Runs BOTH separators and lets each own the lanes it is strongest at, since they
    are complementary:
        * inagoy (htdemucs)  -> kick, snare, toms        (the drum bodies)
        * LarsNet (U-Nets)   -> closed hat, open hat, ride, crash  (metals + hats)

    LarsNet uniquely isolates the hi-hat into its own stem, which is what makes ride
    recoverable; inagoy's htdemucs is a strong separator for the membrane drums and
    reuses the demucs runtime we already load. Combining them yields a fuller kit
    than either alone. Degrades gracefully: if one engine is unavailable the other
    covers what it can; if both fail the caller falls back to the fast heuristic.
    """
    ina = lars = None
    ina_err = lars_err = None
    try:
        if progress: progress("Full-kit engine 1/2: inagoy (kick / snare / toms)...")
        ina, ina_sr, _ = _separate_inagoy(drum_wav, progress=progress)
    except Exception as e:
        ina_err = str(e)[:120]
        if progress: progress(f"  inagoy unavailable: {ina_err}")
    try:
        if progress: progress("Full-kit engine 2/2: LarsNet (hi-hat / ride / crash)...")
        lars, lars_sr, _ = _separate_larsnet(drum_wav, progress=progress)
    except Exception as e:
        lars_err = str(e)[:120]
        if progress: progress(f"  LarsNet unavailable: {lars_err}")

    if ina is None and lars is None:
        raise RuntimeError(f"both full-kit engines failed (inagoy: {ina_err}; larsnet: {lars_err})")

    # Fuse: bodies from inagoy, metals+hats from LarsNet. Fall back per-family.
    stems = {}
    if ina is not None and lars is not None:
        sr = ina_sr
        for k in ("kick", "snare", "toms"):
            stems[k] = ina.get(k)                    # inagoy owns the drum bodies
        stems["hihat"] = lars.get("hihat")           # LarsNet owns the metals + hats
        stems["cymbals"] = lars.get("cymbals")
        isolated_hat = True
        if progress: progress("Fusing engines: bodies from inagoy, hats/ride/crash from LarsNet.")
    elif lars is not None:
        sr = lars_sr; stems = lars; isolated_hat = True
        if progress: progress("Using LarsNet only (inagoy unavailable).")
    else:
        sr = ina_sr; stems = ina; isolated_hat = False
        if progress: progress("Using inagoy only (LarsNet unavailable, no ride).")

    return transcribe_stems(stems, sr, bpm=bpm, progress=progress,
                            has_isolated_hat=isolated_hat, standardize=standardize)
