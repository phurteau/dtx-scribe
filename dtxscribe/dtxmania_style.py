"""Regularize a standardized chart into idiomatic DTXMania patterns ("DTXMania mode").

Raw/standardized audio transcription is faithful but reads "busy" -- timekeeping has
jitter and gaps that make a chart look randomly generated. Real DTXMania/GITADORA
charts read "produced": steady, evenly-spaced timekeeping and a consistent timekeeper
(hi-hat OR ride) within a section. This pass rewrites the timekeeping layer toward
those conventions.

Grounded in an analysis of 2000 real approved GITADORA charts (188,760 bars). The data
DEBUNKED two conventions this module used to enforce, which have been removed:
  * "one crash per bar" -- WRONG: crashes stack freely with kick (107k co-hits), snare
    (49k) and even other crashes (CY+LC). Crashes are now preserved as transcribed.
  * "crash on every phrase downbeat" -- WRONG: only 31% of 4-bar phrase downbeats carry
    a crash. No crashes are injected.

What the data CONFIRMED and this module keeps:
  1. One timekeeper at a time -- hi-hat and ride coexist in only ~0.1% of bars, so a
     redundant second timekeeper is dropped. Chosen once per SECTION (a run of bars),
     not per bar, so the timekeeper doesn't flip hi-hat/ride/hi-hat between neighbours.
  2. De-flam cymbals -- audio transcription splits a hard cymbal/hi-hat hit into a flam
     (a phantom second onset from decay / mic bleed). Real charts essentially never place
     two hits of the same cymbal under ~50-70 ms apart, so a sub-threshold same-lane
     cymbal/hi-hat pair is collapsed to the more on-grid hit. Toms/snare/kick are left
     alone (real fills, drags and double-bass play fast there).
  3. Jitter cleanup only -- a timekeeping line is snapped to the bar's OWN subdivision to
     remove timing jitter, but its note count is PRESERVED. It is never inflated to a
     per-tier grid: real charts of every difficulty are mostly quarter + 8th with 16th a
     minority (Extreme is only ~7% 16th) and mix note values freely bar to bar, so the
     density detected from the song is what the chart keeps.
  4. Closed hi-hat + crash on the same tick is a transcription artifact (3 in 160k real
     bars) -- the closed hi-hat is dropped there so the crash reads as the accent. (Open
     hi-hat under a crash is a real, if rare, technique and is left intact.)
  5. Snap groove, keep fills -- the steady backbone (kick + snare + hi-hat/ride) of a clean
     1/16 bar is matched to the nearest of a mined vocabulary of real grooves (see
     ``pattern_match`` / ``groove_data``) and replaced when the transcription is already
     close, so the timekeeping reads "produced". Tom fills, crashes, open hi-hat and feet
     are never touched, so the song's fills and accents survive verbatim.

Kick, snare, toms and crashes (the groove, fills and accents) are left as transcribed
-- only the hi-hat / ride timekeeping layer is de-conflicted and de-jittered.
"""
from fractions import Fraction
from . import humanize
from . import pattern_match

_HAT = "11"           # closed hi-hat
_HHO = "18"           # open hi-hat
_RIDE = "19"          # ride
_CRASH = ("16", "1A")  # crash, left crash
SECTION = 4           # bars per timekeeping section

# Candidate subdivisions a timekeeping line may sit on: straight (quarter/8th/16th/32nd)
# plus triplets. Used ONLY to snap jitter to a line -- never to inflate a bar's density.
# Real GITADORA charts of every tier mix note values freely, so timekeeping is preserved
# at whatever subdivision the bar actually plays, not forced to a per-tier grid.
_TK_GRIDS = [4, 8, 12, 16, 24, 32]

# Cymbal / hi-hat lanes are bleed-prone: a hard hit's decay or mic bleed spawns a second
# onset a few ms later, which quantizes into a FLAM (two same-lane hits jammed together).
# Real GITADORA charts essentially never place two hits of the SAME cymbal that close. Mined
# across 4,729 corpus charts at their header BPM (docs/drum-corpus-facts.md), the share of
# same-lane consecutive hits under 70 ms is: closed-hat 0.26%, crash 0.45%, left-crash 0.18%
# -- i.e. bleed. Over the SAME 70 ms window the toms jump to 5-6% (hi-tom 6.2%, low-tom 5.0%)
# and snare 1.9% -- genuine fast fills/rolls. 70 ms sits in the valley between the two, so
# collapsing sub-threshold same-lane CYMBAL pairs removes bleed without touching real playing.
# Toms, snare and kick are deliberately NOT de-flammed: real fills, drags and double-bass
# genuinely play fast there.
_CYMBAL_LANES = ("11", "18", "16", "1A", "19")   # closed hat, open hat, crash, Lcrash, ride
FLAM_MS = 70.0                                    # same-lane cymbal hits closer than this = bleed

