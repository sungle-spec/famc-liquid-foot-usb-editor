# Building & releasing the LF+ Editor

The editor is pure Python + PySide6, so it runs on macOS, Windows and Linux from the same source
tree — **no fork, no platform branch of the code**. This repo is the **source** repo: run it with
`python -m lfeditor`, test it with `pytest`, and CI here runs the test suite on all three OSes
(`.github/workflows/tests.yml`).

**Packaging and the OS builds live in a separate repo:**
[famc-liquid-foot-editor-builds](https://github.com/sungle-spec/famc-liquid-foot-editor-builds).
It holds the PyInstaller spec, the icon generator, the Linux AppImage tooling, and the 3-OS
build/release workflow — and it hosts the **Releases** users download.

## Producing bundles

In the builds repo: **Actions → build → Run workflow**, with

- `ref` — the branch / tag / SHA of *this* repo to build (default `main`);
- `release_tag` — optional. Set it (e.g. `v0.0.3`; it must equal `lfeditor.__version__` at that
  ref) to publish the three bundles + `SHA256SUMS.txt` as a Release on the builds repo. Leave it
  empty to just get run artifacts.

Each OS runner checks out this repo, overlays `packaging/`, builds, and runs the frozen binary's
`--selftest` (build the window head-less, load a bundled factory file, check all tabs) before
packaging — a broken bundle fails CI instead of a user's first launch.

The builds repo checks this repo out anonymously (both are public) — no token setup needed.

## Cutting a release

1. Bump `lfeditor/__init__.py::__version__` here and merge to `main`.
2. Run the builds-repo workflow with `ref: main` and `release_tag: vX.Y.Z`.

The release job re-verifies tag == version, generates one combined `SHA256SUMS.txt`, and attaches
everything to a GitHub Release on the builds repo. Users verify with `sha256sum -c SHA256SUMS.txt`
(macOS: `shasum -a 256 -c`).

## Building locally

Clone both repos, overlay, build (on the OS you're targeting — PyInstaller can't cross-compile):

```bash
git clone https://github.com/sungle-spec/famc-liquid-foot-editor-builds builds
cp -R builds/packaging ./packaging          # from this repo's root
pip install -r requirements-dev.txt pillow
python packaging/make_icons.py
pyinstaller --noconfirm packaging/lfeditor.spec
./dist/LFPlusEditor/LFPlusEditor --selftest   # Windows: dist\LFPlusEditor\LFPlusEditor.exe
```

Linux AppImage afterwards: `bash packaging/linux/make_appimage.sh`. The overlaid `packaging/`
copy is git-ignored here — the builds repo is its home.

## Runtime notes for users

* **Windows** — the Liquid Foot+ needs the **FTDI VCP driver** for the USB-serial port to appear
  (most systems already have it via Windows Update). The app is unsigned, so SmartScreen shows
  *"Windows protected your PC"* → **More info → Run anyway**.
* **Linux** — serial ports (`/dev/ttyUSB*`) require membership in the `dialout` group:
  `sudo usermod -aG dialout $USER` then log out/in. Make the AppImage executable
  (`chmod +x *.AppImage`) and run it.
* **macOS** — the app is unsigned/un-notarized, so Gatekeeper blocks the first launch:
  **right-click → Open → Open**, or `xattr -dr com.apple.quarantine "LF+ Editor (native).app"`.

## Deferred: code signing

Not wired up yet (it needs your certificates):

* **macOS** — `codesign --deep --options runtime` with a Developer ID, then `notarytool submit`
  + `stapler staple`. Add the cert (`.p12`) and an app-specific password as builds-repo secrets
  and a signing step before the `ditto` zip.
* **Windows** — Authenticode-sign `LFPlusEditor.exe` with `signtool` using an EV/OV code-signing
  cert. Add the cert + password as secrets and a signing step before `Compress-Archive`.

Until then, the runtime notes above tell users how to get past the OS warnings.
