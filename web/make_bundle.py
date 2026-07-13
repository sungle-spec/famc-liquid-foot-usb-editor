"""Bundle the Qt-free `lfeditor` core + factory backups into a zip for Pyodide.

The web app unpacks `web/lfeditor_bundle.zip` into Pyodide's filesystem and `import lfeditor`. We ship
the whole package source (it's small, pure text) — only the Qt-free modules are ever imported in the
browser (codec, model, text, csvio, search, resources, schema, webapi); ui/fields.py imports Qt
lazily and degrades, comms/ is never touched. Factory `.syx` files come along so the web "Load
Factory Defaults" works.

Run:  python web/make_bundle.py   (also run automatically in CI before the Pages deploy)
"""
from __future__ import annotations

import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "lfeditor"
OUT = pathlib.Path(__file__).resolve().parent / "lfeditor_bundle.zip"

SKIP_DIRS = {"__pycache__"}


def main() -> int:
    n = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PKG.rglob("*")):
            if p.is_dir() or any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.suffix in (".pyc", ".pyo"):
                continue
            # ship .py source and the bundled factory .syx; nothing else
            if p.suffix not in (".py", ".syx"):
                continue
            z.write(p, p.relative_to(ROOT))  # arcname keeps the `lfeditor/...` import path
            n += 1
    print(f"wrote {OUT.relative_to(ROOT)} — {n} files, {OUT.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