# Tier-gated left-foot technique for an authentic DTXMania/GITADORA chart, from the
# 2000-chart analysis: Basic/Advanced use the left foot almost never; Extreme adds
# double bass (which only fires on kick runs too fast for one foot); Master also adds
# the hi-hat "chick" on 2 & 4 -- 95% of real Master charts use the hi-hat foot and 58%
# use double bass. (hihat_foot, double_bass) per tier:
TIER_FOOT = {
    "basic":    (False, False),
    "advanced": (False, False),
    "extreme":  (False, True),
    "master":   (True,  True),
}


def _deconflict_sectional(events, section=SECTION, min_hits=2):
    """Keep ONE timekeeper (hi-hat OR ride) consistent across each ``section`` of bars.

    Hi-hat and ride act as timekeeping in the same bar in only ~0.1% of real GITADORA
    bars, so when both play a full pattern one is redundant. Rather than deciding per
    bar (which makes the timekeeper flip hi-hat/ride/hi-hat between neighbours), the
    winner is chosen once per section -- whichever metal has more hits across the
    section -- and only the loser's full patterns are dropped. An isolated ride accent
    (a single crash-of-ride hit, fewer than ``min_hits``) is never touched."""
    removed = 0
    for start in range(0, len(events), section):
        block = events[start:start + section]
        hh_hits = sum(len(b.get(_HAT, {})) for b in block)
        rd_hits = sum(len(b.get(_RIDE, {})) for b in block)
        if not hh_hits or not rd_hits:
            continue                      # only one timekeeper in play: nothing to resolve
        drop = _RIDE if hh_hits >= rd_hits else _HAT
        for b in block:
            hh, rd = b.get(_HAT), b.get(_RIDE)
            if hh and rd and len(hh) >= min_hits and len(rd) >= min_hits:
                removed += len(b[drop])
                del b[drop]
    return events, removed


def _line_grid(positions):
    """Coarsest subdivision on which all of a timekeeping line's hits already sit (within
    tolerance) -- the bar's OWN resolution, so snapping to it never changes note count."""
    for g in _TK_GRIDS:
        if all(abs(float(p) * g - round(float(p) * g)) <= 0.2 for p in positions):
            return g
    return _TK_GRIDS[-1]


def _collapse_flams(sm, thresh_sec, bar_seconds):
    """Collapse same-lane onsets closer than ``thresh_sec`` into one, keeping the more
    on-grid position (a bleed straggler quantizes to a finer, less-musical subdivision
    than the real hit). Walks left→right so a chain of bleed hits collapses to a single
    note. Returns a new {pos: slot} dict."""
    items = sorted(sm.items())
    kept = []
    for pos, slot in items:
        if kept:
            pp, _ps = kept[-1]
            if float(pos - pp) * bar_seconds < thresh_sec:
                # flam pair: keep whichever sits on the coarser (more musical) grid;
                # on a tie the earlier hit (already kept) wins -- the real transient leads.
                if pos.denominator < pp.denominator:
                    kept[-1] = (pos, slot)
                continue
        kept.append((pos, slot))
    return dict(kept)


def _deflam_cymbals(bar, bar_seconds):
    """Remove bleed-induced flams on cymbal / hi-hat lanes only. Two same-lane onsets
    (or a closed + open hi-hat, which are one physical instrument) closer than FLAM_MS
    are one stroke split by mic bleed -- collapse to the more on-grid hit. Toms, snare
    and kick are untouched."""
    if bar_seconds <= 0:
        return 0
    thresh = FLAM_MS / 1000.0
    changed = 0
    # (a) within each cymbal/hi-hat lane
    for ch in _CYMBAL_LANES:
        sm = bar.get(ch)
        if not sm or len(sm) < 2:
            continue
        new = _collapse_flams(sm, thresh, bar_seconds)
        if len(new) != len(sm):
            changed += len(sm) - len(new)
            bar[ch] = new
    # (b) hi-hat family: a single stroke can register as BOTH closed and open a few ms
    # apart -> drop the open one when it flam-hugs a closed hit (closed is the canonical
    # timekeeping hat).
    hc, ho = bar.get(_HAT), bar.get(_HHO)
    if hc and ho:
        drop = [p for p in ho if any(abs(float(p - q)) * bar_seconds < thresh for q in hc)]
        for p in drop:
            del ho[p]
        if drop:
            changed += len(drop)
        if not ho:
            bar.pop(_HHO, None)
    return changed


