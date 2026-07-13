"""
About dialog — version, attribution, the MIT license, and the legal / hardware-safety notice.

Self-contained: the license + notice text is embedded so it renders in the packaged .app even
when the repo-root LICENSE file isn't shipped. If a LICENSE file is present next to the source
(developer checkout) its text is preferred, so the dialog and the file never drift.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QWidget, QTextEdit,
    QPushButton, QDialogButtonBox,
)

from .. import __version__

EMULATES = "v6.31"

_ABOUT_HTML = f"""
<h2 style="margin-bottom:2px;">LF+ Editor <span style="font-weight:normal;">(native)</span></h2>
<p style="margin-top:0;color:#9fb3c8;">Version {__version__} &nbsp;•&nbsp; emulates FAMC LF+ Editor {EMULATES}</p>
<p>A faithful, cross-platform rewrite of FAMC's official <b>LF+ Editor</b> for the
<b>Liquid Foot+</b> MIDI foot-controller family (12+, 12, Mini, JR, Pro). It opens, edits and
saves the device's <code>.syx</code> backups <b>losslessly</b>, and talks to the hardware over
USB-serial / MIDI.</p>
<p>FAMC, LLC is out of business and the original 2020 Xojo editor will eventually stop running on
modern operating systems. This independent rebuild — for interoperability and preservation — keeps
your rig editable.</p>
<p style="color:#9fb3c8;">Built with Python &amp; PySide6 (Qt). Not affiliated with or endorsed by
FAMC, LLC. &ldquo;Liquid Foot&rdquo; and &ldquo;FAMC&rdquo; are the marks of their respective owners.</p>
"""

# Fallback copy of LICENSE, used when the repo-root file isn't available (packaged build).
_LICENSE_FALLBACK = """MIT License

Copyright (c) 2026 sungle-spec

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

_LEGAL_HTML = """
<h3>Scope &amp; third-party notice</h3>
<p>The MIT license covers the original work in this project: the editor application, the
reverse-engineering / diagnostic scripts, the tests, and the documentation.</p>
<p>It does <b>not</b> grant rights to FAMC, LLC material. The Liquid Foot+ firmware, the original
LF+ Editor, the product manual, and captured device sysex dumps are included or referenced only as
fixtures for interoperability, preservation and testing. FAMC is defunct, but these artifacts may
carry third-party rights and must not be redistributed as part of a paid product without satisfying
yourself as to their status. Bundled FAMC <i>factory-default</i> backups (used by
<i>File &rsaquo; Load Factory Defaults</i>) are FAMC's data, shipped for hardware owners' convenience.</p>
<h3 style="color:#e0b341;">Hardware-safety disclaimer</h3>
<p>This tool can write presets to audio hardware and, optionally, rewrite an FTDI EEPROM. It can
overwrite your presets and, if the EEPROM step is interrupted or misused, can render the device's
USB interface unusable. <b>Use entirely at your own risk.</b> Back up your presets (and the EEPROM)
before use. The authors accept no liability for damaged presets or hardware.</p>
"""


def _license_text() -> str:
    """Prefer the repo's LICENSE file (dev checkout); fall back to the embedded copy."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", "..", "LICENSE"))
    try:
        with open(candidate, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return _LICENSE_FALLBACK


def _rich_page(html: str) -> QWidget:
    page = QTextEdit()
    page.setReadOnly(True)
    page.setHtml(html)
    return page


def _mono_page(text: str) -> QWidget:
    page = QTextEdit()
    page.setReadOnly(True)
    page.setLineWrapMode(QTextEdit.WidgetWidth)
    page.setStyleSheet("QTextEdit { font-family: Menlo, Consolas, monospace; font-size: 11px; }")
    page.setPlainText(text)
    return page


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About LF+ Editor (native)")
        self.setMinimumSize(560, 460)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(_rich_page(_ABOUT_HTML), "About")
        tabs.addTab(_mono_page(_license_text()), "License")
        tabs.addTab(_rich_page(_LEGAL_HTML), "Legal & Safety")
        lay.addWidget(tabs, 1)

        row = QHBoxLayout()
        copy = QPushButton("Copy version info")
        copy.clicked.connect(self._copy_version)
        row.addWidget(copy)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        row.addWidget(buttons)
        lay.addLayout(row)

    def _copy_version(self):
        QGuiApplication.clipboard().setText(version_string())


def version_string() -> str:
    return f"LF+ Editor (native) {__version__} — emulates FAMC LF+ Editor {EMULATES}"
