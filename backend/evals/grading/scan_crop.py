"""Crop a scan region and remove the teacher's marks (red pen, whiten boxes)."""

import io

from PIL import Image, ImageChops, ImageFilter


def clean_crop(
    img: Image.Image,
    bbox: tuple[float, float, float, float],
    page_size: tuple[float, float],
    whiten: list[tuple[float, float, float, float]],
) -> bytes:
    sx, sy = img.width / page_size[0], img.height / page_size[1]
    left, top = round(bbox[0] * sx), round(bbox[1] * sy)
    crop = img.convert("RGB").crop((left, top, round(bbox[2] * sx), round(bbox[3] * sy)))
    w, h = crop.size
    r, g, bl = crop.split()
    # red = strong red channel and clearly above the others; dilate 2 px to catch anti-aliased fringes
    lead = ImageChops.subtract(r, ImageChops.lighter(g, bl)).point(lambda v: 255 if v > 20 else 0)
    red = ImageChops.multiply(r.point(lambda v: 255 if v > 100 else 0), lead)
    # green = green channel clearly above the others, any brightness (second grader's dark green has g~98)
    green = ImageChops.subtract(g, ImageChops.lighter(r, bl)).point(lambda v: 255 if v > 25 else 0)
    mask = ImageChops.lighter(red, green).filter(ImageFilter.MaxFilter(5))
    crop.paste((255, 255, 255), mask=mask)
    # paper floor: grey ghosts of removed ticks (240-249) sit just under paper (250+), so whiten anything near-white
    # shortcut: this also whitens pale printed shading (>=235), fine while the eval texts are black on white; upgrade to a per-page paper estimate if shaded tables matter
    cr, cg, cb = crop.split()
    floor = Image.eval(ImageChops.darker(ImageChops.darker(cr, cg), cb), lambda v: 255 if v >= 235 else 0)
    crop.paste((255, 255, 255), mask=floor)
    px = crop.load()
    for x0, y0, x1, y1 in whiten:
        bx0, by0 = max(round(x0 * sx) - left, 0), max(round(y0 * sy) - top, 0)
        bx1, by1 = min(round(x1 * sx) - left, w), min(round(y1 * sy) - top, h)
        for y in range(by0, by1):
            for x in range(bx0, bx1):
                px[x, y] = (255, 255, 255)
    buf = io.BytesIO()
    crop.save(buf, "PNG")
    return buf.getvalue()