def _regularize_timekeeping(bar):
    """Remove timing JITTER from a steady hi-hat / ride line by snapping each hit to the
    bar's OWN natural subdivision -- NOT a fixed per-tier grid. The number of hits is
    preserved, so per-bar density stays faithful to the song: a bar of 8ths stays 8ths,
    a 16th run stays 16ths, a sparse bar stays sparse. For an already-clean bar (audio is
    pre-quantized, tabs are exact) this is a no-op."""
    changed = 0
    for ch in (_HAT, _RIDE):
        sm = bar.get(ch)
        if not sm or len(sm) < 3:
            continue
        g = _line_grid(list(sm))
        new = {}
        for p, slot in sm.items():
            new[Fraction(round(float(p) * g), g)] = slot
        if new != sm:
            bar[ch] = new
            changed = 1
    return changed


def _declutter_hh_crash(bar):
    """Remove a CLOSED hi-hat that lands on the exact tick of a crash. Across 2000 real
    charts a closed hi-hat and a crash share a tick in only 3 of 160k bars, so a
    coincident closed hat is almost always a transcription artifact -- the crash should
    read as the accent. Open hi-hat under a crash is a genuine (if rare) technique and
    is deliberately left intact."""
    hh = bar.get(_HAT)
    if not hh:
        return 0
    crash_ticks = set()
    for ch in _CRASH:
        crash_ticks |= set(bar.get(ch, {}))
    hit = [p for p in hh if p in crash_ticks]
    for p in hit:
        del hh[p]
    if not hh:
        del bar[_HAT]
    return len(hit)


def _declutter_open_hat(bar):
    """A CLOSED hi-hat that lands on the exact tick of an OPEN hi-hat is impossible -- one
    hand, one hat, so it's either closed or open at a given moment. The section groove snap
    rewrites the closed-hat lane and can drop a closed hat onto a tick the transcription heard
    (by sustain) as OPEN; the open articulation is what you hear, so it wins and the closed hat
    on that tick is removed."""
    hh = bar.get(_HAT)
    ho = bar.get(_HHO)
    if not hh or not ho:
        return 0
    open_ticks = set(ho)
    hit = [p for p in hh if p in open_ticks]
    for p in hit:
        del hh[p]
    if not hh:
        del bar[_HAT]
    return len(hit)


# Physical-playability: a fast snare roll or tom fill commits BOTH hands to the drums, so
# the timekeeping hand can't also play the hi-hat / ride at the same time. Real charts stop
# the hats during a fill; audio transcription doesn't (the hat bleed keeps triggering), which
# is the "snare roll AND hi-hat at once" artifact. We detect a run of >=3 fast snare/tom hits
# and drop the closed-hat / open-hat / ride that fall inside it (kick stays -- it's the foot;
# a crash at the fill's edge stays -- it's a one-hand accent).
_FILL_LANES = ("12", "14", "15", "17")            # snare + toms (the hands-busy drums)
_TIMEKEEP_LANES = ("11", "18", "19")              # closed hat, open hat, ride
_ROLL_MIN = 3                                       # >=3 fast hits = a roll/fill
_ROLL_GAP_FACTOR = 1.4                              # gaps up to ~1.4x a 16th count as "fast"


