from dataclasses import dataclass


@dataclass
class L:
    """One line of a test page. `y` is the baseline in points from the bottom (None: flows down from the middle of the page)."""

    text: str
    size: float = 14
    rgb: tuple[float, float, float] = (0, 0, 0)
    x: float = 72
    y: float | None = None


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[str | L]], outline: list[tuple[str, int]] = ()) -> bytes:
    """A tiny text-only PDF: one list of lines per page (plain strings flow in Helvetica 14pt, `L` places a line), A4.
    `outline` is a flat list of bookmarks (title, 1-based page)."""
    objs: list[bytes] = []
    n = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    root = 4 + 2 * n  # object number of the bookmarks root, after the font
    objs.append(f"<< /Type /Catalog /Pages 2 0 R{f' /Outlines {root} 0 R' if outline else ''} >>".encode())
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    font = 3 + 2 * n
    for i, lines in enumerate(pages):
        placed = [ln if isinstance(ln, L) else L(ln) for ln in lines]
        text = " ".join(
            f"BT /F1 {ln.size} Tf {ln.rgb[0]} {ln.rgb[1]} {ln.rgb[2]} rg {ln.x} {600 - 20 * j if ln.y is None else ln.y} Td ({_esc(ln.text)}) Tj ET"
            for j, ln in enumerate(placed)
        )
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {4 + 2 * i} 0 R /Resources << /Font << /F1 {font} 0 R >> >> >>".encode()
        )
        objs.append(f"<< /Length {len(text)} >>\nstream\n{text}\nendstream".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    if outline:
        objs.append(f"<< /Type /Outlines /First {root + 1} 0 R /Last {root + len(outline)} 0 R /Count {len(outline)} >>".encode())
        for j, (title, pg) in enumerate(outline):
            prev = f" /Prev {root + j} 0 R" if j else ""
            nxt = f" /Next {root + j + 2} 0 R" if j < len(outline) - 1 else ""
            objs.append(f"<< /Title ({_esc(title)}) /Parent {root} 0 R /Dest [{3 + 2 * (pg - 1)} 0 R /Fit]{prev}{nxt} >>".encode())
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
