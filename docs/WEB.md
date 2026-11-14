# Web version of the LF+ Editor

A browser build of the editor that runs entirely client-side — nothing to install. Open it, load a
`.syx`, edit, and download the result, all offline. It is a **pixel-for-pixel port of the desktop
build**: all 11 tabs, the same fields/labels/rocker toggles, the graphical Pages editor and the 2×8
Midi/Groups grid, plus the desktop's auxiliary tools. See [PARITY.md](PARITY.md) for the full
desktop↔web comparison and [UAT.md](UAT.md) for the acceptance-test plan that was run against both
builds (identical steps, matching results).

> **Using the editor?** This page is the technical/architecture doc. The user manual — quick start,
> screenshots, and step-by-step scenarios — is **[WEB_GUIDE.md](WEB_GUIDE.md)**.

## Features

- **All 11 tabs**, byte-exact load/edit/save of `.syx` backups.
- **Q-LIST** searchable record dock (browse any type, **drag a record onto a slot** or command row)
  and the full **Find / Q-LIST** dialog: wildcard name search, per-type checkboxes, number range, a
  MIDI-command filter (channel / message type / CC#-PC#), "list each record once", a results table
  (click a row to jump), and **Export results (CSV)**.
- Whole-record **Copy / Paste / Clear**, **Clear labels**, a **Raw byte** view, and right-click
  **multi-apply** of a toggle across a range of records.
- **CSV** import/export and preset/song/set-list/IA-slot/IA-map **reports**.
- **Quick Repeated Command Programmer** and **Re-order Records**.
- **Experimental device I/O** over [WebSerial](WEBSERIAL.md) (Chrome/Edge): Connect, From LF+, and a
  gated To LF+.

## How it works

The browser cannot run PySide6, but it **can** run Python via [Pyodide](https://pyodide.org)
(CPython → WebAssembly). So the web app reuses the *exact* byte-exact codec and data model the
desktop uses — there is **no second implementation to keep in sync**:

```
web/index.html ─┬─ Pyodide (CDN)  ── runs the real lfeditor codec/model/tools
                ├─ web/app.js     ── boot, file open/save, tabs, record nav, Q-LIST/Find,
                │                     copy/paste/clear, raw view, multi-apply, Tools (CSV/reports/…)
                ├─ web/render.js  ── renders the UI from a JSON schema
                ├─ web/serial.js  ── WebSerial device layer (async I/O only; hardware-verified)
                └─ web/style.css  ── faithful FAMC dark theme
```

- **`lfeditor/schema.py`** (pure Python) introspects the desktop's spec-driven tab definitions
  (`ui/specs.py` → `Field`/`Section`/`TabSpec`, importable without Qt thanks to
  `ui/fields.py::_HAVE_QT` and the Qt-free `ui/tabspec.py`) and emits a JSON description of every
  tab: columns → sections → fields with byte offsets, kinds and options. `render.js` builds the
  faithful widgets from it, so the web and desktop UIs are generated from one source. The two
  bespoke tabs (Pages, Midi/Groups) carry hand-written descriptors with the byte offsets their JS
  renderers need.
- **`lfeditor/webapi.py::Session`** is the thin, Qt-free API the JavaScript drives. It never
  re-implements anything — it reuses the existing pure-Python modules so the web and desktop can't
  drift:
  - editing: `load`/`save`, `get`/`set`, `get_str`/`set_str`, `names`, `decode_button`, command
    tables (`channel_names`, `midi_msg_types`, `decode_command`) and ext-record labels.
  - tools: `copy_record`/`paste_record`/`clear_record`/`clear_labels` (`ui/record_ops.py`),
    `multi_apply`, `raw_bytes`, `find` (`search.py`), `export_text`/`import_text`/`report_text`
    (`csvio.py`; reports are implemented in `reports.py` with compatible exports), `quick_apply` (`quickprog.py`), `move_record` (`reorder.py`).
  - device: `dev_*` wrap `comms/protocol.py` (handshake/read/`.syx`-write framing) — see below.

  Every edit mutates a frame's decoded `values`, so `save()` re-encodes **byte-exact**, exactly like
  the desktop.
- **`web/make_bundle.py`** zips the Qt-free `lfeditor` source + the 8 factory `.syx` into
  `web/lfeditor_bundle.zip`; the app unpacks it into Pyodide's filesystem and `import lfeditor`.

## Device I/O

The web build can talk to an LF+ over USB via the **WebSerial API** (Chrome/Edge). Pyodide can't
block on async serial, so the byte-level protocol stays in Python (`comms/protocol.py`) and
`web/serial.js` does only the async `navigator.serial` reads/writes. **Verified on real hardware**
(2026-07-13: browser pull byte-identical to a desktop pull; writes ACK and read back) — reads are
non-destructive, writes are gated behind a confirm. Full details in [WEBSERIAL.md](WEBSERIAL.md).

## Local development

```bash
python web/make_bundle.py            # build web/lfeditor_bundle.zip
python web/devserver.py 8000         # no-cache static server (plain http.server caches JS)
# open http://localhost:8000   (file:// won't work — fetch needs http; WebSerial needs https/localhost)
```

`web/devserver.py` serves `web/` with `Cache-Control: no-store` so edits show on reload (the stock
`python -m http.server` heuristically caches `app.js`/`render.js` and serves stale code). The asset
`<script>`/`<link>` tags also carry a `?v=` query that is bumped on change.

`web/selftest.html` boots Pyodide, loads a factory file, and asserts a byte-exact round-trip in the
browser — the web analogue of the desktop `--selftest`. The Qt-free layer is covered by
`tests/test_web.py` (schema validity, offsets in range, `Session` round-trip, and the copy/paste,
multi-apply, find, CSV, quick-prog and reorder helpers).

## Deployment

`.github/workflows/pages.yml` builds the bundle and deploys `web/` to **GitHub Pages** on every push
to `main`. Enable it once: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

## Limitations

- **Device I/O needs Chrome/Edge** (WebSerial). Firefox and Safari have no WebSerial, so the
  Connect button is disabled there; use the desktop app to talk to hardware from those browsers.
- Songs, Set-Lists, Pages and IA-Switches have bulk USB reads; Songs, Set-Lists and IA-Switches
  also have a per-record fallback when bulk replies are absent (see [WEBSERIAL.md](WEBSERIAL.md)).
- MIDI Monitor / Pass-Thru is implemented using Web MIDI, independently of the WebSerial connection.
  Live expression-pedal calibration is implemented using WebSerial; its presence in the source
  does not establish hardware validation for every browser/model combination.
- The EEPROM wizard and USB MIDI Bridge remain desktop-only. Device resets and firmware loading
  remain disabled in the editor; the separate firmware loader is a beta tool.
- Startup fetches Pyodide from a CDN and the Python bundle from the server. Browser caching is
  not an offline-install mechanism; offline reloads are not guaranteed.