def _free_hands_during_fills(events, barlens, bpm):
    """Drop hi-hat/ride timekeeping that overlaps a fast snare roll or tom fill (both hands
    are on the drums, so a simultaneous hat is physically impossible). Mutates ``events``;
    returns notes removed. Kick (foot) and crashes (edge accents) are kept."""
    if not bpm or bpm <= 0:
        return 0
    from . import notes as N
    starts = N.bar_starts(barlens, bpm)               # bar start times, computed ONCE
    whole = 4 * 60.0 / bpm

    def at(mi, pos):
        bl = float(barlens[mi]) if mi < len(barlens) else 1.0
        return starts[mi] + float(pos) * bl * whole

    sixteenth = (60.0 / bpm) / 4.0
    gap_max = _ROLL_GAP_FACTOR * sixteenth
    # all snare+tom hits on the absolute timeline
    drum = []
    for mi, bar in enumerate(events):
        for ch in _FILL_LANES:
            for pos in bar.get(ch, {}):
                drum.append((at(mi, pos), mi, ch, pos))
    drum.sort()
    # group into runs of fast consecutive hits
    runs = []
    cur = []
    for hit in drum:
        if cur and hit[0] - cur[-1][0] > gap_max + 1e-6:
            if len(cur) >= _ROLL_MIN:
                runs.append((cur[0][0], cur[-1][0]))
            cur = []
        cur.append(hit)
    if len(cur) >= _ROLL_MIN:
        runs.append((cur[0][0], cur[-1][0]))
    if not runs:
        return 0
    removed = 0
    for mi, bar in enumerate(events):
        for ch in _TIMEKEEP_LANES:
            sm = bar.get(ch)
            if not sm:
                continue
            drop = []
            for pos in sm:
                t = at(mi, pos)
                if any(t0 - 1e-6 <= t <= t1 + 1e-6 for (t0, t1) in runs):
                    drop.append(pos)
            for pos in drop:
                del sm[pos]
                removed += 1
            if not sm:
                bar.pop(ch, None)
    return removed


_TOMS = ("14", "15", "17")
# Toms de-jitter grid: real fills reach 1/32, so snap tom onsets to the coarsest of these
# they already sit on (removes detection jitter without collapsing a genuine fast fill).
_TOM_GRIDS = [4, 8, 12, 16, 24, 32]


def _regularize_toms(bar):
    """De-jitter tom (and snare-roll) onsets: snap each tom lane to the coarsest 1/4..1/32
    subdivision its own hits already fit, so a fill reads clean without changing its note
    count. Whole-kit normalization -- toms were previously left verbatim."""
    changed = 0
    for ch in _TOMS:
        sm = bar.get(ch)
        if not sm or len(sm) < 2:
            continue
        positions = [float(p) for p in sm]
        g = _TOM_GRIDS[-1]
        for cand in _TOM_GRIDS:
            if all(abs(p * cand - round(p * cand)) <= 0.2 for p in positions):
                g = cand
                break
        new = {}
        for p, slot in sm.items():
            new[Fraction(round(float(p) * g), g)] = slot
        if new != sm:
            bar[ch] = new
            changed = 1
    return changed


# A tom FILL is one coherent rhythmic figure -- straight 16ths, an 8th/16th-note triplet, or a
# sextuplet -- but `_regularize_toms` de-jitters each tom lane on its OWN, so the HT/LT/FT of a
# single fill can each resolve to a different subdivision and the fill reads as jitter instead of
# a pattern. This pass (DTXMania mode only) pools every tom onset of a fast run and snaps the
# WHOLE run to the single coarsest subdivision it collectively fits, so the fill lands on one
# clean grid. It preserves the onset count and which tom plays each onset (the melodic contour --
# which tom is high / low / floor -- is decided separately in fullkit's tom-contour pass); only
# the timing is regularized, and only toward the NEAREST real subdivision (faithful). A run that
# fits no subdivision within tolerance (genuine rubato / scatter) is left exactly as detected.
_FILL_GRIDS = [8, 12, 16, 24, 32]   # 8th, 8th-triplet, 16th, sextuplet/16th-triplet, 32nd
FILL_MIN = 3                        # a run of >=3 fast consecutive toms = a fill
_FILL_FAST = 1.4 / 16.0             # consecutive toms within ~1.4x a 16th = one fast run
_FILL_TOL = 0.25                    # onset must sit within 1/4 of a grid cell for that grid to fit


