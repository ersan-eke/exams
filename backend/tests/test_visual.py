"""Region.visual: whether the crop says more than the extracted text."""

import pytest
from conftest import SAMPLES

from app.pipeline.extract import Box, Line, Page, extract
from app.pipeline.models import BBox, Region
from app.pipeline.structure import Grouper, group

BBOX = BBox(x0=50, y0=100, x1=550, y1=300)


def line(text, top=110, size=10.0, fonts=("Helvetica",)):
    return Line(
        page=0, text=text, x0=60, top=top, x1=400, bottom=top + size, font=fonts[0], size=size, bold=False, color=(0, 0, 0), fonts=frozenset(fonts)
    )


def visual(lines=(), graphics=(), checkboxes=()):
    page = Page(index=0, width=600, height=800, lines=list(lines), graphics=list(graphics), checkboxes=list(checkboxes))
    return Grouper.visual(None, page, BBOX)


def test_plain_question_with_answer_box_is_text():
    box = Box(55, 150, 545, 280, "rect")
    assert not visual([line("a) Explain an unnamed pipe."), line("in two sentences.", top=125)], [box])


def test_mc_checkboxes_and_glyphs_are_text():
    boxes = [Box(60, 130 + 15 * i, 70, 140 + 15 * i, "rect") for i in range(4)]
    lines = [line("b) Which statement is true?")] + [line(f"(cid:3) option {i}", top=130 + 15 * i) for i in range(4)]
    assert not visual(lines, boxes, boxes)


@pytest.mark.parametrize("graphic", [Box(100, 150, 300, 250, "curve"), Box(100, 150, 300, 250, "image")])
def test_figures_are_visual(graphic):
    assert visual([line("c) Sketch the function.")], [graphic])


def test_tables_drawn_from_lines_are_visual():
    cells = [Box(60 + 40 * i, 150, 100 + 40 * i, 170, "rect") for i in range(6)]
    assert visual([line("d) Fill in the table.")], cells)


def test_monospace_word_is_text():
    assert not visual([line("Server 10.0.0.1 antwortet", fonts=("Helvetica", "Inconsolata"))])


def test_math_symbol_font_is_text():
    assert not visual([line("f \u2192 g", fonts=("Helvetica", "LMMathSymbols10"))])


def test_code_is_text_with_indent():
    lines = [line("int f(int n) {"), line("if (n == 0) {", top=125), line("return 1;", top=140)]
    lines[1].x0, lines[2].x0 = 70, 80
    assert not visual(lines)
    g = Grouper.__new__(Grouper)
    g.is_solution = False
    g.pages = [Page(index=0, width=600, height=800, lines=lines)]
    assert g.text_in([Region(page=0, bbox=BBOX)]) == "int f(int n) {\n  if (n == 0) {\n    return 1;"


def test_fraction_bar_visual():
    bar = Box(100, 121, 140, 121.5, "line")
    assert visual([line("x + 1"), line("k^{3} - k", top=123)], [bar])


def test_big_operator_visual():
    assert visual([line("H = \u2211 k")])
    assert visual([line("P", fonts=("Helvetica", "CMEX10"))])


def test_matrix_brackets_visual():
    br = [Box(58, 105, 59, 140, "line"), Box(300, 105, 301, 140, "line")]
    assert visual([line("1 0", top=105), line("0 1", top=125)], br)


def test_garbled_glyphs_visual():
    assert visual([line("a) (cid:12) (cid:13)")])


def test_sketch_grid_visual():
    grid = [Box(60, 120 + 20 * i, 260, 120.5 + 20 * i, "line") for i in range(3)] + [
        Box(60 + 60 * i, 120, 60.5 + 60 * i, 260, "line") for i in range(4)
    ]
    assert visual([line("c) Sketch the graph.")], grid)


def test_converted_table_is_text():
    cells = [Box(60 + 40 * i, 150, 100 + 40 * i, 170, "rect") for i in range(6)]
    conv = line("| a | b |", top=145, size=30)
    conv.converted = True
    assert visual([line("d) Fill in.")], cells)
    assert not visual([line("d) Fill in."), conv], cells)


def test_unfolded_scripts_stay_visual():
    ln = line("lim n")
    ln.scripts_uncertain = True
    assert visual([ln])


def test_outside_the_region_does_not_count():
    assert not visual([line("text")], [Box(100, 500, 300, 600, "image")])


NUMPROG = SAMPLES / "numprog" / "numprog-2026-endterm.pdf"


@pytest.mark.skipif(not NUMPROG.exists(), reason="sample missing")
def test_numprog_flags():
    exam = group(extract(NUMPROG), str(NUMPROG), pdf_path=NUMPROG)
    flags = {(t.number, s.label): [r.visual for r in s.regions] for t in exam.tasks for s in t.subtasks}
    assert flags[("1", "a)*")] == [False]  # single choice, all text
    assert flags[("3", "a)*")] == [False]  # subscripts are folded into the text
    assert flags[("3", "b)*")] == [False]  # code is text
    assert flags[("3", "d)*")] == [True]  # plot to sketch in


ANA = [("ana_2011.pdf", "3"), ("ana_2008_Main.pdf", "4"), ("ana_2008_Solution.pdf", "4"), ("ana_2011_Main_Exercises+SeparateSolution.pdf", None)]


@pytest.mark.parametrize("name,task", ANA)
def test_two_dimensional_math_stays_visual(name, task):
    path = SAMPLES / "ana" / name
    if not path.exists():
        pytest.skip("sample missing")
    exam = group(extract(path), str(path), pdf_path=path)
    ts = [t for t in exam.tasks if task is None or t.number == task]
    assert any(r.visual for t in ts for s in t.subtasks for r in s.regions)


def test_fraction_bar_with_line_box_above_bar():
    # pdfplumber line boxes reach above the bar: denominator top (103.6) is above the bar (104.8)
    bar = Box(100, 104.77, 140, 105.2, "line")
    assert visual([line("a_{n}", top=93), line("n + 1", top=103.6)], [bar])


def test_control_and_private_use_glyphs_visual():
    for bad in ("a) x \x01 y", "a) x  y", "a) x � y"):
        assert visual([line(bad)])


def test_overline_visual():
    bar = Box(70, 108, 76, 108.4, "line")
    assert visual([line("z = x + y", top=110)], [bar])
    assert not visual([line("z = x + y", top=110)], [Box(70, 120, 76, 120.4, "line")])
