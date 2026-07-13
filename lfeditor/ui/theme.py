"""Dark theme reproducing the original LF+ Editor v6.31 look.

The original is a charcoal/black app with rounded titled panels, bright-green "LCD" name
fields, red rocker-switch toggles, and a blue FAMC logo. We approximate that with Qt QSS plus
a few custom-painted widgets (see components.py). Colours are tuned against the captured
screenshots in docs/ui/.
"""

# --- palette -------------------------------------------------------------------------------
ACCENT = "#36c9d4"        # FAMC cyan (tab title / section headings)
ACCENT_DIM = "#1f7d85"
GREEN = "#5dd84f"         # bright LCD green (name fields, "On" state, active)
GREEN_DIM = "#2e7d32"
RED = "#d8423a"           # connect-off / red rocker / "Off" LED
AMBER = "#d8a200"
BG = "#23272b"            # window background (near-black charcoal)
PANEL = "#2c3137"         # panel background
PANEL_DK = "#1c2024"      # inset/table background
PANEL_LIGHT = "#3a4046"
FIELD = "#11151a"         # input field background (dark inset)
LCD_BG = "#0c1a0c"        # green-LCD field background
TEXT = "#e6e6e6"
TEXT_DIM = "#9aa0a6"
BORDER = "#15181c"
BORDER_LIGHT = "#3f464d"

QSS = f"""
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ background: {BG}; color: {TEXT};
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; font-size: 12px; }}

/* ---- toolbar / header chrome ---- */
QToolBar {{ background: {PANEL}; border: none; border-bottom: 1px solid {BORDER};
    padding: 5px 6px; spacing: 3px; }}
QToolButton {{ background: {PANEL_LIGHT}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 7px 11px; min-width: 40px; color: {TEXT}; }}
QToolButton:hover {{ background: {ACCENT_DIM}; }}
QToolButton:pressed {{ background: {ACCENT}; color: {BG}; }}
QToolButton:disabled {{ color: {TEXT_DIM}; background: {PANEL}; }}
QMenuBar {{ background: {PANEL}; color: {TEXT}; }}
QMenuBar::item:selected {{ background: {ACCENT_DIM}; }}
QMenu {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}

/* ---- tab bar ---- */
QTabWidget::pane {{ border: 1px solid {BORDER}; background: {PANEL}; top: -1px; }}
QTabBar::tab {{ background: {PANEL_DK}; color: {TEXT_DIM}; padding: 6px 12px;
    border: 1px solid {BORDER}; border-bottom: none; margin-right: 1px;
    border-top-left-radius: 5px; border-top-right-radius: 5px; }}
QTabBar::tab:selected {{ background: {PANEL}; color: {ACCENT}; font-weight: 700; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

/* ---- lists / tables ---- */
QListWidget, QTableWidget, QTreeWidget {{ background: {PANEL_DK}; border: 1px solid {BORDER};
    alternate-background-color: {PANEL}; selection-background-color: {ACCENT_DIM};
    selection-color: white; outline: none; }}
QTableWidget {{ gridline-color: {BORDER}; }}
QHeaderView::section {{ background: {PANEL_LIGHT}; color: {TEXT_DIM}; border: none;
    border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER}; padding: 4px 6px;
    font-weight: 600; }}

/* ---- inputs ---- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{ background: {FIELD};
    border: 1px solid {BORDER}; border-radius: 4px; padding: 3px 6px; color: {TEXT};
    selection-background-color: {ACCENT_DIM}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 16px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM}; }}
QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 16px;
    background: {PANEL_LIGHT}; border-left: 1px solid {BORDER};
    border-top-right-radius: 4px; }}
QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 16px;
    background: {PANEL_LIGHT}; border-left: 1px solid {BORDER};
    border-bottom-right-radius: 4px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {BORDER_LIGHT}; }}
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{ background: {ACCENT}; }}
/* up-arrow / down-arrow images are injected by build_stylesheet() (Qt won't render
   CSS-border triangles for spin arrows, so we paint tiny PNGs at runtime). */

/* ---- green "LCD" name fields (set objectName 'lcd') ---- */
QLineEdit#lcd {{ background: {LCD_BG}; color: {GREEN}; border: 1px solid {BORDER};
    border-radius: 4px; font-weight: 700; font-family: "Menlo", "Courier New", monospace;
    padding: 4px 8px; }}
QLineEdit#lcd:focus {{ border: 1px solid {GREEN}; }}

/* ---- titled section panel (set objectName 'section' on a QGroupBox) ---- */
QGroupBox {{ border: 1px solid {BORDER_LIGHT}; border-radius: 7px; margin-top: 16px;
    padding: 10px 8px 8px 8px; background: {PANEL}; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px;
    padding: 2px 8px; color: {TEXT_DIM}; font-weight: 700; background: transparent; }}
QGroupBox#section::title {{ color: {ACCENT}; }}

/* ---- scrollbars (distinct handle so it doesn't blend into panels/tables) ---- */
QScrollBar:vertical {{ background: {BG}; width: 13px; margin: 0; border-left: 1px solid {BORDER}; }}
QScrollBar::handle:vertical {{ background: {BORDER_LIGHT}; border: 1px solid {PANEL_LIGHT};
    border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 13px; margin: 0; border-top: 1px solid {BORDER}; }}
QScrollBar::handle:horizontal {{ background: {BORDER_LIGHT}; border: 1px solid {PANEL_LIGHT};
    border-radius: 5px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT_DIM}; }}

/* ---- transfer + action buttons ---- */
QPushButton {{ background: {PANEL_LIGHT}; border: 1px solid {BORDER}; border-radius: 5px;
    padding: 5px 10px; color: {TEXT}; }}
QPushButton:hover {{ background: {ACCENT_DIM}; }}
QPushButton:pressed {{ background: {ACCENT}; color: {BG}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; background: {PANEL}; }}
QPushButton#xfer {{ background: #243b46; border: 1px solid {ACCENT_DIM}; color: {ACCENT};
    font-weight: 600; }}
QPushButton#xfer:hover {{ background: {ACCENT_DIM}; color: white; }}
QPushButton#xfer:disabled {{ background: {PANEL}; border: 1px solid {BORDER}; color: {TEXT_DIM}; }}

/* ---- status bar / headings ---- */
QStatusBar {{ background: {PANEL}; color: {TEXT_DIM}; }}
QLabel#status {{ color: {TEXT_DIM}; }}
QLabel#h {{ color: {ACCENT}; font-size: 14px; font-weight: 700; }}
QLabel#tabTitle {{ color: {ACCENT}; font-size: 15px; font-weight: 800; }}
QLabel#sectionNote {{ color: {TEXT_DIM}; font-size: 11px; }}

/* ---- Pages: switch tiles ---- */
QFrame#switchtile {{ background: transparent; border: 2px solid transparent; border-radius: 7px; }}
QFrame#switchtile[sel="true"] {{ border: 2px solid {ACCENT};
    background: rgba(54, 201, 212, 0.10); }}
QFrame#tilebox {{ background: {PANEL_DK}; border: 1px solid #000; border-radius: 6px; }}
QLabel#tilefn {{ color: {GREEN}; font-size: 10px; background: transparent; }}
QLabel#tilenum {{ color: {AMBER}; font-weight: 800; font-size: 14px; background: transparent; }}

/* ---- Pages: group navigator ---- */
QFrame#groupbox {{ background: #3ba7e0; border: 2px solid #2a7bb0; border-radius: 7px; }}
QFrame#groupbox[sel="true"] {{ border: 2px solid white; }}
QLabel#grpnum {{ color: #f2e23a; font-weight: 800; font-size: 13px; background: transparent; }}
"""


