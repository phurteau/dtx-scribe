# PyInstaller spec for DTXScribe (onedir desktop app)
from PyInstaller.utils.hooks import collect_all, collect_submodules
import os, re, shutil

datas, binaries, hiddenimports = [], [], []


# ------------------------------------------------------------------
#  Version resource: read dtxscribe.__version__ (single source of truth)
#  and emit a Windows VSVersionInfo file so the built exe carries a real
#  FileVersion / ProductVersion / ProductName (visible in Properties ->
#  Details, and how the folder advertises which build it is).
# ------------------------------------------------------------------
def _read_version():
    try:
        txt = open(os.path.join(os.getcwd(), "dtxscribe", "__init__.py"),
                   encoding="utf-8").read()
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', txt)
        return m.group(1) if m else "0.0.0"
    except Exception:
        return "0.0.0"

_VER = _read_version()
_parts = [int(x) for x in re.findall(r"\d+", _VER)][:4]
while len(_parts) < 4:
    _parts.append(0)
_vtuple = tuple(_parts)
_vstr = ".".join(str(x) for x in _vtuple)          # e.g. 1.9.6.0

_verfile = os.path.join(os.getcwd(), "version_info.txt")
with open(_verfile, "w", encoding="utf-8") as _vf:
    _vf.write(
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        "    filevers=%(t)s,\n"
        "    prodvers=%(t)s,\n"
        "    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable(u'040904B0', [\n"
        "        StringStruct(u'CompanyName', u'phurteau'),\n"
        "        StringStruct(u'FileDescription', u'DTXScribe - DTXMania drum-chart generator'),\n"
        "        StringStruct(u'FileVersion', u'%(v)s'),\n"
        "        StringStruct(u'InternalName', u'DTXScribe'),\n"
        "        StringStruct(u'OriginalFilename', u'DTXScribe.exe'),\n"
        "        StringStruct(u'ProductName', u'DTXScribe'),\n"
        "        StringStruct(u'ProductVersion', u'%(v)s')])\n"
        "    ]),\n"
        "    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n" % {"t": repr(_vtuple), "v": _vstr})

# heavy / tricky packages: grab everything (py + data + dylibs)
for pkg in ["demucs", "torch", "yt_dlp", "imageio_ffmpeg", "soundfile",
            "julius", "einops", "dora", "openunmix", "webview", "pythonnet",
            "clr_loader"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["dtxscribe", "dtxscribe.songsterr", "dtxscribe.audio",
                  "dtxscribe.transcribe", "dtxscribe.dtx", "dtxscribe.drumkit",
                  "dtxscribe.pipeline", "dtxscribe.report", "dtxscribe.notes",
                  "dtxscribe.humanize", "dtxscribe.playability", "dtxscribe.autosync",
                  "dtxscribe.sources", "dtxscribe.faithfulness", "dtxscribe.difficulty",
                  "dtxscribe.fullkit", "dtxscribe.larsnet_engine",
                  "dtxscribe.standardize", "dtxscribe.simplify", "dtxscribe.dtxmania_style",
                  "dtxscribe.pattern_match", "dtxscribe.groove_data",
                  "dtxscribe.vendor", "dtxscribe.vendor.larsnet_unet",
                  "guitarpro", "attr", "attrs",
                  "app", "anyio", "mido", "clr", "webview.platforms.winforms"]

# gdown (LarsNet weights fetch) - optional; only needed for the Full kit+ engine
try:
    d, b, h = collect_all("gdown")
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass

# app data files
datas += [("web", "web"), ("assets", "assets")]

block_cipher = None

a = Analysis(
    ["desktop.py"],
    pathex=[os.getcwd()],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DTXScribe",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no console window (native app)
    icon=os.path.join(os.getcwd(), "assets", "icon.ico"),
    version=_verfile,       # embed FileVersion / ProductVersion metadata
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="DTXScribe",
)

# ------------------------------------------------------------------
#  Make the portable folder release-ready: drop the uninstaller and a
#  couple of self-describing markers NEXT TO the exe (not inside
#  _internal, where uninstall.cmd's %~dp0 self-delete would be wrong).
#  This is what actually gets zipped for the Releases page, so without
#  this the README's "run uninstall.cmd" instruction ships a missing file.
# ------------------------------------------------------------------
_distroot = globals().get("DISTPATH", os.path.join(os.getcwd(), "dist"))
_portable = os.path.join(_distroot, "DTXScribe")
if os.path.isdir(_portable):
    _un = os.path.join(os.getcwd(), "uninstall.cmd")
    if os.path.exists(_un):
        shutil.copy2(_un, os.path.join(_portable, "uninstall.cmd"))
    with open(os.path.join(_portable, "VERSION.txt"), "w", encoding="utf-8") as _f:
        _f.write("DTXScribe v%s\n" % _VER)
    with open(os.path.join(_portable, "README.txt"), "w", encoding="utf-8") as _f:
        _f.write(
            "DTXScribe v%s (portable)\r\n"
            "\r\n"
            "Run:        double-click DTXScribe.exe\r\n"
            "Uninstall:  run uninstall.cmd - it lists and removes the model\r\n"
            "            weights, cache, logs and shortcuts DTXScribe created,\r\n"
            "            and can delete this folder too. Your saved .dtx charts\r\n"
            "            are never touched.\r\n"
            "\r\n"
            "Everything the app needs lives in the _internal folder - keep it\r\n"
            "next to DTXScribe.exe.\r\n" % _VER)