def _regularize_tom_fills(bar, barlen=1):
    """Snap each tom FILL to the single idiomatic subdivision it best fits (DTXMania mode only).

    A fill is a run of >=FILL_MIN fast consecutive tom onsets pooled across HT/LT/FT. The whole
    run is quantized onto ONE subdivision (the coarsest of _FILL_GRIDS every onset sits within
    _FILL_TOL of) so it reads as a coherent pattern; onset count and per-onset lane are preserved.
    Cross-lane unisons are kept; a same-lane collision moves to the nearest free slot. A run that
    fits no subdivision, or that cannot be laid out inside the bar, is left as detected. Returns
    1 if anything changed."""
    pooled = []
    for ch in _TOMS:
        sm = bar.get(ch)
        if not sm:
            continue
        for p, slot in sm.items():
            pooled.append((float(p), ch, p, slot))
    if len(pooled) < FILL_MIN:
        return 0
    pooled.sort(key=lambda x: x[0])

    # segment into fast consecutive runs
    runs = []
    cur = [pooled[0]]
    for prev, item in zip(pooled, pooled[1:]):
        if item[0] - prev[0] <= _FILL_FAST + 1e-9:
            cur.append(item)
        else:
            runs.append(cur)
            cur = [item]
    runs.append(cur)

    changed = 0
    for run in runs:
        if len(run) < FILL_MIN:
            continue
        posf = [it[0] for it in run]
        # coarsest single subdivision the whole pooled run fits within tolerance
        g = None
        for cand in _FILL_GRIDS:
            if all(abs(p * cand - round(p * cand)) <= _FILL_TOL for p in posf):
                g = cand
                break
        if g is None:
            continue   # fits no clean subdivision -> genuine scatter/rubato, leave the fill alone
        gmax = int(round(float(barlen) * g))
        if gmax < 1:
            continue
        used = {ch: set() for ch in _TOMS}
        placement = []   # (channel, orig_pos, new_pos, slot)
        abort = False
        for _pf, ch, opos, slot in run:
            gi = int(round(_pf * g))
            if gi in used[ch]:
                # nearest free slot on the same lane so no onset is lost to a collision
                for d in (1, -1, 2, -2, 3, -3):
                    if 0 <= gi + d < gmax and (gi + d) not in used[ch]:
                        gi += d
                        break
                else:
                    abort = True
                    break
            if not (0 <= gi < gmax):
                abort = True
                break
            used[ch].add(gi)
            placement.append((ch, opos, Fraction(gi, g), slot))
        if abort:
            continue
        # commit per lane: swap the run's old onsets for the snapped ones
        for ch in _TOMS:
            moves = [(op, npos, slot) for (c, op, npos, slot) in placement if c == ch]
            if not moves:
                continue
            sm = dict(bar.get(ch, {}))
            for op, _npos, _slot in moves:
                sm.pop(op, None)
            for _op, npos, slot in moves:
                sm[npos] = slot
            if sm != bar.get(ch):
                bar[ch] = sm
                changed = 1
    return changed


# Cymbals read messy for the same reason the hats did: crash / ride / open-hat onsets arrive
# a few ms off the beat, so an accent that should sit cleanly on a downbeat or 8th instead
# lands between grid lines. Snap each cymbal onset to the coarsest of these subdivisions it
# sits near -- a lone phrase-start crash lands on the quarter, an 8th ride pattern on the 8th
# -- so the whole kit (not just the hats) reads neat. Grids stop at 1/16: real cymbal work is
# essentially never finer, so this can't preserve (or invent) 1/32 cymbal jitter.
_CYM_LANES = ("16", "1A", "19", "18")   # right crash, left crash, ride, open hi-hat
_CYM_GRIDS = [4, 8, 12, 16]


def _regularize_cymbals(bar):
    """De-jitter every cymbal onset (crash / left-crash / ride / open-hat) onto the coarsest
    1/4..1/16 grid slot it sits near, so cymbal accents land cleanly on the beat like the rest
    of the kit. Unlike the toms pass this also snaps a LONE cymbal hit (accents are usually a
    single crash on a strong beat, and a stray-off-beat crash is the most obvious jitter)."""
    changed = 0
    for ch in _CYM_LANES:
        sm = bar.get(ch)
        if not sm:
            continue
        positions = [float(p) for p in sm]
        g = _CYM_GRIDS[-1]
        for cand in _CYM_GRIDS:
            if all(abs(p * cand - round(p * cand)) <= 0.25 for p in positions):
                g = cand
                break
        new = {}
        for p, slot in sm.items():
            new[Fraction(round(float(p) * g), g)] = slot
        if new != sm:
            bar[ch] = new
            changed = 1
    return changed