def _arrow_pixmap(up: bool):
    """A small triangle arrow PNG painted at runtime (needs a live QGuiApplication)."""
    from PySide6.QtGui import QPixmap, QPainter, QColor, QPolygonF
    from PySide6.QtCore import QPointF, Qt
    pm = QPixmap(18, 18)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(TEXT))
    if up:
        tri = QPolygonF([QPointF(5, 12), QPointF(13, 12), QPointF(9, 5)])
    else:
        tri = QPolygonF([QPointF(5, 6), QPointF(13, 6), QPointF(9, 13)])
    p.drawPolygon(tri)
    p.end()
    return pm


def build_stylesheet() -> str:
    """Return the full stylesheet with spin-box arrow images generated at runtime.

    Call after a QApplication exists. Falls back to the plain QSS (no arrows) if image
    generation isn't possible. Arrow PNGs are written once to a temp dir and reused."""
    try:
        import os
        import tempfile
        cache = os.path.join(tempfile.gettempdir(), "lfeditor_arrows")
        os.makedirs(cache, exist_ok=True)
        up_path = os.path.join(cache, "up.png")
        down_path = os.path.join(cache, "down.png")
        if not os.path.exists(up_path):
            _arrow_pixmap(True).save(up_path)
            _arrow_pixmap(False).save(down_path)
        up_url = up_path.replace("\\", "/")
        down_url = down_path.replace("\\", "/")
        extra = (
            f'QSpinBox::up-arrow {{ image: url("{up_url}"); width: 9px; height: 9px; }}'
            f'QSpinBox::down-arrow {{ image: url("{down_url}"); width: 9px; height: 9px; }}'
        )
        return QSS + extra
    except Exception:  # noqa: BLE001
        return QSS
