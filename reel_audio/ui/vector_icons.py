from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _pt(rect: QRectF, x: float, y: float) -> QPointF:
    return QPointF(rect.left() + rect.width() * x / 24.0, rect.top() + rect.height() * y / 24.0)


def _line(p: QPainter, r: QRectF, x1: float, y1: float, x2: float, y2: float) -> None:
    p.drawLine(_pt(r, x1, y1), _pt(r, x2, y2))


def _ellipse(p: QPainter, r: QRectF, x: float, y: float, w: float, h: float) -> None:
    p.drawEllipse(QRectF(_pt(r, x, y), _pt(r, x + w, y + h)))


def _rect(p: QPainter, r: QRectF, x: float, y: float, w: float, h: float, radius: float = 0.0) -> None:
    rr = QRectF(_pt(r, x, y), _pt(r, x + w, y + h))
    if radius:
        scale = min(r.width(), r.height()) / 24.0
        p.drawRoundedRect(rr, radius * scale, radius * scale)
    else:
        p.drawRect(rr)


def draw_vector_icon(p: QPainter, name: str, rect: QRectF, color: QColor | str = "#d8dee6", width: float = 1.8) -> None:
    color = QColor(color)
    scale = min(rect.width(), rect.height()) / 24.0
    pen = QPen(color, max(1.0, width * scale))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    n = name.lower().replace("_", "-")
    if n in {"waveform", "audio-waveform"}:
        for x, y1, y2 in [(3,9,15),(6,6,18),(9,3,21),(12,7,17),(15,4,20),(18,8,16),(21,10,14)]:
            _line(p, rect, x, y1, x, y2)
    elif n == "settings":
        _ellipse(p, rect, 9, 9, 6, 6)
        for a,b,c,d in [(12,2,12,5),(12,19,12,22),(2,12,5,12),(19,12,22,12),(4.9,4.9,7,7),(17,17,19.1,19.1),(17,7,19.1,4.9),(4.9,19.1,7,17)]:
            _line(p, rect, a,b,c,d)
        _ellipse(p, rect, 5.5,5.5,13,13)
    elif n == "plus":
        _line(p, rect, 12,5,12,19); _line(p, rect,5,12,19,12)
    elif n in {"x", "close", "remove"}:
        _line(p, rect, 6.5,6.5,17.5,17.5); _line(p, rect,17.5,6.5,6.5,17.5)
    elif n in {"folder", "folder-open"}:
        path = QPainterPath(_pt(rect, 3, 7)); path.lineTo(_pt(rect, 9,7)); path.lineTo(_pt(rect,11,9)); path.lineTo(_pt(rect,21,9)); path.lineTo(_pt(rect,20,19)); path.lineTo(_pt(rect,4,19)); path.closeSubpath(); p.drawPath(path)
    elif n == "history":
        path = QPainterPath(_pt(rect, 4, 9)); path.cubicTo(_pt(rect,5,5), _pt(rect,8,3), _pt(rect,12,3)); path.cubicTo(_pt(rect,17,3), _pt(rect,21,7), _pt(rect,21,12)); path.cubicTo(_pt(rect,21,17), _pt(rect,17,21), _pt(rect,12,21)); path.cubicTo(_pt(rect,8,21), _pt(rect,5,19), _pt(rect,3.5,16)); p.drawPath(path)
        _line(p, rect,4,4,4,9); _line(p, rect,4,9,9,9); _line(p, rect,12,7,12,12); _line(p, rect,12,12,15.5,14)
    elif n in {"chevron-down", "down"}:
        _line(p, rect,7,9.5,12,14.5); _line(p, rect,12,14.5,17,9.5)
    elif n in {"sparkles", "sparkle"}:
        path = QPainterPath(_pt(rect, 12,2)); path.lineTo(_pt(rect,13.6,7.4)); path.lineTo(_pt(rect,19,9)); path.lineTo(_pt(rect,13.6,10.6)); path.lineTo(_pt(rect,12,16)); path.lineTo(_pt(rect,10.4,10.6)); path.lineTo(_pt(rect,5,9)); path.lineTo(_pt(rect,10.4,7.4)); path.closeSubpath(); p.drawPath(path)
        _line(p, rect,19,3,19,7); _line(p, rect,17,5,21,5); _line(p, rect,5,16,5,21); _line(p, rect,2.5,18.5,7.5,18.5)
    elif n in {"mic", "microphone"}:
        _rect(p, rect, 9,3,6,11,3); path=QPainterPath(_pt(rect,6,11)); path.cubicTo(_pt(rect,6,16),_pt(rect,8.5,18),_pt(rect,12,18)); path.cubicTo(_pt(rect,15.5,18),_pt(rect,18,16),_pt(rect,18,11)); p.drawPath(path); _line(p,rect,12,18,12,22); _line(p,rect,8,22,16,22)
    elif n == "car":
        path=QPainterPath(_pt(rect,4,15)); path.lineTo(_pt(rect,6,9)); path.lineTo(_pt(rect,8,6)); path.lineTo(_pt(rect,16,6)); path.lineTo(_pt(rect,18,9)); path.lineTo(_pt(rect,20,15)); path.closeSubpath(); p.drawPath(path); _line(p,rect,5,11,19,11); _ellipse(p,rect,5,15,3,3); _ellipse(p,rect,16,15,3,3)
    elif n == "music":
        _line(p,rect,9,18,9,6); _line(p,rect,9,6,19,4); _line(p,rect,19,4,19,16); _ellipse(p,rect,4,16,5,4); _ellipse(p,rect,14,14,5,4)
    elif n in {"users", "podcast"}:
        _ellipse(p,rect,8,4,8,8); path=QPainterPath(_pt(rect,4,21)); path.cubicTo(_pt(rect,4,16),_pt(rect,7,14),_pt(rect,12,14)); path.cubicTo(_pt(rect,17,14),_pt(rect,20,16),_pt(rect,20,21)); p.drawPath(path)
        _ellipse(p,rect,17,7,4,4); path=QPainterPath(_pt(rect,18,13)); path.cubicTo(_pt(rect,21,13),_pt(rect,23,15),_pt(rect,23,18)); p.drawPath(path)
    elif n == "play":
        path=QPainterPath(_pt(rect,8,5)); path.lineTo(_pt(rect,19,12)); path.lineTo(_pt(rect,8,19)); path.closeSubpath(); p.drawPath(path)
    elif n == "pause":
        _line(p,rect,9,6,9,18); _line(p,rect,15,6,15,18)
    elif n == "skip-back":
        _line(p,rect,7,6,7,18); path=QPainterPath(_pt(rect,18,6)); path.lineTo(_pt(rect,9,12)); path.lineTo(_pt(rect,18,18)); path.closeSubpath(); p.drawPath(path)
    elif n == "skip-forward":
        _line(p,rect,17,6,17,18); path=QPainterPath(_pt(rect,6,6)); path.lineTo(_pt(rect,15,12)); path.lineTo(_pt(rect,6,18)); path.closeSubpath(); p.drawPath(path)
    elif n == "volume":
        path=QPainterPath(_pt(rect,4,10)); path.lineTo(_pt(rect,8,10)); path.lineTo(_pt(rect,13,6)); path.lineTo(_pt(rect,13,18)); path.lineTo(_pt(rect,8,14)); path.lineTo(_pt(rect,4,14)); path.closeSubpath(); p.drawPath(path); path=QPainterPath(_pt(rect,16,9)); path.cubicTo(_pt(rect,18,11),_pt(rect,18,13),_pt(rect,16,15)); p.drawPath(path); path=QPainterPath(_pt(rect,18.5,6.5)); path.cubicTo(_pt(rect,22,10),_pt(rect,22,14),_pt(rect,18.5,17.5)); p.drawPath(path)
    elif n == "waves":
        for y in (7,12,17):
            path=QPainterPath(_pt(rect,3,y)); path.cubicTo(_pt(rect,6,y-3),_pt(rect,9,y-3),_pt(rect,12,y)); path.cubicTo(_pt(rect,15,y+3),_pt(rect,18,y+3),_pt(rect,21,y)); p.drawPath(path)
    elif n in {"user", "voice"}:
        _ellipse(p,rect,9,4,6,6); path=QPainterPath(_pt(rect,5,20)); path.cubicTo(_pt(rect,6,15),_pt(rect,8.5,13),_pt(rect,12,13)); path.cubicTo(_pt(rect,15.5,13),_pt(rect,18,15),_pt(rect,19,20)); p.drawPath(path)
    elif n in {"compression", "bars"}:
        _line(p,rect,5,19,5,12); _line(p,rect,10,19,10,7); _line(p,rect,15,19,15,4); _line(p,rect,20,19,20,10)
    elif n == "scissors":
        _ellipse(p,rect,3,4,5,5); _ellipse(p,rect,3,15,5,5); _line(p,rect,7.5,8,20,18); _line(p,rect,7.5,16,20,6)
    elif n in {"normalize", "sliders"}:
        _line(p,rect,5,5,5,19); _line(p,rect,12,5,12,19); _line(p,rect,19,5,19,19); _line(p,rect,2.5,9,7.5,9); _line(p,rect,9.5,15,14.5,15); _line(p,rect,16.5,8,21.5,8)
    elif n in {"upload", "export"}:
        _line(p,rect,12,16,12,4); _line(p,rect,8,8,12,4); _line(p,rect,16,8,12,4); path=QPainterPath(_pt(rect,5,14)); path.lineTo(_pt(rect,5,20)); path.lineTo(_pt(rect,19,20)); path.lineTo(_pt(rect,19,14)); p.drawPath(path)
    elif n in {"reset", "rotate"}:
        path=QPainterPath(_pt(rect,5,8)); path.cubicTo(_pt(rect,8,4),_pt(rect,14,3),_pt(rect,18,7)); path.cubicTo(_pt(rect,22,11),_pt(rect,21,17),_pt(rect,17,20)); path.cubicTo(_pt(rect,13,23),_pt(rect,7,21),_pt(rect,5,17)); p.drawPath(path); _line(p,rect,5,8,5,3); _line(p,rect,5,8,10,8)
    elif n in {"expand", "maximize"}:
        _line(p,rect,8,3,3,3); _line(p,rect,3,3,3,8); _line(p,rect,16,3,21,3); _line(p,rect,21,3,21,8); _line(p,rect,3,16,3,21); _line(p,rect,3,21,8,21); _line(p,rect,21,16,21,21); _line(p,rect,16,21,21,21)
    elif n == "spectrum":
        for x,h in [(4,6),(8,12),(12,17),(16,10),(20,14)]: _line(p,rect,x,20,x,20-h)
    elif n == "info":
        _ellipse(p,rect,3,3,18,18); _line(p,rect,12,10,12,17); _line(p,rect,12,7,12,7.2)
    else:
        _ellipse(p,rect,5,5,14,14)


def make_icon(name: str, color: str = "#d8dee6", size: int = 64, stroke: float = 1.8) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    margin = size * 0.16
    draw_vector_icon(painter, name, QRectF(margin, margin, size - 2 * margin, size - 2 * margin), color, stroke)
    painter.end()
    return QIcon(pm)


def make_state_icon(name: str, off_color: str = "#c8d1d9", on_color: str = "#273038", size: int = 64, stroke: float = 1.8) -> QIcon:
    icon = QIcon()
    off = make_icon(name, off_color, size, stroke).pixmap(size, size)
    on = make_icon(name, on_color, size, stroke).pixmap(size, size)
    icon.addPixmap(off, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(on, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(off, QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(on, QIcon.Mode.Active, QIcon.State.On)
    return icon
