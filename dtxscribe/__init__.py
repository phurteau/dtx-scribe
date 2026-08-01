"""DTXScribe - automated DTXMania chart generator."""
import os as _os, shutil as _shutil

__version__ = "1.9.8"


def _appdata_base():
    return _os.environ.get("LOCALAPPDATA") or _os.path.join(_os.path.expanduser("~"), ".cache")


def migrate_legacy_appdata():
    """One-time move of the pre-rebrand data folder %LOCALAPPDATA%\\DTXForge to
    %LOCALAPPDATA%\\DTXScribe, so an updated install keeps its already-downloaded
    model weights (~1 GB), cache and logs instead of re-downloading them under the
    new name. Merge-aware and idempotent: safe to call on every launch and from
    either entry point (native window or browser). Never raises."""
    try:
        base = _appdata_base()
        old = _os.path.join(base, "DTXForge")
        new = _os.path.join(base, "DTXScribe")
        if not _os.path.isdir(old) or _os.path.abspath(old) == _os.path.abspath(new):
            return
        if not _os.path.exists(new):
            _os.rename(old, new)                     # clean rename when target is absent
            return
        for name in _os.listdir(old):                # target exists: merge without clobbering
            src, dst = _os.path.join(old, name), _os.path.join(new, name)
            if _os.path.exists(dst):
                continue
            try:
                _shutil.move(src, dst)
            except Exception:
                pass
        try:
            if not _os.listdir(old):
                _os.rmdir(old)
        except Exception:
            pass
    except Exception:
        pass
