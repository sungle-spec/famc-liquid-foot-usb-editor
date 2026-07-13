"""
End-to-end offline UAT, codified.

These drive the real `MainWindow` head-less (offscreen Qt) the way a user would: open every
shipped fixture + factory file, walk every record on every tab, perturb every interactive widget
and confirm the edit reaches the byte buffer, exercise the bespoke Midi/Groups and Pages tabs,
run the menu actions, and prove save/reload stays byte-exact. The exploratory version lives in
`scripts/uat_drive.py`; this is the regression-locked subset.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import tempfile

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import (
    QApplication, QMessageBox, QComboBox, QLineEdit, QSpinBox, QPushButton, QWidget,
)

from lfeditor.resources import FACTORY_DEFAULTS, FACTORY_SPECIAL, factory_path

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "reference" / "sysex_dumps"
RJM = str(FIXTURES / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _silence_dialogs(monkeypatch):
    """Auto-accept every confirm dialog so gated actions proceed head-less."""
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "about", staticmethod(lambda *a, **k: None))


def _win(qapp, path=RJM):
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load(path)
    return w


# ---- helpers (mirrors of scripts/uat_drive.py, kept inline so the test is self-contained) ----

_INTERACTIVE = (QComboBox, QLineEdit, QSpinBox, QPushButton)


def _child_widgets(field):
    seen, out, roots = set(), [], []
    top = getattr(field, "w", None)
    if isinstance(top, QWidget):
        roots.append(top)
    for attr in vars(field).values():
        if isinstance(attr, (list, tuple)):
            roots += [x for x in attr if isinstance(x, QWidget)]
        elif isinstance(attr, dict):
            roots += [x for x in attr.values() if isinstance(x, QWidget)]
    for root in roots:
        for wdg in [root] + root.findChildren(QWidget):
            if id(wdg) not in seen:
                seen.add(id(wdg))
                if isinstance(wdg, _INTERACTIVE):
                    out.append(wdg)
    return out


def _perturb(wdg):
    if not wdg.isEnabled():
        return False
    if isinstance(wdg, QComboBox):
        if wdg.count() < 2:
            return False
        i = (wdg.currentIndex() + 1) % wdg.count()
        wdg.setCurrentIndex(i)
        wdg.activated.emit(i)
        return True
    if isinstance(wdg, QSpinBox):
        new = wdg.value() + (1 if wdg.value() < wdg.maximum() else -1)
        if new == wdg.value():
            return False
        wdg.setValue(new)
        wdg.editingFinished.emit()
        return True
    if isinstance(wdg, QLineEdit):
        if wdg.isReadOnly() or wdg.maxLength() < 1:
            return False
        old = wdg.text()
        new = (old[:-1] + "X") if old and not old.endswith("X") else (old + "1")[:wdg.maxLength()]
        if new == old:
            new = "0" * min(2, wdg.maxLength())
        wdg.setText(new)
        wdg.editingFinished.emit()
        return True
    if isinstance(wdg, QPushButton) and wdg.isCheckable():
        wdg.setChecked(not wdg.isChecked())
        wdg.toggled.emit(wdg.isChecked())
        wdg.clicked.emit()
        return True
    return False


# ---- 1. every shipped file loads byte-exact and walks without mutation ----

ALL_FILES = [(p.name, str(p)) for p in sorted(FIXTURES.glob("*.syx"))] + [
    (fname, factory_path(fname)) for _l, fname in FACTORY_DEFAULTS + FACTORY_SPECIAL
]


@pytest.mark.parametrize("name,path", ALL_FILES, ids=[n for n, _ in ALL_FILES])
def test_file_loads_byte_exact_and_walks_clean(qapp, name, path):
    w = _win(qapp, path)
    raw = pathlib.Path(path).read_bytes()
    assert w.dump.to_bytes() == raw, f"{name} did not round-trip on load"

    before = w.dump.to_bytes()
    for tab in w.tab_widgets:
        rail = getattr(tab, "rail", None)
        if rail is None:
            continue
        for r in range(rail.list.count()):
            rail.list.setCurrentRow(r)
    assert w.dump.to_bytes() == before, f"{name}: navigation mutated bytes"


# ---- 2. perturbing every widget reaches the byte buffer and still round-trips ----

def test_heavy_edit_writes_back_and_round_trips(qapp):
    w = _win(qapp)
    before = w.dump.to_bytes()   # snapshot ONCE — a full-dump serialize per widget is O(records×widgets)
    perturbed = 0
    for tab in w.tab_widgets:
        rail = getattr(tab, "rail", None)
        if rail is not None and rail.list.count():
            rail.list.setCurrentRow(0)
        for f in getattr(tab, "_all_fields", []):
            for wdg in _child_widgets(f):
                if _perturb(wdg):
                    perturbed += 1
    assert perturbed > 100, f"only {perturbed} widgets exercised"
    assert w.dump.to_bytes() != before, "no edits reached the byte buffer"

    with tempfile.NamedTemporaryFile(suffix=".syx", delete=False) as tf:
        tmp = tf.name
    try:
        w.dump.to_file(tmp)
        w2 = _win(qapp, tmp)
        assert w2.dump.to_bytes() == pathlib.Path(tmp).read_bytes()
    finally:
        os.unlink(tmp)


# ---- 3. bespoke tabs (no _all_fields) write back ----

def test_midi_groups_controls_write_back(qapp):
    from lfeditor.ui.tabs.midi_groups_tab import MidiGroupsTab
    w = _win(qapp)
    mg = next(t for t in w.tab_widgets if isinstance(t, MidiGroupsTab))
    groups = {
        "exclusive": [getattr(f, "w", None) for f in getattr(mg, "_excl", [])],
        "grouped": list(getattr(mg, "_grp_combos", [])),
        "names": list(getattr(mg, "_name_edits", [])),
        "maxpre": list(getattr(mg, "_maxpre", [])),
        "plus1": list(getattr(mg, "_tg_plus1", [])),
        "send": list(getattr(mg, "_tg_send", [])),
        "msb": list(getattr(mg, "_tg_msb", [])),
    }
    for gname, widgets in groups.items():
        wrote = 0
        for wdg in widgets:
            if wdg is None:
                continue
            snap = w.dump.to_bytes()
            if _perturb(wdg) and w.dump.to_bytes() != snap:
                wrote += 1
        assert wrote > 0, f"Midi/Groups {gname}: no control wrote to bytes"


def test_pages_controls_and_swap_write_back(qapp):
    from lfeditor.ui.tabs.pages_tab import PagesTab
    w = _win(qapp)
    pg = next(t for t in w.tab_widgets if isinstance(t, PagesTab))
    pg.rail.list.setCurrentRow(0)
    pg._select(0)
    groups = {
        "params": [getattr(f, "w", None) for f in getattr(pg, "_param_fields", [])],
        "ftypes": list(getattr(pg, "f_types", [])),
        "fvalues": list(getattr(pg, "f_values", [])),
        "trig": [getattr(pg, "trig", None)],
    }
    for gname, widgets in groups.items():
        wrote = 0
        for wdg in widgets:
            if wdg is None:
                continue
            snap = w.dump.to_bytes()
            if _perturb(wdg) and w.dump.to_bytes() != snap:
                wrote += 1
        assert wrote > 0, f"Pages {gname}: no control wrote to bytes"

    snap = w.dump.to_bytes()
    pg._swap(0, 1, False)
    assert w.dump.to_bytes() != snap, "tile drag-swap did not mutate bytes"


# ---- 4. a known value survives a full save/reload (encode symmetry) ----

def test_known_value_survives_save_reload(qapp):
    w = _win(qapp)
    presets = w.tab_widgets[0]
    presets.rail.list.setCurrentRow(0)
    presets.header.name.setText("UAT_NAME_7")
    presets.header.name.editingFinished.emit()

    with tempfile.NamedTemporaryFile(suffix=".syx", delete=False) as tf:
        tmp = tf.name
    try:
        w.path = tmp
        w.save_file()
        assert not w._dirty
        w2 = _win(qapp, tmp)
        assert (w2.dump.presets[0].name or "").strip() == "UAT_NAME_7"
    finally:
        os.unlink(tmp)


# ---- 5. menus: every factory file loads as untitled+dirty with full preset bank ----

@pytest.mark.parametrize("label,fname", FACTORY_DEFAULTS + FACTORY_SPECIAL,
                         ids=[l for l, _ in FACTORY_DEFAULTS + FACTORY_SPECIAL])
def test_menu_load_factory(qapp, label, fname):
    w = _win(qapp)
    w.load_factory(fname, label)
    assert w.path is None and w._dirty
    assert w.dump.counts().get("Preset", 0) == 384


# ---- 6. transfer buttons are graceful with no device attached ----

def test_transfers_safe_offline(qapp):
    w = _win(qapp)
    assert w.transport is None
    # none of these should raise without a connected device
    w.transfer("to", 1, 0)
    w.transfer("from", 1, 0)
    w.transfer("all_to", 1, 0)
    w.push_to_device()
    w.pull_from_device()


# ---- 7. theme stylesheet builds (the full --selftest runs against each frozen bundle in CI) ----

def test_build_stylesheet_returns_qss(qapp):
    # The end-to-end `--selftest` (build window + apply stylesheet + load a factory file) is run
    # against the real frozen binary by the CI build job on every OS; doing it again in-process is
    # redundant and uniquely slow (it's the only test that styles a freshly-built MainWindow). Here
    # we just confirm the stylesheet builder works (it also writes its spin-arrow PNGs).
    from lfeditor.ui.theme import build_stylesheet
    qss = build_stylesheet()
    assert isinstance(qss, str) and len(qss) > 500
