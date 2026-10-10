"""Generate the application icon.

Writes a multi-resolution ``assets/icon.ico`` (PNG-compressed entries, which
Windows Vista and later understand) plus a 256 px ``assets/icon.png``.
"""

from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide2.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt  # noqa: E402
from PySide2.QtGui import (  # noqa: E402
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide2.QtWidgets import QApplication  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

DOTS = (
    ((0.30, 0.30), "#3ea6ff"),
    ((0.68, 0.34), "#3ddc97"),
    ((0.42, 0.64), "#ffb020"),
    ((0.74, 0.74), "#ff5c6c"),
)
EDGES = ((0, 1), (0, 2), (1, 3), (2, 3))


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)

    gradient = QLinearGradient(0, 0, 0, size)
    gradient.setColorAt(0.0, QColor("#1d2735"))
    gradient.setColorAt(1.0, QColor("#0d1219"))
    painter.setBrush(QBrush(gradient))
    painter.setPen(QPen(QColor("#2b3648"), max(1.0, size * 0.02)))
    radius = size * 0.22
    painter.drawRoundedRect(
        QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92), radius, radius
    )

    pen = QPen(QColor("#3ea6ff"))
    pen.setWidthF(max(1.0, size * 0.035))
    pen.setCapStyle(Qt.RoundCap)
    for start, end in EDGES:
        painter.setPen(pen)
        painter.drawLine(
            QPointF(DOTS[start][0][0] * size, DOTS[start][0][1] * size),
            QPointF(DOTS[end][0][0] * size, DOTS[end][0][1] * size),
        )

    for (fx, fy), color in DOTS:
        painter.setBrush(QBrush(QColor(color)))
        painter.setPen(QPen(QColor("#0d1219"), max(1.0, size * 0.012)))
        painter.drawEllipse(QPointF(fx * size, fy * size), size * 0.075, size * 0.075)

    painter.setBrush(Qt.NoBrush)
    for index, alpha in enumerate((210, 150, 90)):
        arc_pen = QPen(QColor(62, 166, 255, alpha))
        arc_pen.setWidthF(max(1.0, size * 0.026))
        painter.setPen(arc_pen)
        inset = size * (0.09 + index * 0.055)
        painter.drawArc(
            QRectF(inset, inset, size - 2 * inset, size - 2 * inset), -30 * 16, 60 * 16
        )

    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer(QByteArray())
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def build_ico(images) -> bytes:
    """Assemble a multi-resolution ICO file from PNG-encoded images."""
    entries = []
    payload = b""
    offset = 6 + 16 * len(images)
    for size, data in images:
        dimension = 0 if size >= 256 else size
        entries.append(struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset,
        ))
        offset += len(data)
        payload += data
    header = struct.pack("<HHH", 0, 1, len(images))
    return header + b"".join(entries) + payload


def main() -> int:
    QApplication(sys.argv[:1])
    os.makedirs(ASSETS, exist_ok=True)

    sizes = (16, 24, 32, 48, 64, 128, 256)
    rendered = [(size, render(size)) for size in sizes]

    png_path = os.path.join(ASSETS, "icon.png")
    rendered[-1][1].save(png_path, "PNG")
    print("wrote %s" % png_path)

    ico_path = os.path.join(ASSETS, "icon.ico")
    with open(ico_path, "wb") as handle:
        handle.write(build_ico([(size, png_bytes(image)) for size, image in rendered]))
    print("wrote %s (%d bytes)" % (ico_path, os.path.getsize(ico_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
