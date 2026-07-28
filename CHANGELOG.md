# Changelog

## v1.9.7

Refinement release. An optional cleanup for busy cymbals in DTXMania mode. Still a public preview, so some rough edges may remain.

- **Tidy cymbals (optional).** DTXMania mode gains an off-by-default "Tidy cymbals" toggle that thins over-detected crash and ride density for a cleaner read. Pooled crash and ride hits landing within 100 ms collapse to the earliest one, kept in place. It is cosmetic and accuracy-neutral: kick, snare, toms, open hi-hat, and both feet are untouched.

## v1.9.6

Accuracy release. Better tempo detection and wider hi-hat support, grounded on a corpus of real charts. Still a public preview, so some rough edges may remain.

- **Smarter tempo detection.** Audio transcription and Record mode now resolve the tempo octave more reliably, so a fast song is far less likely to be charted at half speed (or a slow one at double). The picker is grounded on the tempo distribution of thousands of real charts and still yields to a tempo you type in.
- **Roland hi-hat foot and edge.** Hi-hat edge and foot-splash notes that some Roland modules send now map to the right lane instead of being dropped.

## v1.9.5

Public preview. Record mode, a finer difficulty scale, and remappable keyboard keys. This is a preview build, so some rough edges and bugs may still be present.

- **Record mode.** Play a take on an electronic drum kit over MIDI, or on your computer keyboard, and DTXScribe turns it into a chart. Set a tempo, play, then edit the result like any other chart. Play-along to a song, a count-in, tap tempo, and per-device latency calibration are built in.
- **Learn my kit.** A short walkthrough maps your module's pads, so kits that send non-standard notes still chart correctly.
- **Remappable keyboard keys.** In Record mode you can reassign which key hits which drum. Your layout is saved, with a reset button to restore the defaults.
- **Finer difficulty scale.** Charts are rated on a 1.0 to 9.99 scale that tracks note density and peak bursts, shown in the output and used to pick the DTXMania difficulty tier.
- **Clean exit.** Closing the app, by the Exit button or the window X, shuts everything down with nothing left running in the background.
- **Fixes.** Hardened against malformed input and edge cases found in testing.

## v1.9.0

Full-length songs, a new app icon, and a proper uninstaller.

- **The whole song is now in the chart.** Audio-only charts keep the complete backing track -
  the intro before the first drum hit and the outro after the last note - instead of trimming to
  the first hit. The chart rides on the full song with lead-in bars, so the first note still lands
  exactly on the first real hit, and the editor plays the intro and outro too.
- **More reliable YouTube downloads.** DTXScribe now tries several YouTube players when fetching
  audio, so it gets past the intermittent "confirm you're not a bot" check far more often with no
  login. If a video still needs a sign-in, staying signed in with Firefox (or using **Upload file**)
  works reliably.
- **New app icon.** A distinctive DTXScribe mark on the app window, the taskbar, and the browser tab.
- **Full uninstaller.** `uninstall.cmd` now finds and removes everything DTXScribe puts on your PC -
  the downloaded model weights, cache and logs, any older pre-rebrand data, and shortcuts - after
  listing them with sizes and asking first. It can optionally delete the program folder itself at
  the end, and it never touches your saved charts.

## v1.8.0

Editor flexibility and cleaner charts: rearrange the lanes to your taste, group drum voices
the way a DTXMania kit reads them, and hear the song play through its outro.

- **Rearrange the lanes.** A new **Arrange lanes** mode in the editor lets you drag the lane
  columns into whatever left-to-right order you're used to - the columns **glide smoothly** as
  you drag, so you can see exactly where a lane will land before you drop it. It's a per-you
  view preference (remembered between runs) and **never changes the chart or the exported
  file** - a kick is still a kick. Normal note editing is locked while arranging, so you can't
  nudge a lane by accident, and a **Reset** eases the columns back to the default GITADORA order.
- **Lane grouping.** A new **Lane Grouping** control in Advanced combines drum lanes the way a
  DTXMania kit reads them: **Full (11 lanes)** keeps everything separate, **Standard (9 lanes)**
  folds the ride and open hi-hat like the default kit, and **Custom** lets you pick each fold
  (ride→cymbal, open+closed hi-hat→one, left pedal→bass). The editor's one-click **Group &
  clean** menu now offers the same folds after the fact, all undoable.
