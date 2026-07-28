"""End-to-end pipeline orchestration. Each run streams progress + stage events."""
import os, re, copy, traceback
from . import (songsterr, audio, transcribe, drumkit, dtx, humanize, playability,
               notes, autosync, sources, faithfulness as faith, difficulty)


class Cancelled(Exception):
    """Raised at a stage boundary when the UI's Stop button requested cancellation."""

def normalize_dlevel(text, default="50"):
    """Accept '0-99' (tens scale, 50->5.00) or '0.00-9.99' (literal). Emit the
    DTXMania hundredths integer that displays that difficulty (5.55 -> 555)."""
    s = str(text).strip() or str(default)
    try:
        if "." in s:
            d = float(s)                 # 0.00-9.99
        else:
            iv = int(s)
            d = iv / 10.0 if 0 <= iv <= 99 else iv / 100.0
    except ValueError:
        d = 5.0
    d = max(0.0, min(9.99, d))
    return int(round(d * 100))           # hundredths; DTXMania shows d


def _slug(s):
    s = re.sub(r'[<>:"/\\|?*]+', "", s or "").strip()
    return re.sub(r"\s+", " ", s) or "chart"

def run(opts, workdir, assets_dir, progress):
    """
    opts keys:
      tab_source: 'songsterr' | 'midi' | 'audio'
      songsterr_query / songsterr_url  (for songsterr)
      midi_path                         (for midi)
      audio_source: 'songsterr' | 'url' | 'upload' | 'none'
      audio_url, upload_audio_path
      remove_drums: bool  (option C)
      title, artist, bpm(optional), dlevel
    Returns dict(folder, zip, stats).
    """
    os.makedirs(workdir, exist_ok=True)
    kit_dir = os.path.join(assets_dir, "drumkit")
    kit_files = drumkit.ensure_kit(kit_dir)

    # stage/log shims (progress may be a Reporter or a plain callable)
    def ckpt():
        # abort cleanly at stage boundaries if the user hit Stop
        if hasattr(progress, "is_cancelled") and progress.is_cancelled():
            raise Cancelled()
    def stg(sid, msg=None):
        ckpt()
        if hasattr(progress, "stage"): progress.stage(sid, msg)
        elif msg: progress(msg)
    def skp(sid):
        if hasattr(progress, "skip"): progress.skip(sid)
    def log(msg):
        progress(msg)
    def setdata(key, value):
        if hasattr(progress, "set_data"): progress.set_data(key, value)

    title = (opts.get("title") or "").strip()
    artist = (opts.get("artist") or "").strip()
    if not title or not artist:
        raise RuntimeError("Title and Artist are required.")
    bpm = opts.get("bpm")
    m = None

    # Audio-only transcription style: 'raw' (as heard) | 'standardize' (grid + clean).
    # Back-compat: honor the old `standardize` bool when `style` is absent.
    style = str(opts.get("style") or
                ("standardize" if opts.get("standardize", True) else "raw")).lower()
    notes_style = str(opts.get("notes_style", "transcribed")).strip().lower()
    # DTXMania regularization needs a clean, grid-locked base to work from, so it always
    # transcribes audio with Standardize regardless of the Raw/Standardize toggle.
    do_std_audio = (style != "raw") or (notes_style == "dtxmania")

    # Notation is OPTIONAL. With no tab URL/paste and no uploaded tab file, the
    # drums are transcribed straight from the audio (which then becomes required).
    _has_tab = bool((opts.get("songsterr_url") or "").strip() or opts.get("tab_file_path"))
    if opts.get("tab_source") in ("songsterr", "url", "auto") and not _has_tab:
        opts["tab_source"] = "audio"

    asrc = opts.get("audio_source", "none")
    drum_mode = opts.get("drum_mode", "keep")           # keep = full song (default)
    auto_sync = bool(opts.get("auto_sync", True)) and asrc in ("url", "upload")
    need_stem = (drum_mode in ("remove", "quiet")) or (opts["tab_source"] == "audio")
    if opts["tab_source"] == "audio" and asrc == "none":
        raise RuntimeError("No notation was provided, so DTXScribe needs audio to "
                           "transcribe the drums from. Add a YouTube link or upload an audio file.")

    # ---------- 1. NOTATION ----------
    stg("notation", "Resolving notation source...")
    if opts["tab_source"] in ("songsterr", "url", "auto"):
        # smart-detect: Songsterr / Guitar Pro / MIDI / ASCII from URL or uploaded file
        kind, payload = sources.detect(url_or_id=opts.get("songsterr_url", ""),
                                       file_path=opts.get("tab_file_path", ""),
                                       workdir=workdir)
        log(f"Detected source: {kind}.")
        if kind == "songsterr":
            sid = payload
            m = songsterr.meta(sid)
            _t = re.sub(r"\s+drum\s*tab\s*$", "", m.get("title", title), flags=re.I).strip()
            title = opts.get("title") or _t
            artist = opts.get("artist") or m.get("artist", artist)
            trk = songsterr.fetch_drum_notation(m)
            events, barlens = transcribe.from_songsterr(trk["measures"])
            if not bpm:
                tt = (trk.get("automations") or {}).get("tempo")
                bpm = (tt[0]["bpm"] if tt else 120)
        elif kind == "guitarpro":
            events, barlens, bpm2 = transcribe.from_guitarpro(payload)
            bpm = bpm or bpm2
        elif kind == "midi":
            events, barlens, bpm2 = transcribe.from_midi(payload)
            bpm = bpm or bpm2
        elif kind == "ascii":
            events, barlens, bpm2 = transcribe.from_ascii_tab(payload, bpm=bpm or 120)
            bpm = bpm or bpm2
        else:
            raise RuntimeError(f"Unsupported source kind: {kind}")
        log(f"Transcribed {dtx.count_chips(events)} notes across {len(events)} bars.")
    elif opts["tab_source"] == "midi":
        log("Parsing MIDI drum track...")
        events, barlens, bpm2 = transcribe.from_midi(opts["midi_path"])
        bpm = bpm or bpm2
    elif opts["tab_source"] == "audio":
        events = barlens = None                         # produced later from audio
    else:
        raise ValueError("bad tab_source")

    # surface a detected BPM to the UI as early as it's known (tab sources know it now)
    if bpm:
        setdata("bpm", round(float(bpm), 3))

    # ---------- 2. AUDIO ----------
    raw_audio = None
    audio_onsets = []   # raw per-lane onset positions for the editor review overlay (audio path only)
    sampled_lanes = []  # drum lanes voiced from real one-shots sliced from THIS song (audio path)
    lead_in_barlens = []  # empty intro bars to prepend after rating (audio-only, full-song intro)
    if asrc == "none":
        skp("audio")
    else:
        stg("audio")
        if asrc == "songsterr":
            if not m:
                m = songsterr.meta(songsterr.parse_song_id(opts.get("songsterr_url") or ""))
            log("Downloading tab-synced audio from Songsterr...")
            raw_audio = os.path.join(workdir, "src.opus")
            songsterr.download_synced_audio(m, raw_audio)
        elif asrc == "url":
            log("Downloading audio from link...")
            raw_audio = audio.download_audio_url(opts["audio_url"], os.path.join(workdir, "src"), progress=log)
        elif asrc == "upload":
            raw_audio = opts["upload_audio_path"]
            log("Using uploaded audio file.")

    full_wav = None
    drum_stem = None
    if raw_audio:
        full_wav = os.path.join(workdir, "fullmix.wav")
        log("Decoding audio...")
        audio.to_wav(raw_audio, full_wav)

    # ---------- 3. DRUM SEPARATION ----------
    if raw_audio and need_stem:
        stg("separate", "Separating drums (Demucs)...")
        _, drum_stem = audio.demucs_remove_drums(full_wav, os.path.join(workdir, "demucs"), log)
    else:
        skp("separate")

    # ---------- 3b. AUDIO-ONLY TRANSCRIBE ----------
    if opts["tab_source"] == "audio":
        if not drum_stem:
            raise RuntimeError("Audio-only transcription needs the isolated drum track, "
                               "but drum separation did not produce one.")
        # Always attempt the automatic dual-engine full kit (toms + ride + hats);
        # fall back to the fast built-in detector only if the models can't load.
        from . import fullkit
        stg("notation", "Full-kit transcription (inagoy + LarsNet, beta)...")
        do_std = do_std_audio
        kit_samples = {}
        try:
            events, barlens, bpm2, audio_anchor, kit_samples, audio_onsets = fullkit.from_audio_fullkit(
                drum_stem, bpm=bpm, progress=log, standardize=do_std)
        except Exception as e:
            log(f"Full-kit engines unavailable ({str(e)[:100]}); "
                f"using the fast kick/snare/hat detector.")
            events, barlens, bpm2, audio_anchor = transcribe.from_audio_drums(
                drum_stem, bpm=bpm, progress=log, standardize=do_std)
            kit_samples = {}
        bpm = bpm or bpm2
        # The transcription puts the first detected hit at chart t=0. Rather than trimming
        # the intro off the backing track, keep the FULL song and represent the intro as
        # empty "lead-in" bars prepended to the chart (applied after rating, section 6f) so
        # the first note still lands on the first real drum hit. Any planning issue falls
        # back to the original trim-to-first-hit behavior so audio and chart stay in sync.
        if audio_anchor and audio_anchor > 0.05:
            try:
                lead_in_barlens = notes.plan_leadin(barlens, bpm, audio_anchor)
            except Exception as e:
                lead_in_barlens = []
                log(f"Intro lead-in planning failed ({str(e)[:60]}); trimming instead.")
            if lead_in_barlens:
                log(f"Keeping the full song: the {audio_anchor:.2f}s intro becomes "
                    f"{len(lead_in_barlens)} lead-in bar(s); the chart still starts on the first hit.")
            else:
                log(f"Aligning backing track to first drum hit (trim {audio_anchor:.2f}s).")
                full_wav = audio.trim_start(full_wav, os.path.join(workdir, "full_trim.wav"), audio_anchor)
                drum_stem = audio.trim_start(drum_stem, os.path.join(workdir, "drums_trim.wav"), audio_anchor)

        # ---------- 3c. PER-SONG DRUM VOICING ----------
        # Voice the chart with one-shots sliced from THIS song's isolated stems (so toms,
        # snare, etc. sound like the real kit) and fall back to the synth sample per lane
        # that had no clean, isolated hit. Build a job-local kit dir so the shared
        # assets/drumkit stays untouched.
        if kit_samples:
            import shutil as _sh
            job_kit = os.path.join(workdir, "kit")
            os.makedirs(job_kit, exist_ok=True)
            for _lab, _fn in kit_files.items():
                _sh.copy2(os.path.join(kit_dir, _fn), os.path.join(job_kit, _fn))
            saved = []
            for _lab, _seg in kit_samples.items():
                _fn = kit_files.get(_lab)
                if not _fn:
                    continue
                try:
                    fullkit.save_oneshot(os.path.join(job_kit, _fn), _seg)
                    saved.append(_lab)
                except Exception:
                    pass
            if saved:
                kit_dir = job_kit
                sampled_lanes = saved
                log("Sampled real drums from the song: " + ", ".join(sorted(saved))
                    + " (other lanes use the built-in kit).")
        if opts["tab_source"] == "audio" and not sampled_lanes:
            log("No clean isolated drum hits could be sampled from this song; "
                "the chart uses the built-in synth kit. If you also had no backing "
                "track, add your own .ogg to the chart folder.")

    if events is None:
        raise RuntimeError("No notation was produced.")
    if not bpm:
        bpm = 120
    setdata("bpm", round(float(bpm), 3))    # final detected/effective BPM (audio-only path)

    # snapshot the faithful transcription - the baseline for the faithfulness score
    original_events = copy.deepcopy(events)

    # ---------- 4. AUTO-SYNC (align external audio to the chart) ----------
    if raw_audio and auto_sync and opts["tab_source"] != "audio":
        stg("align")
        alpha = beta = None
        # Preferred: align to the tab-synced Songsterr master (same recording -> robust)
        ref_wav = None
        if m is not None:
            try:
                ref_opus = os.path.join(workdir, "ref.opus")
                songsterr.download_synced_audio(m, ref_opus)
                ref_wav = os.path.join(workdir, "ref.wav")
                audio.to_wav(ref_opus, ref_wav)
            except Exception as e:
                log(f"Auto-sync reference unavailable ({str(e)[:60]}); using chart notes.")
        if ref_wav:
            alpha, beta = autosync.align_audio_to_reference(full_wav, ref_wav, progress=log)
        elif drum_stem:
            note_times = [notes.abs_time(n["m"], n["pos"], barlens, bpm) for n in notes.flatten(events)]
            alpha, beta = autosync.align_audio_to_chart(drum_stem, note_times,
                                                        notes.bar_starts(barlens, bpm)[-1], progress=log)
        else:
            log("Auto-sync: no reference or drum stem; skipping alignment.")
        if alpha is not None and (abs(alpha - 1) > 1e-4 or abs(beta) > 0.01):
            full_aln = os.path.join(workdir, "full_aligned.wav")
            autosync.apply_alignment(full_wav, full_aln, alpha, beta)
            full_wav = full_aln
            if drum_stem:
                dr_aln = os.path.join(workdir, "drums_aligned.wav")
                autosync.apply_alignment(drum_stem, dr_aln, alpha, beta)
                drum_stem = dr_aln
            log("Audio aligned to chart timeline.")
    else:
        skp("align")

    # ---------- 4b. BUILD BGM (per drum mode) ----------
    bgm_file = None
    if raw_audio:
        if drum_mode == "keep" or not drum_stem:
            bgm_wav = full_wav
        else:
            k = 0.90 if drum_mode == "remove" else 0.55
            bgm_wav = audio.build_bgm(full_wav, drum_stem, os.path.join(workdir, "bgm_ducked.wav"), k)
        bgm_file = os.path.join(workdir, "bgm.ogg")
        log("Encoding BGM...")
        audio.to_ogg(bgm_wav, bgm_file)

    # ---------- 5. FOOT TECHNIQUE ----------
    # Applied automatically and tier-gated for DTXMania style (section 6c). There is no
    # manual foot-technique control -- feet fill the gaps once the hands are regularized.
    hh_on = db_on = False
    db_converted = 0

    # ---------- 6. PLAYABILITY ----------
    stg("playability", "Checking human playability...")
    rep = playability.analyze(events, barlens, bpm)
    log(f"Playability: {rep['verdict']} (score {rep['score']}/100, {rep['issue_count']} tight spots).")
    play_report = rep
    if rep["issue_count"] > 0 and opts.get("auto_relax", True):
        log("Auto-relaxing hard passages...")
        events, relax = playability.auto_relax(events, barlens, bpm, allow_doublebass=db_on)
        play_report = relax["after"]
        log(f"After relax: {play_report['verdict']} (score {play_report['score']}/100, {play_report['issue_count']} tight spots).")

    # ---------- 6b. DIFFICULTY TIER (choose it first; needed by DTXMania + thinning) ----------
    dlevel_in = str(opts.get("dlevel", "")).strip()
    tier_choice = str(opts.get("dlevel_tier", "auto")).strip().lower()

    if dlevel_in:
        dlevel_val = normalize_dlevel(dlevel_in)
        dlevel_display = round(dlevel_val / 100.0, 2)
        dlevel_auto = False
    else:
        dscore = difficulty.compute(events, barlens, bpm)   # preliminary, for auto tier
        dlevel_val = dscore["value"]
        dlevel_display = dscore["display"]
        dlevel_auto = True

    if tier_choice in ("basic", "advanced", "extreme", "master"):
        tier_key = tier_choice
    else:
        tier_key = dtx.tier_from_score(dlevel_display)

    # ---------- 6c. NOTES STYLE (DTXMania regularization - any source, tab or audio) ----------
    if notes_style == "dtxmania":
        from . import dtxmania_style, pattern_match
        # Cymbal grouping is handled uniformly by the Lane-grouping post-step (6d-2), so the
        # DTXMania regularizer no longer folds cymbals itself.
        tidy_cym = str(opts.get("tidy_cymbals", "false")).lower() == "true"
        events, nchg = dtxmania_style.apply(events, barlens, bpm, tier_key,
                                            aggressive=True, group_cymbals=False,
                                            tidy_cymbals=tidy_cym)
        log(f"DTXMania style: whole groove rewritten to real GITADORA patterns; "
            f"tom fills, crashes and feet kept as the fill layer ({nchg} edits).")
        if tidy_cym:
            log("DTXMania tidy cymbals: over-detected crash/ride density thinned "
                "(pooled onsets within 100ms merged to the earliest, kept in place).")
        # Authentic charts add left-foot technique, tier-gated (real data: Basic/Advanced
        # ~none, Extreme double bass, Master hi-hat chick + double bass). Feet fill the
        # gaps now that the hands are regularized, so no manual toggle is needed.
        events, hh_on, db_on, db_converted = dtxmania_style.auto_foot(events, barlens, bpm, tier_key)
        if hh_on or db_on:
            bits = []
            if hh_on: bits.append("hi-hat foot on 2 & 4")
            if db_on: bits.append(f"double bass ({db_converted} fast kicks split)")
            log(f"DTXMania foot technique for {tier_key.title()}: {', '.join(bits)}.")
        # niche: move the open hi-hat onto the left-foot pedal (after auto_foot so the
        # one-left-foot rule holds against any chick/double-bass notes it just added).
        if str(opts.get("openhat_lp", "false")).lower() == "true":
            events, oh_moved = pattern_match.openhat_to_left_pedal(events)
            if oh_moved:
                log(f"Open hi-hat moved to left-foot pedal ({oh_moved} notes).")

    # ---------- 6c-2. STANDARDIZE regularization (audio, conservative) ----------
    # When the audio was transcribed with Standardize (and NOT DTXMania), run the SAME
    # regularization the previous DTXMania did, in its conservative form: one timekeeper per
    # section, de-flam cymbals, de-jitter timekeeping, declutter closed-hat-under-crash, and
    # the conservative "snap groove, keep fills" (real grooves kept, only noise nudged). This
    # is the rung between Raw and DTXMania. Auto foot technique and cymbal grouping are NOT
    # applied here -- those stay DTXMania-only.
    if notes_style != "dtxmania" and opts["tab_source"] == "audio" and do_std_audio:
        from . import dtxmania_style
        events, nchg = dtxmania_style.apply(events, barlens, bpm, tier_key,
                                            aggressive=False, group_cymbals=False)
        if nchg:
            log(f"Standardize: de-flam + de-jitter + groove snapped to real patterns "
                f"(real grooves kept faithful, {nchg} edits).")

    # ---------- 6d. DE-CONFLICT a redundant second timekeeper (hi-hat AND ride) ----------
    # Note values are NOT capped by tier -- the chart keeps its real 16th/32nd content at
    # any difficulty; only a redundant simultaneous timekeeper is dropped.
    from . import simplify
    events, thinned = simplify.thin_for_tier(events, tier_key)
    if thinned:
        log(f"Removed {thinned} redundant timekeeper notes (hi-hat/ride played together).")

    # ---------- 6d-2. LANE GROUPING (Advanced preset: Full / Standard / Custom) ----------
    # Fold drum lanes onto DTXMania's standard combined lanes, per the user's grouping preset.
    # This is the single, style-independent grouping control (the DTXMania-style regularizer's
    # own cymbal fold is disabled above so grouping happens only here). "full" = no fold.
    folds = dtx.folds_from_opts(
        opts.get("lane_grouping", "full"),
        ride=str(opts.get("grp_ride", "false")).lower() == "true",
        openhat=str(opts.get("grp_openhat", "false")).lower() == "true",
        lp=str(opts.get("grp_lp", "false")).lower() == "true")
    if folds:
        gmoved = dtx.group_lanes(events, folds)
        if gmoved:
            _names = {"ride": "ride→cymbal", "openhat": "open+closed hi-hat", "lp": "left pedal→bass"}
            log(f"Lane grouping ({', '.join(_names.get(f, f) for f in folds)}): {gmoved} notes folded.")

    # Re-rate after style + thinning so the shown score and #DLEVEL match the emitted notes.
    if dlevel_auto:
        dscore = difficulty.compute(events, barlens, bpm)
        dlevel_val = dscore["value"]
        dlevel_display = dscore["display"]
        fa = dscore["factors"]
        log(f"Auto-difficulty: {dlevel_display:.2f}/9.99 "
            f"(density {fa.get('avg_density')}/s -> lvl {fa.get('level_density')}, "
            f"2-sec peak {fa.get('peak_2s')}/s -> lvl {fa.get('level_peak')}). "
            f"Rated against the level reference table.")
        setdata("dlevel", dlevel_display)

    # ---------- 6e. FAITHFULNESS (final chart vs the original source) ----------
    fscore = faith.compare(original_events, events)
    log(faith.summary_line(fscore, "audio" if opts["tab_source"] == "audio" else "tab"))

    # ---------- 6f. INTRO LEAD-IN (audio-only, full-song intro) ----------
    # Rating is done on the played content, so now prepend the empty intro bars planned at
    # section 3b. The full (untrimmed) BGM keeps the song's real intro; these bars push the
    # first note to the first drum hit so chart and audio line up. The editor sees the bars
    # too, so it plays the intro for free. No-op on the tab/MIDI paths.
    if lead_in_barlens:
        n_lead = len(lead_in_barlens)
        events = [dict() for _ in lead_in_barlens] + events
        barlens = list(lead_in_barlens) + list(barlens)
        # Keep the review-overlay onsets aligned: their bar indices were computed against
        # the pre-lead-in chart (first hit = bar 0), so shift each by the lead-in count.
        for o in audio_onsets:
            if isinstance(o, dict) and o.get("bar") is not None:
                o["bar"] += n_lead
        log(f"Added {n_lead} intro lead-in bar(s); the chart now plays from the song's start.")

    dtx_name, tier_label, tier_slot = dtx.tier_info(tier_key)
    setdata("dlevel_tier", tier_key)
    log(f"Difficulty level: {tier_label.title()} (score {dlevel_display:.2f}) -> {dtx_name}.")

    # ---------- 7. PACKAGE (deferred for the editor-first flow) ----------
    # The UI edits the chart in-memory first and packages ONCE on download, so nothing
    # is zipped at generation time when defer_package is set.
    defer = bool(opts.get("defer_package"))
    stg("package", "Preparing chart..." if defer else "Building DTX chart...")
    if bgm_file is None:
        import wave
        silent_wav = os.path.join(workdir, "silence.wav")
        with wave.open(silent_wav, "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
            w.writeframes(b"\x00\x00" * 44100)
        bgm_file = os.path.join(workdir, "bgm.ogg")
        audio.to_ogg(silent_wav, bgm_file)

    meta = dict(title=title, artist=artist, bpm=round(float(bpm), 3),
                dlevel=dlevel_val,
                comment=(f"Charted by {opts['author']} using DTXScribe."
                         if opts.get("author") else "Charted using DTXScribe."),
                bgm=os.path.basename(bgm_file))
    jacket_path = opts.get("jacket_path")
    if jacket_path and os.path.exists(jacket_path):
        meta["preimage"] = os.path.basename(jacket_path)
        log(f"Jacket image added ({meta['preimage']}).")
    else:
        jacket_path = None
    song_name = f"{_slug(artist)} - {_slug(title)}"
    repack = dict(out_dir=os.path.join(workdir, "dist"), song_name=song_name,
                  bgm_file=bgm_file, kit_dir=kit_dir, kit_files=kit_files,
                  dtx_name=dtx_name, set_label=tier_label, set_slot=tier_slot,
                  image_file=jacket_path)
    if defer:
        folder, zpath = None, None
    else:
        dtx_text = dtx.emit_dtx(events, barlens, meta)
        folder, zpath = dtx.package(repack["out_dir"], song_name, dtx_text, bgm_file,
                                    kit_dir, kit_files, dtx_name=dtx_name,
                                    set_label=tier_label, set_slot=tier_slot,
                                    image_src=jacket_path)
    if hasattr(progress, "finish"): progress.finish()
    stats = dict(measures=len(events), chips=dtx.count_chips(events), bpm=meta["bpm"],
                 drum_mode=drum_mode if raw_audio else "none",
                 removed_drums=bool(raw_audio and drum_mode != "keep"),
                 has_audio=bool(raw_audio), audio_source=asrc,
                 sampled_lanes=sampled_lanes, sampled_count=len(sampled_lanes),
                 playability=play_report["verdict"], play_score=play_report["score"],
                 play_issues=play_report["issue_count"],
                 faithfulness=fscore["percent"], notes_moved=fscore["moved"],
                 notes_dropped=fscore["dropped"], notes_added=fscore["added"],
                 dlevel=dlevel_display, dlevel_auto=dlevel_auto,
                 dlevel_tier=tier_key, dtx_file=dtx_name, tier_manual=(tier_choice in ("basic","advanced","extreme","master")),
                 source=opts["tab_source"], title=title, artist=artist)
    log("Done.")
    # Chart model + re-emit params, so the UI editor can load/edit/re-save the chart.
    chart = dict(events=events, barlens=barlens, bpm=float(meta["bpm"]), meta=meta,
                 has_audio=bool(raw_audio), review=dict(onsets=audio_onsets))
    return dict(folder=folder, zip=zpath, stats=stats, playability=play_report,
                faithfulness=fscore, chart=chart, repack=repack)
