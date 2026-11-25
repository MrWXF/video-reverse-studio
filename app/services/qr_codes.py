"""Self-hosted QR SVG generation for share links."""

from __future__ import annotations

from html import escape

from reportlab.graphics.barcode.qr import QrCodeWidget


def qr_svg(value: str, *, border: int = 4, size: int = 220, level: str = "M") -> str:
    """Render a compact SVG QR code without calling external services."""

    if not value:
        raise ValueError("二维码内容不能为空")
    if len(value.encode("utf-8")) > 1000:
        raise ValueError("分享链接过长，无法生成二维码")
    border = max(1, min(int(border), 12))
    size = max(80, min(int(size), 720))
    level = level if level in {"L", "M", "Q", "H"} else "M"

    widget = QrCodeWidget(value=value, barLevel=level)
    widget.draw()
    modules = widget.qr.getModuleCount()
    extent = modules + border * 2
    paths: list[str] = []

    for row in range(modules):
        column = 0
        while column < modules:
            if not widget.qr.isDark(row, column):
                column += 1
                continue
            run_start = column
            while column < modules and widget.qr.isDark(row, column):
                column += 1
            run = column - run_start
            x = run_start + border
            y = row + border
            paths.append(f"M{x} {y}h{run}v1h-{run}z")

    label = escape(value, quote=True)
    path_data = "".join(paths)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{size}" height="{size}" viewBox="0 0 {extent} {extent}" '
        'role="img" aria-label="分享二维码">'
        f'<title>分享二维码：{label}</title>'
        f'<rect width="{extent}" height="{extent}" fill="#fff"/>'
        f'<path d="{path_data}" fill="#111"/>'
        "</svg>"
    )
