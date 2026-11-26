"""Docling enrichment: formulas become $LaTeX$ lines (fake items, no docling)."""

import importlib.util

import pytest
from conftest import SAMPLES

from app.pipeline import enrich as E
from app.pipeline.enrich import Enriched, enrich_pages, valid_latex
from app.pipeline.extract import Box, Line, Page
from app.pipeline.models import BBox
from app.pipeline.structure import Grouper


def line(text, top, x0=60, x1=400, size=10.0):
    return Line(page=0, text=text, x0=x0, top=top, x1=x1, bottom=top + size, font="CMR10", size=size, bold=False, color=(0, 0, 0), raw_len=len(text))


def page(lines, graphics=()):
    return Page(index=0, width=600, height=800, lines=list(lines), graphics=list(graphics))


def test_formula_replaces_lines():
    p = page([line("Compute", 100), line("x a", 120), line("b y", 132), line("done", 160)])
    enrich_pages([p], [Enriched(0, (55, 115, 405, 148), "formula", r"\frac{x}{y}")])
    assert [ln.text for ln in p.lines] == ["Compute", r"$\frac{x}{y}$", "done"]
    f = p.lines[1]
    assert f.converted and f.raw_len == 6 and f.font == "CMR10" and (f.top, f.bottom) == (115, 148)


def test_formula_over_fraction_bar_region_becomes_text():
    p = page([line("a) Show", 100), line("x", 120), line("y", 134)], [Box(60, 130, 100, 131, "line")])
    bbox = BBox(x0=50, y0=95, x1=550, y1=150)
    assert Grouper.visual(None, p, bbox)
    enrich_pages([p], [Enriched(0, (55, 118, 405, 148), "formula", r"\frac{x}{y}")])
    assert not Grouper.visual(None, p, bbox)


def test_math_font_lines_do_not_keep_the_region_visual():
    ext = line("(", 120)
    ext.fonts = frozenset({"LMMathExtension10-Regular"})
    p = page([line("a) Show", 100), ext, line("x", 134)], [Box(60, 130, 100, 131, "line")])
    enrich_pages([p], [Enriched(0, (55, 118, 405, 148), "formula", r"\frac{x}{y}")])
    assert not Grouper.visual(None, p, BBox(x0=50, y0=95, x1=550, y1=150))


def test_dropped_digit_rejects_formula():
    p = page([line("v1 = ( 1 -2 2 ) (cid:1)", 100)])
    enrich_pages([p], [Enriched(0, (55, 95, 405, 115), "formula", r"v_1 = \left(\begin{array}{cc} 1 \\ -2 \end{array}\right)")])
    assert not p.lines[0].converted
    p = page([line("E(0) = 0. (4.1)", 100)])  # equation number is allowed to vanish
    enrich_pages([p], [Enriched(0, (55, 95, 405, 115), "formula", "E(0) = 0.")])
    assert p.lines[0].converted


def test_inline_formula_in_wide_line_is_left():
    p = page([line("let x = a over b and more text", 100)])
    enrich_pages([p], [Enriched(0, (100, 100, 150, 110), "formula", "x")])
    assert p.lines[0].text.startswith("let x") and not p.lines[0].converted


@pytest.mark.parametrize(
    "s",
    [
        "\\frac{a}{b",
        "a$b",
        "",
        "x" * 2001,
        "\\left( x",
        "\\quad\\quad\\quad\\quad x",
        "a \\\\ \\\\ \\\\ \\\\ b",
        "a $ b $ c $ d",
        "a \\right) b \\left( c \\right)",
    ],
)
def test_invalid_latex_dropped(s):
    assert not valid_latex(s)
    p = page([line("x", 100)])
    enrich_pages([p], [Enriched(0, (55, 95, 405, 115), "formula", s)])
    assert p.lines[0].text == "x"


def test_valid_latex():
    assert valid_latex(r"\left( \frac{a}{b} \right) \quad x")
    assert valid_latex(r"a \$ b")


def test_enrich_failure_is_swallowed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(E, "find_items", boom)
    monkeypatch.setattr(E, "available", lambda: True)
    p = page([line("x", 100)])
    E.enrich("x.pdf", [p])
    assert p.lines[0].text == "x"


def test_without_mlx_nothing_runs(monkeypatch):
    monkeypatch.setattr(E, "available", lambda: False)
    monkeypatch.setattr(E, "find_items", lambda *a: pytest.fail("must not run"))
    E.enrich("x.pdf", [page([])])


@pytest.mark.skipif(importlib.util.find_spec("mlx_vlm") is None, reason="needs mlx_vlm (Apple Silicon)")
def test_numprog_integration():
    from app.pipeline.extract import extract

    pdf = SAMPLES / "numprog" / "numprog-2026-endterm.pdf"
    pages = extract(pdf)
    try:
        items = E.find_items(pdf)
    except Exception as e:  # models not cached / offline
        pytest.skip(f"docling unavailable: {type(e).__name__}")
    assert any(i.kind == "formula" for i in items)
    E.enrich_pages(pages, items)
    assert any(ln.converted and ln.text.startswith("$") for p in pages for ln in p.lines)
