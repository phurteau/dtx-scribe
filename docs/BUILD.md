# Building the standalone .exe

The pre-built app is distributed as a zip (see the Releases page). To build it
yourself from source:

## Prerequisites
- Windows 10/11, Python 3.10+
- `pip install -r requirements.txt`
- `pip install pyinstaller demucs soundfile`  (Demucs pulls in PyTorch, ~2 GB)
- deno in `assets/bin/deno.exe` (run `setup.cmd`, or download from
  https://github.com/denoland/deno/releases)

## Build
```bat
python -m PyInstaller --noconfirm --clean DTXScribe.spec
```
Output lands in `dist/DTXScribe/` - a folder containing `DTXScribe.exe` plus an
`_internal/` folder with all dependencies (torch, ffmpeg, deno, the web UI, and
the drum-kit samples). Zip that whole folder to distribute.

The spec makes the folder **release-ready automatically**: it reads
`dtxscribe.__version__`, embeds it as the exe's Windows version resource
(visible in Properties -> Details), and drops `uninstall.cmd`, a `VERSION.txt`
and a portable `README.txt` next to `DTXScribe.exe`. So the zip already carries
the uninstaller the README points at and states which build it is - no manual
copy step. (`version_info.txt` is a generated throwaway and is git-ignored.)

The build is **onedir** (a folder, not a single file) because the PyTorch payload
doesn't pack cleanly into a one-file exe. Total size is ~750 MB unzipped.

## Notes
- `DTXScribe.spec` lists the hidden imports and bundled data. If you add a new
  `dtxscribe/` module, add it to the `hiddenimports` list.
- The torch "sharding_spec not found" warnings during build are harmless
  (deprecated optional submodules).
- UI-only changes (edits to `web/index.html`) don't need a full rebuild - just
  copy the file into `dist/DTXScribe/_internal/web/` and re-zip.
