#!/usr/bin/env python3
"""Regenerate the web user-guide screenshots (docs/img/web/*.png).

Drives the web editor head-less with Playwright: boots the app, loads the bundled
Liquid Foot+ Pro+ factory defaults (never personal rig data), walks every tab and
the tool dialogs, and captures the images referenced by docs/WEB_GUIDE.md.

Usage:
    python web/make_bundle.py                # make sure the bundle is current
    python web/devserver.py 8000 &           # serve web/
    .venv/bin/pip install playwright        # chromium itself: `playwright install chromium`
    .venv/bin/python scripts/web_screenshots.py [http://localhost:8000]
"""
from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "img" / "web"
VIEW = {"width": 1280, "height": 860}

TAB_SHOTS = {           # tab name -> file
    "Presets": "tab-presets.png",
    "Set-List": "tab-setlist.png",
    "IA-Slot": "tab-iaslot.png",
    "IA-Maps": "tab-iamaps.png",
    "Midi/Groups": "tab-midigroups.png",
    "Global": "tab-global.png",
    "Songs": "tab-songs.png",
    "Pages": "tab-pages.png",
    "Sysex Msgs": "tab-sysex.png",
    "Exp Pedals": "tab-exppedals.png",
    "Colors": "tab-colors.png",
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEW, device_scale_factor=2)
        page.goto(BASE)
        # wait for Pyodide + the lfeditor bundle to boot
        page.wait_for_function("typeof App !== 'undefined' && !!App.pyodide", timeout=120_000)
        # load the bundled factory defaults (safe, non-personal data)
        page.evaluate("""() => {
            const f = document.getElementById('factory');
            f.value = [...f.options].find(o => o.textContent.includes('Pro+')).value;
            f.dispatchEvent(new Event('change'));
        }""")
        page.wait_for_function("App.loaded === true")

        def shot(name, selector=None):
            target = page.locator(selector) if selector else page
            target.screenshot(path=str(OUT / name))
            print("wrote", OUT / name)

        # chrome
        shot("toolbar.png", "#toolbar")
        shot("record-header.png", "#recordhdr")

        # every tab
        for tab, fname in TAB_SHOTS.items():
            page.evaluate(f"selectTab({tab!r})")
            page.wait_for_timeout(150)
            shot(fname)

        page.evaluate("selectTab('Presets')")
        page.wait_for_timeout(150)
        shot("presets-commands.png", "#content .section:has(table.cmd)")
        shot("presets-iastates.png", "#content .section:has(.iawrap)")

        # Q-LIST dock (opened, filtered)
        page.click("#btn-qlist")
        page.fill("#qlist .qsearch", "12")
        page.dispatch_event("#qlist .qsearch", "input")
        page.wait_for_timeout(100)
        shot("qlist.png", "#qlist")
        page.click("#btn-qlist")   # hide again

        # Find / Q-LIST dialog with a live search
        page.click("#btn-find")
        page.fill(".modal input.wide", "Preset #01*")
        page.click(".modal-foot button:has-text('Search')")
        page.wait_for_timeout(100)
        shot("find.png", ".modal")
        page.click(".modal-foot button:has-text('Close')")

        # Quick Repeated Command Programmer
        page.select_option("#tools", label="Quick Command Programmer…")
        page.dispatch_event("#tools", "change")
        page.wait_for_timeout(100)
        shot("quickprog.png", ".modal")
        page.click(".modal-foot button:has-text('Cancel')")

        # Re-order Records
        page.select_option("#tools", label="Re-order Records…")
        page.dispatch_event("#tools", "change")
        page.wait_for_timeout(100)
        shot("reorder.png", ".modal")
        page.click(".modal-foot button:has-text('Cancel')")

        # raw byte view
        page.click("#btn-raw")
        page.wait_for_timeout(100)
        shot("raw.png", "#rawpanel")
        page.click("#btn-raw")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