- **Full-length playback in the editor.** When the backing track has an outro after the last
  charted note, the editor now plays through it (the playhead parks on the last bar) instead of
  cutting off - matching how the packaged chart already plays in-game.

## v1.7.0

**DTX Forge is now DTXScribe.** The app has been renamed to better reflect what it does -
transcribe drums into DTXMania charts. Same tool, same workflow, new name.

- **Rebrand to DTXScribe.** New name throughout the app, window title, and the standalone
  build (`DTXScribe.exe`).
- **Your downloads carry over.** On first launch the app automatically moves your existing
  data folder (`%LOCALAPPDATA%\DTXForge` → `%LOCALAPPDATA%\DTXScribe`), so the ~1 GB of
  drum-separation model weights you already downloaded are reused instead of re-fetched.
- **Updates keep working.** Updating from an older build through the in-app updater keeps working
  - GitHub redirects the old release URLs to the renamed repository.

## v1.6.2

Editor craft: a smoother highway, clearer bar tracking, authentic foot technique on
falling pedals, and a modernized look across the whole app.

- **Peek scrolling.** The editor now shows a slice of the previous and next bars above
  and below the current one, with a faint grid so nothing reads blank - and playback
  scrolls smoothly, then snaps the active bar to center, instead of jumping.
- **Bar-number readout.** The current bar number rides next to its downbeat "1" (in your
  accent color) in both gutters, and the top boundary is labelled as the *next* bar's "1"
  and number - so you always know where you are.
- **Edit across bar lines.** A note detected slightly early or late can now be dragged - or
  nudged with Alt + ↑ / ↓ - across a bar boundary onto the neighbouring bar's downbeat.
- **Authentic foot technique on the highway.** During playback the falling kick and
  left-pedal chips carry the right-foot / left-foot silhouettes from DTXMania, so the
  pedal work reads exactly like the game.
- **Crunchier hit splash.** Notes burst with the game's own chip-fire art as they cross the
  judgement line, so hits land with impact.
- **Modernized interface.** Dimensional, glossy note chips; a glowing playhead with a
  rounded scrubber handle; a 3D round play button; and depth, gradients and glossy
  buttons across both light and dark themes.
- **Exit button** to cleanly close the app, plus small label polish (SPEED / SCROLL
  transport controls, "Drums in the Backing Track").

## v1.6.1

Play-feel and real-sound polish, plus the ability to open existing charts.

- **Real drum samples in the editor.** The Drum Sounds preview now plays each chart's own
  kit - the per-song one-shots sliced from your track (generated charts) or an imported
  chart's bundled samples - instead of the generic synth kit. Lanes without a real sample
  still fall back to the built-in kit.
- **Open an existing chart.** Import a `.dtx` (notes only) or a chart `.zip`/folder (with its
  backing track and jacket) straight into the editor, then edit and re-download. Imported
  charts keep their own drum sounds through both the preview and re-packaging.
- **Hit splash at the judgement line.** Notes flash a colored burst as they cross the line
  during playback, so hits read clearly instead of feeling like misses.

## v1.6.0

A ground-up chart-editor overhaul: a standard transport, a self-review layer, and fast bulk
editing so the last 20% of a transcription is a quick touch-up instead of a bar-by-bar chore.

- **Standard transport bar.** Play/pause in the center, back/forward 5s & 10s, and previous/next
  bar - with the note highway free of controls. Space plays, arrows step bars, and dragging the
  playhead scrubs the audio in both directions.
- **Redo + keyboard shortcuts.** Full undo/redo (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z), plus Ctrl+C /
  Ctrl+V, Delete, and Escape.
- **Review layer.** The app marks where it *heard* a drum hit in the audio but charted nothing
  near it (cyan), and a Review button jumps you through the spots worth checking - so you fix the
  weak cymbal/hi-hat calls instead of hunting for them.
- **Assisted groove copy/paste.** Copy a bar and the overview highlights every repeat; stamp your
  fix onto all of them at once (exact match by default, an optional looser near-match).
