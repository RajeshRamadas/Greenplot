import io
from xml.sax.saxutils import escape

import segno


def qr_svg(data: str, caption: str | None = None, scale: int = 8) -> bytes:
    """QR code as SVG, with an optional printed caption under it for asset/checkpoint labels."""
    qr = segno.make(data, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, border=2, xmldecl=False, svgns=True)
    svg = buf.getvalue().decode()
    if not caption:
        return svg.encode()
    w, h = qr.symbol_size(scale=scale, border=2)
    inner = svg[svg.index(">") + 1 : svg.rindex("</svg>")]
    out = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h + 34}" viewBox="0 0 {w} {h + 34}">'
        f'<rect width="100%" height="100%" fill="#fff"/>{inner}'
        f'<text x="{w / 2}" y="{h + 20}" font-family="Arial, sans-serif" font-size="14" text-anchor="middle">{escape(caption)}</text>'
        f'<text x="{w / 2}" y="{h + 32}" font-family="Arial, sans-serif" font-size="9" fill="#555" text-anchor="middle">{escape(data)}</text>'
        "</svg>"
    )
    return out.encode()
