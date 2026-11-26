from functools import cache

import pytest
from conftest import SAMPLES

from app.pipeline.extract import extract
from app.pipeline.mc import reading_order
from app.pipeline.models import BBox
from app.pipeline.structure import group

EXAM = SAMPLES / "grnvs" / "grnvs_endterm_2019.pdf"
SOL = SAMPLES / "grnvs" / "grnvs_endterm_2019-solution.pdf"


def needs(path):
    return pytest.mark.skipif(not path.exists(), reason=f"{path} missing")


@cache
def subtasks(path):
    exam = group(extract(path), str(path), pdf_path=path)
    return {s.id: s for t in exam.tasks for s in t.subtasks}


def box(x, y, size=10):
    return BBox(x0=x, y0=y, x1=x + size, y1=y + size)


def test_reading_order_rows_then_columns():
    # Two columns, rows slightly misaligned (as in GRNVS 2019 A6e).
    boxes = [box(65, 273), box(306, 228), box(65, 252), box(306, 250), box(65, 229), box(306, 271)]
    assert [(b.x0, b.y0) for b in reading_order(boxes)] == [
        (65, 229),
        (306, 228),
        (65, 252),
        (306, 250),
        (65, 273),
        (306, 271),
    ]


def test_reading_order_single_column():
    boxes = [box(80, 300), box(80, 100), box(80, 200)]
    assert [b.y0 for b in reading_order(boxes)] == [100, 200, 300]


@needs(EXAM)
def test_options_grnvs_2019_a6e():
    s = subtasks(EXAM)["A6e"]
    assert len(s.mc_options) == 6
    assert all(o.region == 0 for o in s.mc_options)
    first = s.mc_options[0].bbox
    assert first.x0 == pytest.approx(0.027, abs=0.01)
    assert first.y0 == pytest.approx(0.282, abs=0.02)
    assert first.x1 - first.x0 == pytest.approx(0.021, abs=0.005)
    assert first.y1 - first.y0 == pytest.approx(0.123, abs=0.02)
    ys = [o.bbox.y0 for o in s.mc_options]
    assert ys[0] < ys[2] < ys[4] and s.mc_options[1].bbox.x0 > 0.5  # rows first, then x
    assert any("Signalpegel" in o.text for o in s.mc_options)
    assert all("handelt" not in o.text for o in s.mc_options[:1])  # text stops at the next box


@needs(EXAM)
def test_free_text_has_no_options():
    s = subtasks(EXAM)["A2b"]
    assert s.mc_options == []
    assert s.mc_key is None


@needs(EXAM)
def test_no_key_without_ink():
    assert subtasks(EXAM)["A6e"].mc_key is None


@needs(SOL)
def test_key_from_solution_ink():
    s = subtasks(SOL)["A6e"]
    assert len(s.mc_options) == 6
    assert s.mc_key == [0, 2, 3]  # hand-verified: Signalpegel, Leitungscode, "01 erzeugt immer eine Pegeländerung"


GDB_SOL = SAMPLES / "gdb" / "gdb_24_endterm_lsg.pdf"


@needs(GDB_SOL)
def test_solution_ink_squares_are_not_checkboxes():
    # The solution lists answers like "1, ∀, z, ■" in blue; those squares are not answer options.
    s = subtasks(GDB_SOL)["A8b"]
    assert s.mc_options == []
    assert s.mc_key is None


@needs(SOL)
def test_no_key_without_pdf_path():
    exam = group(extract(SOL), SOL.name)  # display name only: the file is not read
    s = next(s for t in exam.tasks for s in t.subtasks if s.id == "A6e")
    assert len(s.mc_options) == 6
    assert s.mc_key is None


@needs(EXAM)
def test_answer_box_is_relative_to_its_region():
    s = subtasks(EXAM)
    [b] = s["A1b"].answer_boxes
    assert b.region == 0
    assert 0 <= b.bbox.x0 < 0.05 and b.bbox.x1 > 0.95  # full-width grid
    assert 0.05 < b.bbox.y0 < 0.15 and b.bbox.y1 > 0.95  # below the prompt, down to the crop's bottom
    assert all(not st.answer_boxes for st in s.values() if st.mc_options)


THEO = SAMPLES / "theo" / "theo-endterm-2026.pdf"


@needs(THEO)
def test_crops_stop_above_the_barcode_footer():
    s = subtasks(THEO)
    [r] = s["A1f"].regions  # ends at the page bottom: no footer, no barcode-only crop on the next page
    assert r.bbox.y1 < 760


@needs(THEO)
def test_answer_box_split_over_two_pages_gives_one_box_per_region():
    st = subtasks(THEO)["A3b"]
    assert [r.page for r in st.regions] == [5, 6]
    assert [b.region for b in st.answer_boxes] == [0, 1]


ANA = SAMPLES / "ana" / "ana_2024_Main.pdf"


@needs(ANA)
def test_task_overview_page_does_not_set_the_label_column():
    assert {"A1c", "A3b", "A6d"} <= set(subtasks(ANA))