- **Marquee selection.** Shift-drag a box to select notes, then copy / paste / delete them - with
  a right-click context menu. Paste carries a pattern into any other bar.
- **Bulk voice cleanups.** One-click, whole-chart fixes for the common transcription artifacts:
  all rides → crash, left crash → crash, thin hi-hats by half, and clear all toms.
- **Jacket image.** Upload a song-select image; it's embedded as `#PREIMAGE` and bundled in the zip.
- **"Clean Up"** replaces the old "Standardize" label, and a notice now tells you when no backing
  track or drum sample could be captured (so you can supply your own `.ogg`).

## v1.5.5

Cleaner cymbals and a recalibration on the full 31-version chart corpus.

- **Cymbals read as crashes.** GITADORA charts don't use a separate ride lane, so audio-only
  charts now voice every detected cymbal as a crash instead of splitting some onto a ride. A new
  precision guard keeps a cymbal only when it lands on a musical accent (with a kick or snare) or
  is a loud, isolated hit - so bleed from the separated stem no longer sprays in phantom cymbals -
  while songs whose groove rides the cymbals keep their full cymbal line.
- **Re-grounded on the complete corpus.** The pattern library and cleanup thresholds were
  recalibrated against the full 31-version, ~8,000-chart corpus (now through GALAXY WAVE DELTA).
  The expanded data confirmed the existing tuning, with the timekeeping cleanup now uniform across
  every difficulty tier.

## v1.5.4

Per-song drum sounds, a clearer update indicator, and a banner fix.

- **Real drum sounds from your song.** Audio-only charts now voice each drum chip with a one-shot
  sliced from that song's own separated stems - so the kick, snare, toms, hats, ride and crash
  sound like the actual recording instead of a fixed synth kit. Any lane without a clean, isolated
  hit falls back to the built-in kit, so a chart is never silent or garbled.
- **"Latest" confirmation.** When you're on the newest release the header now shows a subtle
  "✓ Latest" badge next to the version. When an update exists you get the download banner plus an
  "● Update available" badge.
- **Fixed an empty update bar.** A stray blank bar could appear at the top when you were already on
  the latest version; the update banner now only shows when there's actually a newer release.

## v1.5.3

Black dark mode, a colour-wheel accent picker, and in-app update notifications.

- **True-black dark mode.** Dark mode is now genuine black with neutral panels instead of the
  dimmed-green theme, so the accent colour is what stands out. The default accent is unchanged
  (the deep green), and light mode is untouched.
- **Colour-wheel accent picker.** The accent picker is now an HSV colour wheel with a brightness
  slider, a hex field and a live preview - pick any colour, not just the old presets.
- **Update notifications.** On launch the app checks GitHub for a newer release and shows a
  dismissible banner when one is available. One click downloads the new build straight into your
  Downloads folder (unzip and run to update). Fails silently when offline - no banner, no error.

## v1.5.2

Data-calibrated cleanup thresholds and a regression test that keeps them honest.

- **Keep thresholds are now empirically calibrated, not hand-picked.** A closed-loop calibration
  takes real corpus charts as ground truth, injects synthetic transcription noise into the
  hi-hat/ride (bleed ghosts plus dropped and jittered hits), runs the cleaner at each candidate
  strength, and scores how well the result recovers the original chart (F1 over 1/16 timekeeping
  slots). Averaged over multiple noise seeds and ~160 charts per tier, the data picks a gentler
  keep strength (35 for Basic, 30 for Advanced/Extreme/Master) than the earlier hand-picked
  50/45/38/32, which sat past the plateau and over-cleaned. Kick and snare remain untouched.
- **Grounding regression test.** `test_grounding.py` re-runs a mini calibration and fails if the
  shipped thresholds ever drift off the data-optimal plateau, and checks the per-lane note grids
  still match how real charts subdivide each lane.
- **Corpus tooling in the repo.** The mining and calibration scripts used to derive every threshold
  now live under `tools/` (with a README), so the grounding is reproducible from the real charts.

## v1.5.1

Note-preservation fix and a much deeper grounding in real charts.

