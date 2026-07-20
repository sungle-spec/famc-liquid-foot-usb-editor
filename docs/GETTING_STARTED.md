# Getting started

Everything you need to go from zero to editing your Liquid Foot+ — pick your platform, launch the
editor, and (optionally) connect the hardware.

The editor comes in two identical flavours:

| | Best for | Get it |
|---|---|---|
| **Desktop app** (macOS / Windows / Linux) | day-to-day use, full device I/O incl. MIDI monitor, EEPROM wizard, live pedal calibration | [Releases](https://github.com/sungle-spec/famc-liquid-foot-editor-builds/releases) |
| **Web editor** (any modern browser) | nothing to install; device I/O in Chrome/Edge | the hosted page (see below) — or run it locally |

Both are the same code (the web version runs the actual Python codec in your browser via Pyodide),
so files, features, and layout match 1:1.

## 1. Launch the desktop app

### macOS

1. Download the mac zip from the [Releases page](https://github.com/sungle-spec/famc-liquid-foot-editor-builds/releases), unzip, and drag **LF+ Editor (native).app** to Applications.
2. First launch: the app is unsigned, so **right-click → Open → Open** (or clear quarantine with
   `xattr -dr com.apple.quarantine "LF+ Editor (native).app"`).
3. **File → Load Factory Defaults** picks a starting rig, or **File → Open…** loads your `.syx`
   backup.

### Windows

1. **Install the FTDI VCP driver first** if you'll connect a device — see
   [Windows driver setup](#3-windows-install-the-ftdi-vcp-driver-first) below.
2. Download the windows zip from the [Releases page](https://github.com/sungle-spec/famc-liquid-foot-editor-builds/releases), unzip, run `LFPlusEditor.exe`.
3. SmartScreen shows *"Windows protected your PC"* (the app is unsigned) → **More info → Run
   anyway**.

### Linux

1. Download the AppImage from the [Releases page](https://github.com/sungle-spec/famc-liquid-foot-editor-builds/releases), then `chmod +x LFPlusEditor-*.AppImage` and run it.
2. For device access, add yourself to the serial group once:
   `sudo usermod -aG dialout $USER`, then log out/in.

### From source (any OS)

```bash
git clone https://github.com/sungle-spec/famc-liquid-foot-usb-editor
cd famc-liquid-foot-usb-editor
python3 -m venv .venv && source .venv/bin/activate    # Python 3.11+
pip install -r requirements-dev.txt
python -m lfeditor                                    # or: python -m lfeditor yourbackup.syx
```

## 2. Launch the web editor

- **Hosted:** open the GitHub Pages site (linked from the repo header) — nothing to install, your
  file never leaves the browser.
- **Locally:**

  ```bash
  python web/make_bundle.py      # one-time: packs the Python core for the browser
  python web/devserver.py        # serves http://localhost:8000
  ```

Then **Load Factory…** or **Open…** a `.syx`, edit, **Save**. Full manual:
[WEB_GUIDE.md](WEB_GUIDE.md).

Device I/O from the browser needs **Chrome or Edge** (WebSerial) — Firefox/Safari can edit files
but can't talk to the hardware.

## 3. Windows: install the FTDI VCP driver first

The Liquid Foot+ speaks USB-serial through an FTDI chip. On Windows, **both the web editor and the
desktop app need the FTDI VCP (Virtual COM Port) driver** before the device shows up as a COM
port:

1. Most systems already have it (Windows Update installs it when the device is plugged in). Plug
   the LF+ in, wait a moment, and check Device Manager → **Ports (COM & LPT)** for a *USB Serial
   Port (COMn)*.
2. If no COM port appears: install the driver from FTDI —
   **<https://ftdichip.com/drivers/vcp-drivers/>** (choose the Windows "setup executable") — then
   replug the device. The same driver also shipped inside the original FAMC editor's installer, so
   machines that ran the original editor are usually already set.
3. Still nothing? Try another USB cable/port (charge-only cables are a classic culprit).

macOS (10.15+) and Linux need no driver — the FTDI driver is in the OS (Linux: just the `dialout`
group membership above).

## 4. Connect your LF+ (macOS one-time setup)

On macOS the LF+ first needs its USB chip switched to the standard FTDI product ID so the built-in
driver picks it up — the editor automates this:

1. Plug the LF+ in, open the desktop editor, and run **Hardware → Device Connection Setup…** —
   the wizard detects the device state, **saves a full EEPROM backup**, then applies the one-time,
   reversible change. It needs `libusb`: `brew install libusb`.
2. Then **Hardware → Connect** (or the toolbar **Connect**) puts the device in Editor Mode;
   **From LF+** reads your rig; **To LF+** writes edits back (always behind a confirmation).

Step-by-step with screenshots: **[DESKTOP_GUIDE.md — first-time setup](DESKTOP_GUIDE.md#first-time-setup-make-the-device-appear-as-a-serial-port)**.
Windows/Linux devices that already show a serial port skip straight to Connect. In the web editor,
click **Connect** and pick the port in the browser prompt ([details](WEBSERIAL.md)). What the
wizard actually does under the hood, and what to expect: **[EEPROM_SWITCH.md](EEPROM_SWITCH.md)**.

## 5. Next steps

- **[DESKTOP_GUIDE.md](DESKTOP_GUIDE.md)** — the full illustrated desktop manual (every menu, tab, and scenario).
- **[WEB_GUIDE.md](WEB_GUIDE.md)** — the same for the web editor.
- **[USER_GUIDE.md](../USER_GUIDE.md)** — compact all-in-one reference.
- **Always keep backups**: **Backup** in the toolbar writes a timestamped copy before you experiment.