def apply(events, barlens, bpm, tier="advanced", aggressive=True, group_cymbals=True):
    """Regularize a chart toward idiomatic DTXMania patterns.

    Mutates and returns (events, changed_count). By default DTXMania mode is AGGRESSIVE: it
    rewrites the whole groove (kick/snare/hat/ride) of every 4/4 non-fill bar to the nearest
    real GITADORA groove so the chart reads "produced" even far from the exact transcription
    (faithfulness is deliberately waived for feel). Tom fills, crashes, open hi-hat and the
    feet are preserved as the fill/accent layer. ``group_cymbals`` folds ride + left-crash
    onto the single right crash lane, as most DTXMania kits play them. (The niche open-hat ->
    left-pedal move is applied by the pipeline AFTER auto_foot, so it isn't handled here.)

    Set ``aggressive=False`` for the older conservative denoise (only unrecognized grooves
    are nudged, within a small budget) -- kept for regression stability.
    """
    # 1. one timekeeper (hi-hat OR ride) at a time, chosen consistently per section.
    events, changed = _deconflict_sectional(events)
    whole = (4 * 60.0 / bpm) if bpm and bpm > 0 else 0.0
    for i, bar in enumerate(events):
        bar_seconds = float(barlens[i]) * whole if i < len(barlens) else whole
        # 1b. remove bleed-induced cymbal/hi-hat flams (the audio artifact) BEFORE snapping.
        changed += _deflam_cymbals(bar, bar_seconds)
        # 2. clean timing jitter -- snap the timekeeper to the bar's OWN subdivision.
        changed += _regularize_timekeeping(bar)
        # 2b. whole-kit normalization: de-jitter the toms (and snare-roll) onsets too.
        changed += _regularize_toms(bar)
        # 2b-2. DTXMania only: after the per-lane de-jitter, determine the fill PATTERN --
        #       snap each fast tom run to the one subdivision the whole fill fits so it reads
        #       as a coherent figure, not per-lane jitter (pairs with fullkit's contour pass,
        #       which decides which tom is high/low/floor). Faithful path leaves toms as detected.
        if aggressive:
            changed += _regularize_tom_fills(bar, barlens[i] if i < len(barlens) else 1)
        # 2c. ...and the cymbals (crash / ride / open-hat) -- neat across the WHOLE kit,
        #     not just the hats: accents land on the beat instead of between grid lines.
        changed += _regularize_cymbals(bar)
        # 3. a closed hi-hat sharing a crash's tick is an artifact -> let the crash speak.
        changed += _declutter_hh_crash(bar)
    # 4. hands-busy realism FIRST (before the groove snap can collapse a roll): a fast snare
    #    roll / tom fill commits both hands, so drop any hi-hat / ride that overlaps it -- fixes
    #    the impossible "snare roll AND hi-hat at once". Done on the intact transcription so the
    #    roll is still detectable.
    changed += _free_hands_during_fills(events, barlens, bpm)
    # 5. snap the groove (kick+snare+hat/ride backbone) to real GITADORA patterns.
    #    AGGRESSIVE (DTXMania): SECTION-first -- vote one clean groove per phrase and repeat it,
    #    so the chart reads neat and consistent like the real corpus (not haphazard bar-to-bar).
    #    CONSERVATIVE (Standardize): per-bar denoise of only unrecognized grooves.
    if aggressive:
        events, snapped = pattern_match.snap_sections(events, barlens, bpm, tier)
    else:
        events, snapped = pattern_match.snap(events, barlens, bpm, tier, aggressive=False)
    changed += snapped
    if snapped:
        for bar in events:
            changed += _declutter_hh_crash(bar)   # a snapped hat can land on a crash tick
            changed += _declutter_open_hat(bar)   # ...or on an open-hat tick (open wins)
    # 6. optional: fold ride + left-crash onto the one right cymbal (typical DTXMania kit).
    if group_cymbals:
        events, moved = pattern_match.group_right_cymbals(events)
        changed += moved
    # 7. optional (niche): the open-hat -> left-pedal move is applied by the pipeline AFTER
    #    auto_foot, so it also respects any left-foot notes that stage adds.
    # Crashes are otherwise preserved: real charts stack them with kick, snare and other
    # crashes, so this pass neither collapses crashes to one-per-bar nor injects them.
    return events, changed


def auto_foot(events, barlens, bpm, tier="advanced"):
    """Add tier-gated left-foot technique to a DTXMania-style chart AFTER the hands are
    regularized, so the foot fills the gaps around the FINAL hi-hat/ride layout (this is
    why it runs here rather than in the generic humanize stage, which would see the
    pre-regularized hands). The one-left-foot rule is preserved by humanize's own
    ordering -- double bass claims a tick first, then the hi-hat chick only fills a
    still-free 2 & 4 backbeat -- so a chick and a left kick can never share a tick, as in
    real charts. Returns (events, hihat_on, double_on, converted_kicks)."""
    hh, db = TIER_FOOT.get(str(tier).lower(), (False, False))
    converted = 0
    if hh or db:
        events, converted = humanize.humanize(events, barlens, bpm,
                                              hihat_on=hh, doublebass=db)
    return events, hh, db, converted