- **Keeps the notes that belong there.** v1.5.0's DTXMania cleanup was too aggressive - it voted
  the whole groove (including kick and snare) toward a "consensus" and deleted real playing. Now the
  regularization only cleans the bleed-prone **hi-hat / ride timekeeping**; **kick and snare are
  preserved exactly as played**, so fast double-kicks, ghost snares and syncopation all survive.
- **Off-beat timekeeping is respected.** Off-beats are ~40% of every lane's hits in real charts (up
  to 55% at Master), so the cleanup no longer treats an off-beat hi-hat as suspect - disco/funk/ska
  off-beat hats, off-beat ride and varied 16th patterns are kept; only sporadic bleed is removed.
- **Genre-safe.** Jazz swing (triplet ride), shuffle, odd meters (5/4, 7/8, waltz), blast beats,
  double bass, polyrhythm and ghost notes are all left intact - verified by a genre test suite.
- **Tier-aware cleanup.** Grounded in the full corpus (see below), difficulty scales hard - a Master
  chart is 3.5× denser than Basic and off-beat over half the time - so the cleanup is now gentler at
  higher difficulties (where there's more intentional playing) and firmer at lower ones.
- **Grounded in 6,621 real charts.** Every threshold (de-flam window, keep strength, per-lane note
  grids) is now calibrated from the whole deduplicated corpus across both sets and documented in
  `docs/drum-corpus-facts.md` (+ machine-readable `docs/drum_facts*.json`), not assumed.

## v1.5.0

A built-in chart editor, a big step up in charting quality, and a smoother finish flow.

- **Cleaner, more "real" charts (DTXMania Chart Style).** The DTXMania style now grooms the whole
  groove toward the way real charts are actually written, grounded in a corpus of **4,700+ real
  GITADORA/DrumMania charts**. Instead of snapping each bar on its own (which read jittery and
  "thrown together"), it now finds a clean groove for each phrase and **repeats it**, so the chart
  is as consistent bar-to-bar as a real one. Stray, bleed-induced ghost hi-hats are voted out, so a
  quarter-note hat stays a quarter instead of inflating into a busy 8th/16th mess.
- **The whole kit reads neat, not just the hi-hats.** Cymbals, ride and open hi-hats are de-jittered
  onto a clean grid too, so crashes land on the beat instead of between grid lines. Toms are cleaned
  the same way.
- **No more impossible rolls.** During a fast snare roll or tom fill both hands are on the drums, so
  the hi-hat/ride that transcription used to layer on top (physically impossible to play) is now
  removed for the length of the fill.
- **Chart Style options.** When **DTXMania** style is selected, you can group the right cymbal onto
  the ride, and (optionally) map open hi-hats to the left-foot pedal. Left-foot technique (hi-hat
  chick / double bass) is added automatically, tier-appropriate.
- **Visual chart editor.** A new **Review & edit notes** step opens a vertical, one-bar-at-a-time
  editor (DTXMania-style colored lanes). **Click** an empty cell to add a note, **drag** to move it,
  **right-click** to delete; a grid selector (¼ · 8th · ⅓ · 16th · 24 · 32nd) sets the snap. **Undo**
  (button or Ctrl+Z) and a **Reset** that also restores the view. Clean up anything by hand.
- **Game-style playback in the editor.** Notes fall down a highway past a raised **judgement line**
  (a little above the pad icons, like a real rhythm game), the charted drum sounds play as each note
  crosses the line, and the whole-song play animation is smooth. Per-bar **Play** hears just the slice
  under the bar you're editing, with **🐢 Slow / 🐇 Fast** (pitch-preserved), a scroll-speed control,
  and a **loop** toggle. A draggable scrubber seeks and previews exactly where the line sits.
- **De-flam cymbals.** Audio transcription can split one hard cymbal/hi-hat hit into a flam (a phantom
  second onset from decay or mic bleed). Same-lane cymbal/hi-hat hits closer than ~70 ms are collapsed
  to one, so timekeeping reads clean. Toms, snare and kick are left alone (they really do play fast).
- **Downloads land in your Downloads folder.** Clicking **Download chart .zip** now saves the package
  straight to your Downloads folder and shows you the exact path (the in-app browser's download
  handler could silently drop it before). The chart is packaged **once, on download**, after any edits.
- **UI polish.** "Notes Style" is now **Chart Style**; a **Make another chart** button resets the page
  after a download; console shows a blinking cursor while a stage runs; trimmed wording throughout.

## v1.4.1

Fidelity fix - the chart now mirrors the song's actual per-bar note values, at every
difficulty. Grounded in an analysis of **4,700+ real GITADORA/DrumMania charts**, which
showed that charts of *every* tier mix note values freely (even Basic charts contain
16ths and triplets) and that 16th notes are a minority even at Extreme (~11%).

- **Per-bar fidelity (audio "Standardize").** Each bar is now quantized to its **own
  natural subdivision** - quarter, 8th, 16th, 32nd *or* triplet, whichever that bar
  actually plays - instead of a fixed 1/16 grid. A sparse bar stays sparse; the next bar
  with a 16th run or a 32nd fill keeps its density. Triplets are preserved.
- **Difficulty no longer caps note values.** Tiers previously thinned timekeeping to a
  per-tier grid (Basic → 1/4, Advanced → 1/8, Extreme → 1/16). That's removed: a chart of
  **any** difficulty keeps the song's real 16th / triplet / 32nd content. The tier is a
  *rating* of density and complexity, not a note-value ceiling.
- **DTXMania style no longer inflates density.** Its timekeeping pass now only removes
  timing *jitter* (snapping to each bar's own subdivision) and never rewrites a bar to a
  fixed tier grid, so an 8th-note bar stays 8th and a sparse bar stays sparse.
- No new features; generation output is more faithful to the source.

## v1.4.0

DTXMania **Notes style** matured into an empirically-grounded chart generator, a critical
silent-drums fix, and automatic tier-gated foot technique.

- **Fixed: audio-only charts had no drum sounds.** The standardize pass wrote note cells
  as the drum label instead of the DTX WAV slot, so DTXMania played nothing on the pads.
  Cells now reference the correct WAV - drums sound again.
- **Notes style (Transcribed / DTXMania).** The DTXMania regularizer is a first-class **Notes
  style** control that works for **both** a supplied tab and audio transcription, not just
  audio-only. The audio-only toggle is now just **Raw / Standardize**.
- **DTXMania style, grounded in 2,000 real GITADORA charts.** The regularizer was rebuilt against
  an analysis of 2,000 published charts (188,760 bars):
  - **Steady, evenly-spaced timekeeping** at the tier's resolution (80% of real hi-hat bars are
    perfectly even).
  - **One timekeeper per section** - hi-hat *or* ride, chosen per phrase instead of flip-flopping
    bar to bar (the two coexist in only ~0.1% of real bars).
  - **Crashes are preserved, not thinned.** Earlier builds collapsed crashes to one per bar and
    injected a crash on every phrase start; real charts do neither - crashes stack freely with
    kick/snare, and only 31% of phrase downbeats carry one - so both rules were removed.
  - A **closed** hi-hat sharing a crash's tick (a transcription artifact - 3 in 160k real bars)
    is cleaned up; a rare **open** hi-hat under a crash is kept.
- **Automatic, tier-gated foot technique in DTXMania style.** Basic/Advanced add little or none;
  Extreme adds double bass on genuinely fast kick runs; Master adds the hi-hat "chick" on 2 & 4
  too (95% of real Master charts use it, 58% use double bass). The left foot is one resource - a
  hi-hat chick and a double kick never share a tick. The manual **LFHH / DKDK** toggles remain for
  Transcribed style and are handled automatically when DTXMania is selected.
- **Lower density.** Hi-hat and ride are de-conflicted (real charts don't play both at once),
  roughly halving the timekeeping density on busy songs. Master keeps both.
- **Stop button.** A red Stop next to Generate cancels a run mid-generation so you can change
  settings; the pipeline aborts at the next stage boundary.
- **Version** shown in the header; minor UI polish.

## v1.3

Cleaner, more playable audio-only charts, difficulty that actually simplifies, and UI polish.

- **Standardize pass (audio-only).** Raw drum onsets are quantized to a clean **1/16 grid** while
  **genuine 1/32 fills/rolls are preserved**, and doubled / jittered / physically-impossible notes are
  removed - fixing the "too many notes, impossible to play" charts. Toggle **Standardize / Raw** in the
  Advanced card (Raw emits exactly what was heard).
- **Difficulty tiers now thin density.** Lower tiers trim the hi-hat / ride timekeeping (Basic → 1/4,
  Advanced → 1/8, Extreme → 1/16, Master → everything); kick/snare/toms/crashes are untouched. The score
  is re-rated to match the emitted notes.
- **BPM octave correction.** Tempo detection no longer locks onto the half-time pulse (e.g. a 190 BPM punk
  song reading as 95); a well-supported double below 100 BPM is auto-corrected.
- **UI.** Generate button moved to the bottom of the input column, drum emoji removed, card 4 renamed
  **Advanced**, and the default accent is the darker green in dark mode.
- **`uninstall.cmd`** helper reclaims the ~1 GB of downloaded model weights (the app itself is portable -
  just delete the folder).
- **Spotify links** are explicitly unsupported (DRM) - use YouTube / SoundCloud / a direct file / Upload.

## v1.2

Difficulty tiers, required metadata, and a standalone-exe reliability fix.

- **Difficulty tiers.** Basic / Advanced / Extreme / Master picker; the `.dtx` is named by tier
  (`bsc` / `adv` / `ext` / `mstr`) in its `set.def` slot. Auto-derives from the 0.00-9.99 score.
- **Title and Artist are required** (client validation + server guard).
- **Standalone exe launch fix.** The windowed build's local server crashed on startup
  (`'NoneType' object has no attribute 'isatty'`); it now starts cleanly and shows the native window, with
  a browser fallback and a diagnostic log at `%LOCALAPPDATA%\DTXForge\dtxforge.log`.
- **Launcher hardening.** `DTX Forge.cmd` falls back `pythonw → pyw → python` (Microsoft Store Python has
  no `pythonw`); `run.cmd` waits for the server before opening the browser.

## v1.1

Audio-only full-kit transcription, automatic difficulty, and UI refinements.

- **Notation is now optional; audio is required.** Leave the tab blank and DTX Forge
  transcribes the drums straight from the audio.
- **Full-kit audio transcription** - automatically separates the drum track into
  individual pieces to recover a full kit: **kick, snare, toms (high/low/floor),
  open & closed hi-hat, ride, and crash**. Runs two complementary separation models
  (fetched at runtime, not bundled); falls back to a fast built-in detector.
- **Auto difficulty** - leave Difficulty blank and it's rated from a skilled-player
  reference so beginners get a realistic sense of the demand.
- **Any-URL audio** - YouTube, SoundCloud, Bandcamp, Vimeo and 1000+ sites, plus
  direct audio-file links.
- **BPM & difficulty auto-fill** - populate live once detected (never overwrites a
  value you typed).
- **Hi-Hat Pedal** simplified to a single **2 & 4 backbeat** toggle (the game-typical
  pattern).
- **UI** - reordered input cards (Details → Audio → Notation → Advanced),
  source-aware faithfulness (hidden in audio-only mode), "Charted using DTX Forge"
  credit written into the chart.

> Model weights are downloaded at runtime to `%LOCALAPPDATA%/DTXForge` and are **not**
> redistributed. LarsNet weights are CC BY-NC (non-commercial); see `LICENSE`.

## v1.0
First release.

- **Multi-source notation** - Songsterr (URL/id), Guitar Pro (.gp/.gp5/.gpx),
  MIDI, and pasted/uploaded ASCII drum tabs; auto-detected.
- **Audio** - YouTube (tiered: anonymous → browser session cookies → fallback,
  with a bundled deno JS runtime) or file upload.
- **Auto-sync** - aligns YouTube/uploaded audio to the chart via same-recording
  cross-correlation.
- **Drum modes** - Keep (full song), Quiet (~50% drums), Remove (~90% arcade).
- **Hi-Hat Pedal** - 1:1 True / Medium / Off left-foot hi-hat.
- **DKDK Mode** - On/Off double-bass; converts only too-fast-for-one-leg kicks.
- **Human-playability check** - 2-hands/2-feet model with auto-relax.
- **Faithfulness score** - reports how true the chart is to the tab.
- **Pipeline visualizer**, light/dark themes, accent color picker.
- Spec-correct DTXMania channel + GM-drum lane mapping.
