#!/usr/bin/env python3
"""Regenerate the desktop user-guide screenshots (docs/img/desktop/*.png).

Boots the real MainWindow head-less (offscreen Qt — the app's own rendering, no screen
capture or permissions needed), loads the bundled Liquid Foot+ Pro+ factory program (never
personal rig data), and grabs the window on every tab plus the tool dialogs and detail crops
referenced by docs/DESKTOP_GUIDE.md.

Usage:
    .venv/bin/python scripts/desktop_screenshots.py
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QToolBar  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "img" / "desktop"
SIZE = (1280, 860)

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
    app = QApplication.instance() or QApplication([])
    from lfeditor.ui.theme import build_stylesheet
    app.setStyleSheet(build_stylesheet())

    from lfeditor.resources import factory_path
    from lfeditor.ui.app import MainWindow, TAB_ORDER

    win = MainWindow()
    win.resize(*SIZE)
    win.load(factory_path("Factory_DefaultsPro.syx"))
    win.show()
    app.processEvents()

    def shot(widget, name):
        app.processEvents()
        widget.grab().save(str(OUT / name))
        print("wrote", OUT / name)

    # every tab (full window)
    for i, tab in enumerate(TAB_ORDER):
        win.tabs.setCurrentIndex(i)
        app.processEvents()
        shot(win, TAB_SHOTS[tab])

    # chrome details
    win.tabs.setCurrentIndex(0)
    app.processEvents()
    shot(win.findChild(QToolBar), "toolbar.png")
    presets_tab = win.tabs.currentWidget()
    shot(presets_tab.header, "record-header.png")
    shot(win.qlist, "qlist.png")

    # Presets detail crops: the command table + the IA-state table
    for f in presets_tab._all_fields:
        cls = type(f).__name__
        if cls == "CommandTableField":
            shot(f.w, "presets-commands.png")
        elif cls == "IAStateGridField":
            shot(f.w, "presets-iastates.png")

    # raw byte view
    win.act_raw.setChecked(True)
    presets_tab.set_raw_visible(True)
    app.processEvents()
    shot(presets_tab.tbl, "raw.png")
    presets_tab.set_raw_visible(False)

    # Find / Q-LIST dialog with a live search
    d = win._ensure_find_dialog()
    d.resize(660, 560)
    d.show()
    d.text.setText("Preset #01*")
    d.run_search()
    shot(d, "find.png")
    d.close()

    # Quick Repeated Command Programmer
    from lfeditor.ui.quickprog_dialog import QuickProgDialog
    qp = QuickProgDialog(win, lambda: win.dump, lambda: None)
    qp.show()
    shot(qp, "quickprog.png")
    qp.close()

    # Re-order Records (Save / Sync)
    from lfeditor.ui.reorder_dialog import ReorderDialog
    ro = ReorderDialog(win, lambda: win.dump, lambda: None)
    ro.show()
    shot(ro, "reorder.png")
    ro.close()

    # MIDI Monitor / Pass-Thru (works with no ports; shows the tool's layout)
    from lfeditor.ui.midi_monitor import MidiMonitorDialog
    mm = MidiMonitorDialog(win)
    mm.show()
    shot(mm, "midimonitor.png")
    mm.close()

    # About / License
    from lfeditor.ui.about_dialog import AboutDialog
    ab = AboutDialog(win)
    ab.show()
    shot(ab, "about.png")
    ab.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
