# DTXScribe Roadmap

What's shipped, what's available to try, and what's planned. This is a living document and
scope may change.

## Public preview

Everything we set out to build is now shipped. Record mode, the chart editor, audio and tab
transcription, and the difficulty system are all available today as a public preview. It works
end to end, and we are still smoothing rough edges, so some bugs may still be present. Feedback
is welcome.

## Now available (public preview)

### Record mode - play your own charts on an electronic drum kit

Instead of transcribing a chart from audio or a tab, connect your electronic drum module or use
your computer keyboard, play, and DTXScribe turns your performance straight into a playable
DTXMania chart, then opens it in the editor for cleanup.

**Two ways to record:**

- **Freeplay (default)** - no audio needed. Pick a tempo and a time signature, play to a
  metronome, and hit Stop. Your chart is built from what you played. Nothing to upload,
  nothing to download until you're happy with it.
- **Play-along** - record over an uploaded song. DTXScribe detects the tempo, lets you confirm
  the click lines up with the music, and the song becomes the backing track of your chart.

**How it works:**

1. Pick your input device. The kit is detected even if you turn it on *after* opening the app -
   no restart needed.
2. Set the tempo and time signature (4/4, 3/4, 6/8, 5/4, 7/8, and more). For play-along the
   tempo is detected for you.
3. Optional one-time latency calibration so your hits line up precisely.
4. Press Start, play through the count-in, and record. Your hits print in real time on the lane
   view.
5. Press Stop - your take opens in the editor, ready to tidy up and export.

**Works with your kit.** The core of every mainstream module (kick, snare, toms, hi-hat, crash,
ride) works out of the box over standard MIDI - Yamaha DTX, Roland TD, Alesis, and others.
A quick guided "learn your kit" step captures anything non-standard, so any MIDI drum module is
supported, and your kit profile is saved so you only do it once. No kit? You can play on the
computer keyboard instead, and reassign which key hits which drum.

This is available now in public preview, and we keep refining it from testing and feedback.

## Recently shipped

### v1.9.6
- Smarter tempo detection, so a fast song is less likely to be charted at half speed.
- Wider Roland hi-hat support (edge and foot-splash notes).

### v1.9.5
- Record mode, in public preview.
- A finer 1.0 to 9.99 difficulty scale.
- Remappable keyboard-to-pad keys.
- Clean shutdown with nothing left running in the background.

### v1.9.0
- Full-length songs in the chart - the complete intro and outro are kept, not trimmed.
- More reliable YouTube downloads.
- New app icon and a full uninstaller.

### v1.8.0
- Rearrange the editor lanes into your preferred order, with a smooth drag animation.
- Lane grouping (Full / Standard / Custom) to fold voices the way a DTXMania kit reads them.
- Full-length playback in the editor, including the outro.

### v1.7.0
- The app was renamed from DTX Forge to DTXScribe.

See [CHANGELOG.md](CHANGELOG.md) for the full history.

## What's next

Future releases focus on accuracy and refinement rather than big new features:

- Broader electronic drum coverage, checked against the published MIDI maps for more modules, so
  more kits chart correctly out of the box.
- Capturing dynamics (accents and ghost notes) from your playing.
- Smarter automatic clean-up of repeated patterns.
- A pickable drum sample pack for recorded charts, so the kit can sound closer to a real kit.

Feedback and testing are welcome. Open an issue with what you'd like to see.
