"""
Toolbar icons, drawn with QPainter so they ship inside the app (no binary assets) and theme
cleanly. They mirror the original LF+ Editor's metaphors: a floppy for open/save, a red life-ring
for backup, a sparkling page for clear, twin pages for copy, a clipboard for paste.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QPointF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPolygonF

from .theme import ACCENT, GREEN, RED, TEXT, TEXT_DIM

_SIZE = 40
_PAPER = "#d7dde3"
_PAPER_DK = "#aeb6bd"


def _canvas() -> tuple[QPixmap, QPainter]:
    pm = QPixmap(_SIZE, _SIZE)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    return pm, p


def _floppy(accent: str, with_check: bool) -> QPixmap:
    pm, p = _canvas()
    body = QColor(accent)
    p.setPen(QPen(QColor(TEXT), 1.4))
    p.setBrush(QBrush(body))
    # body with a clipped top-right corner
    poly = QPolygonF([QPointF(8, 8), QPointF(28, 8), QPointF(32, 12),
                      QPointF(32, 32), QPointF(8, 32)])
    p.drawPolygon(poly)
    # shutter (top metal slider)
    p.setBrush(QColor(_PAPER_DK))
    p.setPen(Qt.NoPen)
    p.drawRect(QRectF(13, 8, 12, 7))
    p.setBrush(QColor(body.darker(140)))
    p.drawRect(QRectF(20, 9, 3, 5))
    # label area
    p.setBrush(QColor(_PAPER))
    p.drawRect(QRectF(12, 19, 16, 11))
    if with_check:
        p.setPen(QPen(QColor(GREEN), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(14, 25), QPointF(18, 29), QPointF(26, 21)]))
    else:
        p.setPen(QPen(QColor(TEXT_DIM), 1))
        for y in (22, 25, 28):
            p.drawLine(QPointF(14, y), QPointF(26, y))
    p.end()
    return pm


def _life_ring() -> QPixmap:
    pm, p = _canvas()
    red = QColor(RED)
    p.setPen(Qt.NoPen)
    p.setBrush(red)
    p.drawEllipse(QRectF(6, 6, 28, 28))
    # white segments between the spokes
    p.setBrush(QColor("#f0f0f0"))
    for ang in (45, 135, 225, 315):
        import math
        cx, cy, r = 20, 20, 14
        a = math.radians(ang)
        p.drawEllipse(QPointF(cx + r * 0.62 * math.cos(a), cy - r * 0.62 * math.sin(a)), 4.2, 4.2)
    # inner hole
    p.setBrush(QColor("#1b1f23"))
    p.drawEllipse(QRectF(13, 13, 14, 14))
    p.setBrush(QColor(_PAPER))
    p.drawEllipse(QRectF(15, 15, 10, 10))
    p.end()
    return pm


def _page(x: float, y: float, p: QPainter, fill: str = _PAPER):
    """A document with a folded top-right corner, top-left at (x, y)."""
    w, h, fold = 17, 21, 6
    p.setPen(QPen(QColor("#5b6166"), 1.2))
    p.setBrush(QColor(fill))
    body = QPolygonF([QPointF(x, y), QPointF(x + w - fold, y), QPointF(x + w, y + fold),
                      QPointF(x + w, y + h), QPointF(x, y + h)])
    p.drawPolygon(body)
    p.setBrush(QColor(_PAPER_DK))
    p.drawPolygon(QPolygonF([QPointF(x + w - fold, y), QPointF(x + w, y + fold),
                             QPointF(x + w - fold, y + fold)]))


def _clear_page() -> QPixmap:
    pm, p = _canvas()
    _page(11, 9, p)
    # ruled lines
    p.setPen(QPen(QColor(TEXT_DIM), 1))
    for yy in (17, 21, 25):
        p.drawLine(QPointF(14, yy), QPointF(24, yy))
    # sparkle / "new" star
    p.setPen(QPen(QColor(ACCENT), 2.2, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(28, 9), QPointF(28, 17))
    p.drawLine(QPointF(24, 13), QPointF(32, 13))
    p.end()
    return pm


def _copy_pages() -> QPixmap:
    pm, p = _canvas()
    _page(8, 12, p, _PAPER_DK)   # back page
    _page(14, 7, p, _PAPER)      # front page
    p.setPen(QPen(QColor(TEXT_DIM), 1))
    for yy in (15, 19, 23):
        p.drawLine(QPointF(17, yy), QPointF(27, yy))
    p.end()
    return pm


def _paste() -> QPixmap:
    pm, p = _canvas()
    # clipboard board
    p.setPen(QPen(QColor("#5b6166"), 1.3))
    p.setBrush(QColor(ACCENT).darker(160))
    p.drawRoundedRect(QRectF(8, 9, 24, 26), 3, 3)
    # clip at top
    p.setBrush(QColor(TEXT_DIM))
    p.drawRoundedRect(QRectF(15, 6, 10, 6), 2, 2)
    # pasted page
    p.setPen(QPen(QColor("#5b6166"), 1))
    p.setBrush(QColor(_PAPER))
    p.drawRect(QRectF(12, 15, 16, 17))
    p.setPen(QPen(QColor(TEXT_DIM), 1))
    for yy in (20, 24, 28):
        p.drawLine(QPointF(15, yy), QPointF(25, yy))
    p.end()
    return pm


def _find() -> QPixmap:
    pm, p = _canvas()
    p.setPen(QPen(QColor(ACCENT), 3.0))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(10, 9, 16, 16))           # lens
    p.setPen(QPen(QColor(ACCENT), 3.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(24, 23), QPointF(32, 31))   # handle
    p.end()
    return pm


_BUILDERS = {
    "open": lambda: _floppy(ACCENT, with_check=False),
    "save": lambda: _floppy(GREEN, with_check=True),
    "backup": _life_ring,
    "clear": _clear_page,
    "copy": _copy_pages,
    "paste": _paste,
    "find": _find,
}


def icon(name: str) -> QIcon:
    """Return the themed toolbar QIcon for one of: open save backup clear copy paste."""
    return QIcon(_BUILDERS[name]())
