import io

from PIL import Image

from evals.grading.scan_crop import clean_crop
from evals.grading.scan_points import parse_cover_total, read_cover_total, read_scores
from tests.pdf_util import L, make_pdf


def _png(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def _fill(img, x0, y0, x1, y1, color):
    for x in range(x0, x1):
        for y in range(y0, y1):
            img.putpixel((x, y), color)


def test_clean_crop_removes_red():
    img = Image.new("RGB", (200, 200), "white")
    _fill(img, 20, 20, 30, 30, (0, 0, 255))
    _fill(img, 60, 20, 70, 30, (255, 0, 0))
    out = _png(clean_crop(img, (0, 0, 200, 200), (200, 200), []))
    assert out.getpixel((25, 25)) == (0, 0, 255)
    assert out.getpixel((65, 25)) == (255, 255, 255)


def test_clean_crop_removes_red_fringe_and_neighbours():
    img = Image.new("RGB", (200, 200), "white")
    img.putpixel((20, 20), (240, 205, 210))  # pink anti-aliased fringe
    _fill(img, 60, 20, 70, 30, (255, 0, 0))
    img.putpixel((71, 25), (20, 20, 20))  # 2 px from the stroke
    img.putpixel((73, 25), (20, 20, 20))  # 4 px away
    out = _png(clean_crop(img, (0, 0, 200, 200), (200, 200), []))
    assert out.getpixel((20, 20)) == (255, 255, 255)
    assert out.getpixel((71, 25)) == (255, 255, 255)
    assert out.getpixel((73, 25)) == (20, 20, 20)


def test_clean_crop_keeps_non_red_ink_and_paper_noise():
    img = Image.new("RGB", (200, 200), "white")
    for x, c in ((20, (40, 60, 200)), (60, (20, 20, 20)), (100, (200, 195, 195))):
        img.putpixel((x, 20), c)
    out = _png(clean_crop(img, (0, 0, 200, 200), (200, 200), []))
    assert [out.getpixel((x, 20)) for x in (20, 60, 100)] == [(40, 60, 200), (20, 20, 20), (200, 195, 195)]


def test_clean_crop_removes_green_marks():
    img = Image.new("RGB", (200, 200), "white")
    img.putpixel((20, 20), (6, 98, 54))  # dark green pen
    img.putpixel((60, 20), (150, 210, 160))  # light green
    _fill(img, 100, 20, 110, 30, (6, 98, 54))
    img.putpixel((111, 25), (20, 20, 20))  # 2 px from the stroke
    out = _png(clean_crop(img, (0, 0, 200, 200), (200, 200), []))
    assert [out.getpixel(p) for p in ((20, 20), (60, 20), (111, 25))] == [(255, 255, 255)] * 3


def test_clean_crop_keeps_dark_inks_far_from_marks():
    img = Image.new("RGB", (200, 200), "white")
    colors = [(20, 20, 20), (40, 60, 200), (30, 35, 60), (200, 195, 195)]
    for i, c in enumerate(colors):
        img.putpixel((20 + 30 * i, 20), c)
    out = _png(clean_crop(img, (0, 0, 200, 200), (200, 200), []))
    assert [out.getpixel((20 + 30 * i, 20)) for i in range(4)] == colors


def test_clean_crop_whitens_boxes():
    img = Image.new("RGB", (100, 100), "white")
    _fill(img, 10, 10, 30, 30, (0, 0, 0))
    out = _png(clean_crop(img, (0, 0, 100, 100), (100, 100), [(5, 5, 35, 35)]))
    assert set(out.get_flattened_data()) == {(255, 255, 255)}


def test_clean_crop_scales_and_crops():
    img = Image.new("RGB", (400, 400), "white")
    out = _png(clean_crop(img, (100, 100, 200, 200), (200, 200), []))
    assert out.size == (200, 200)


def test_clean_crop_whiten_clipped_and_outside():
    img = Image.new("RGB", (100, 100), "black")
    out = _png(clean_crop(img, (50, 50, 100, 100), (100, 100), [(0, 0, 60, 60), (0, 0, 10, 10)]))
    assert out.getpixel((5, 5)) == (255, 255, 255)
    assert out.getpixel((20, 20)) == (0, 0, 0)


def test_clean_crop_whitens_near_white_ghosts_only():
    img = Image.new("RGB", (100, 100), "white")
    img.putpixel((10, 10), (242, 242, 242))  # grey ghost of a removed tick
    img.putpixel((20, 10), (236, 240, 238))  # tinted ghost, min channel >= 235
    img.putpixel((30, 10), (230, 230, 230))  # above the paper floor cut-off, kept
    img.putpixel((40, 10), (20, 20, 20))  # dark ink, kept
    out = _png(clean_crop(img, (0, 0, 100, 100), (100, 100), []))
    assert [out.getpixel((x, 10)) for x in (10, 20, 30, 40)] == [(255, 255, 255), (255, 255, 255), (230, 230, 230), (20, 20, 20)]


# --- scan_points ---


def _write(tmp_path, pages):
    p = tmp_path / "scan.pdf"
    p.write_bytes(make_pdf(pages))
    return p


def test_read_scores_in_top_order_ignores_watermark(tmp_path):
    p = _write(
        tmp_path,
        [
            ["cover"],
            [
                L("0,5", x=35, y=300),
                L("1,0", x=35, y=700),
                L("NurzurpersoenlichenEinsicht", x=20, y=500),
                L("2,5", x=162, y=400),  # overview table, outside the margin
            ],
        ],
    )
    s = read_scores(p)
    assert [(x.page, x.points) for x in s] == [(1, 1.0), (1, 0.5)]
    assert s[0].top < s[1].top and s[0].x0 < 70


def test_read_scores_watermark_letter_on_score_line(tmp_path):
    p = _write(tmp_path, [["cover"], [L("r", x=20, y=500), L("1,0", x=35, y=500)]])
    assert [x.points for x in read_scores(p)] == [1.0]


def test_read_scores_dot_decimal(tmp_path):
    p = _write(tmp_path, [["cover"], [L("12.0", x=30, y=500)]])
    assert [x.points for x in read_scores(p)] == [12.0]


def test_read_scores_skips_cover(tmp_path):
    p = _write(tmp_path, [[L("1,0", x=35, y=500)], ["page"]])
    assert read_scores(p) == []


def test_parse_cover_total():
    assert parse_cover_total("Σ (Modulprüfung) Note\n20.0 4.0") == 20.0
    assert parse_cover_total("Σ(Endterm) Note(Endterm) Σ(Bonus) Σ Note Notenintervall\n47.0 3.3 9.0 56.0 2.0 [") == 47.0
    assert parse_cover_total("Σ(Midterm)\n31.5\nHinweise:") == 31.5
    assert parse_cover_total("no total here\n20.0") is None
    assert parse_cover_total("Σ(Midterm)") is None


def test_read_cover_total_no_sigma(tmp_path):
    assert read_cover_total(_write(tmp_path, [["Total", "20.0"]])) is None


# --- import_scans ---
import base64

import pytest

from app.grading.models import GradeIn
from app.pipeline.extract import GradingBox, Page
from app.pipeline.models import BBox, ExamStructure, Region, Subtask, Task
from evals.grading import import_scans as imp
from evals.grading.scan_points import Score


def test_find_pairs_handles_gdb_gbd_and_sol_names(tmp_path):
    names = [
        "bio-endterm-2025-kim", "bio-endterm-2025-solution",
        "Endterm-2025-kim", "endterm-2025-sol", "mat-endterm-2025-sol",
        "phy-2025-endterm-kim", "phy-2025-endterm-solution",
        "phy-midterm-2025-kim", "phy-midterm-2025-sol",
        "net-sec-25-kim", "net-sec-25-endterm-sol",
        "gdb-endterm-2025-kim", "gbd-endterm-2025-solution",
        "lonely-kim",
    ]  # fmt: skip
    for n in names:
        (tmp_path / f"{n}.pdf").touch()
    got = {s.stem: (a, sol.stem if sol else None) for a, s, sol in imp.find_pairs(tmp_path)}
    assert got["bio-endterm-2025-kim"][1] == "bio-endterm-2025-solution"
    assert got["Endterm-2025-kim"][1] == "endterm-2025-sol"
    assert got["phy-2025-endterm-kim"][1] == "phy-2025-endterm-solution"
    assert got["phy-midterm-2025-kim"][1] == "phy-midterm-2025-sol"
    assert got["net-sec-25-kim"][1] == "net-sec-25-endterm-sol"
    assert got["gdb-endterm-2025-kim"][1] == "gbd-endterm-2025-solution"
    assert got["lonely-kim"][1] is None
    assert got["Endterm-2025-kim"][0] == "exam-02"  # case-insensitive sort: bio < Endterm


def _sub(id, y0, y1, page=0, points=2.0, mc_key=None):
    return Subtask(
        id=id,
        label=id,
        points=points,
        regions=[Region(page=page, bbox=BBox(x0=0, y0=y0, x1=200, y1=y1), image=f"{id}_0.png")],
        text=id,
        mc_key=mc_key,
    )


def _exam(*subs, page_count=1):
    return ExamStructure(
        source="x", page_count=page_count, page_sizes=[(200, 200)] * page_count, kind="digital", is_solution=True,
        tasks=[Task(id="A", number="1", subtasks=list(subs))],
    )  # fmt: skip


def _score(top, points, page=1):
    return Score(page=page, top=top, bottom=top + 10, x0=10, x1=30, points=points)


def test_match_skips_subtask_with_no_or_two_scores():
    exam = _exam(_sub("A1", 0, 50), _sub("A2", 60, 110), _sub("A3", 120, 170))
    scores = [_score(10, 1), _score(20, 1), _score(70, 2)]  # A1 twice, A2 once, A3 none
    assert imp.match(scores, exam) == {"A2": 2}


def test_mapping_ok_requires_sum_match_and_enough_pages():
    exam = _exam(_sub("A1", 0, 50), _sub("A2", 60, 110))
    scores = [_score(10, 1), _score(70, 2)]
    assert imp.mapping_ok(scores, exam, 3.0, 2)
    assert not imp.mapping_ok(scores, exam, 4.0, 2)
    assert not imp.mapping_ok(scores, exam, 3.0, 1)
    assert not imp.mapping_ok(scores, exam, None, 2)


def _setup_cases(tmp_path, monkeypatch):
    exam = _exam(_sub("A1", 0, 50), _sub("A2", 60, 110, mc_key=[0]), _sub("A3", 120, 170))
    blank, ink = tmp_path / "blank", tmp_path / "ink"
    blank.mkdir()
    ink.mkdir()
    for sid in ("A1", "A2", "A3"):
        for d in (blank, ink):
            Image.new("RGB", (20, 20), "white").save(d / f"{sid}_0.png")
    asked = []

    def fake(scan, index):
        asked.append(index)
        return Image.new("RGB", (400, 400), "white")

    monkeypatch.setattr(imp, "DPI", 144)
    monkeypatch.setattr(imp, "render_page", fake)
    pages = [Page(index=0, width=200, height=200, grading_boxes=[GradingBox(150, 0, 170, 20, 2)])]
    scores = [_score(10, 1), _score(70, 2), _score(130, 2)]
    pts = imp.match(scores, exam)
    return imp.build_cases("exam-01", tmp_path / "s.pdf", exam, pages, scores, pts, blank, ink), asked


def test_build_cases_excludes_mc_and_never_uses_cover_page(tmp_path, monkeypatch):
    cases, asked = _setup_cases(tmp_path, monkeypatch)
    assert [c["id"] for c in cases] == ["exam-01/A1", "exam-01/A3"]
    assert asked and 0 not in asked
    bad = _exam(_sub("A1", 0, 50, page=-1))
    with pytest.raises(ValueError):
        imp.build_cases("e", tmp_path / "s.pdf", bad, [], [], {"A1": 1}, tmp_path, tmp_path)


def test_cases_validate_as_gradein(tmp_path, monkeypatch):
    cases, _ = _setup_cases(tmp_path, monkeypatch)
    for c in cases:
        GradeIn.model_validate(c["request"])
        base64.b64decode(c["request"]["answer"]["images"][0])
    assert cases[0]["expected"] == 1.0


def _two_page_sub():
    regions = [Region(page=p, bbox=BBox(x0=0, y0=0, x1=200, y1=200), image=f"A1_{p}.png") for p in (0, 1)]
    return Subtask(id="A1", label="A1", points=2.0, regions=regions, text="A1")


def test_build_cases_multi_page_order(tmp_path, monkeypatch):
    exam = _exam(_two_page_sub(), page_count=2)
    for d in ("blank", "ink"):
        (tmp_path / d).mkdir()
        for p in (0, 1):
            Image.new("RGB", (20, 20), "white").save(tmp_path / d / f"A1_{p}.png")
    asked, colors = [], {1: (0, 0, 255), 2: (120, 0, 160)}

    def fake(scan, index):
        asked.append(index)
        return Image.new("RGB", (400, 400), colors[index])

    monkeypatch.setattr(imp, "DPI", 144)
    monkeypatch.setattr(imp, "render_page", fake)
    pages = [Page(index=i, width=200, height=200, grading_boxes=[]) for i in (0, 1)]
    cases = imp.build_cases("e", tmp_path / "s.pdf", exam, pages, [], {"A1": 1.0}, tmp_path / "blank", tmp_path / "ink")
    assert asked == [1, 2]  # scan pages 2 then 3 (1-based), never the cover
    imgs = cases[0]["request"]["answer"]["images"]
    assert [_png(base64.b64decode(i)).getpixel((5, 5)) for i in imgs] == [colors[1], colors[2]]


def test_build_cases_removes_teacher_marks(tmp_path, monkeypatch):
    exam = _exam(_sub("A1", 0, 200))
    for d in ("blank", "ink"):
        (tmp_path / d).mkdir()
        Image.new("RGB", (20, 20), "white").save(tmp_path / d / "A1_0.png")
    img = Image.new("RGB", (400, 400), "white")
    _fill(img, 100, 300, 110, 303, (255, 0, 0))  # red stroke
    _fill(img, 288, 10, 293, 15, (0, 0, 0))  # padded area beside grading box (box x0=300px)
    _fill(img, 20, 200, 25, 205, (0, 0, 0))  # inside Score box
    _fill(img, 200, 300, 210, 310, (0, 0, 255))  # student ink survives
    monkeypatch.setattr(imp, "DPI", 144)
    monkeypatch.setattr(imp, "render_page", lambda scan, index: img)
    pages = [Page(index=0, width=200, height=200, grading_boxes=[GradingBox(150, 0, 170, 20, 2)])]
    scores = [_score(100, 1)]
    cases = imp.build_cases("e", tmp_path / "s.pdf", exam, pages, scores, {"A1": 1.0}, tmp_path / "blank", tmp_path / "blank")
    out = _png(base64.b64decode(cases[0]["request"]["answer"]["images"][0]))
    white = (255, 255, 255)
    assert out.getpixel((105, 301)) == white
    assert out.getpixel((290, 12)) == white
    assert out.getpixel((22, 202)) == white
    assert out.getpixel((205, 305)) == (0, 0, 255)


def test_build_cases_skips_points_above_max_and_question_line_only(tmp_path, monkeypatch):
    exam = _exam(_sub("A1", 0, 50), _sub("A2", 60, 110), _sub("A3", 120, 150))
    for d in ("blank", "ink"):
        (tmp_path / d).mkdir()
        for sid in ("A1", "A2", "A3"):
            Image.new("RGB", (20, 20), "white").save(tmp_path / d / f"{sid}_0.png")
    monkeypatch.setattr(imp, "DPI", 144)
    monkeypatch.setattr(imp, "render_page", lambda scan, index: Image.new("RGB", (400, 400), "white"))
    pages = [Page(index=0, width=200, height=200, grading_boxes=[])]
    pts = {"A1": 2.0, "A2": 2.5, "A3": 2.0}  # A2 above max 2.0, A3 region only 30 pt tall
    cases = imp.build_cases("e", tmp_path / "s.pdf", exam, pages, [], pts, tmp_path / "blank", tmp_path / "ink")
    assert [c["id"] for c in cases] == ["e/A1"]


def test_main_one_line_errors(tmp_path):
    with pytest.raises(SystemExit) as e:
        imp.main([str(tmp_path / "nope")])
    assert isinstance(e.value.code, str) and "\n" not in e.value.code and "not found" in e.value.code
    with pytest.raises(SystemExit) as e:
        imp.main([str(tmp_path)])
    assert isinstance(e.value.code, str) and "\n" not in e.value.code and "no scans" in e.value.code


@pytest.mark.parametrize(("n_pages", "expected"), [(1, "excluded: too few pages"), (2, "excluded: sum mismatch")])
def test_import_one_exclusions(tmp_path, monkeypatch, n_pages, expected):
    exam = _exam(_sub("A1", 0, 50), _sub("A2", 60, 110))
    monkeypatch.setattr(imp, "extract", lambda sol: [])
    monkeypatch.setattr(imp, "group", lambda pages, name, pdf_path: exam)
    monkeypatch.setattr(imp, "read_scores", lambda scan: [_score(10, 1), _score(70, 2)])
    monkeypatch.setattr(imp, "read_cover_total", lambda scan: 4.0)  # parsed sum is 3
    monkeypatch.setattr(imp.pypdfium2, "PdfDocument", lambda p: [None] * n_pages)
    status, cases, mc, un = imp._import_one("e", tmp_path / "s.pdf", tmp_path / "sol.pdf", tmp_path)
    assert status.startswith(expected)
    assert (cases, mc, un) == ([], 0, 0)


# --- manual_cases ---
from evals.grading import manual_cases as man

MANUAL_MD = """# comment
A1 | 1.5 | first line
    second line
A2 | 2 | [mc]
A9 | 1 | not in structure
Z1 | 1 | text only
    @max 2
    @question Q?
    @solution S!
A3 | 3 | too many points
A4 | 1 | mc_key but not marked
"""


def _manual_setup(tmp_path, monkeypatch, cover, md=MANUAL_MD):
    exam = _exam(_sub("A1", 0, 50), _sub("A2", 60, 110, mc_key=[0]), _sub("A3", 120, 170, points=2.0), _sub("A4", 180, 230, mc_key=[1]))
    (tmp_path / "x-kim.pdf").touch()
    (tmp_path / "x-sol.pdf").touch()
    (tmp_path / "manual").mkdir()
    (tmp_path / "manual" / "exam-01.md").write_text(md)
    for d in ("blank", "ink"):
        (tmp_path / d).mkdir()
        Image.new("RGB", (20, 20), "white").save(tmp_path / d / "A1_0.png")
    monkeypatch.setattr(man, "extract", lambda sol: [])
    monkeypatch.setattr(man, "group", lambda pages, name, pdf_path: exam)
    monkeypatch.setattr(man, "render_variants", lambda *a, **k: {"blank": tmp_path / "blank", "ink": tmp_path / "ink"})
    monkeypatch.setattr(man, "read_cover_total", lambda scan: cover)


def test_load_manual_builds_valid_cases(tmp_path, monkeypatch):
    _manual_setup(tmp_path, monkeypatch, 9.5)
    cases = man.load_manual(tmp_path)
    assert [(c["id"], c["expected"]) for c in cases] == [
        ("manual/exam-01/A1", 1.5),
        ("manual/exam-01/Z1", 1.0),
    ]  # mc (incl. unmarked mc_key), unmatched, above max dropped
    for c in cases:
        GradeIn.model_validate(c["request"])
    r = cases[0]["request"]
    assert r["answer"] == {"text": "first line\nsecond line", "images": []} and len(r["question"]["images"]) == 1
    assert (
        cases[1]["request"]["points"] == 2.0 and cases[1]["request"]["solution"]["text"] == "S!" and cases[1]["request"]["question"]["text"] == "Q?"
    )


def test_manual_max_entry_ignores_structure(tmp_path, monkeypatch):
    md = "A2 | 1 | typed\n    @max 2\n    @question Q?\n    @solution S!\n"
    _manual_setup(tmp_path, monkeypatch, 1.0, md=md)  # A2 has mc_key, regions and its own text in the structure
    (c,) = man.load_manual(tmp_path)
    r = c["request"]
    assert (r["points"], r["question"], r["solution"]) == (2.0, {"text": "Q?", "images": []}, {"text": "S!", "images": [], "rubric": []})


def test_load_manual_excludes_sum_mismatch_and_main_reports(tmp_path, monkeypatch, capsys):
    _manual_setup(tmp_path, monkeypatch, 10.0)
    assert man.load_manual(tmp_path) == []
    man.main([str(tmp_path)])
    out = capsys.readouterr().out
    assert "2 mc, 1 unmatched ['A9'], 1 dropped" in out
    assert "sum 9.5 vs cover 10.0, excluded" in out
    assert (tmp_path / "manual-cases.jsonl").read_text() == ""
    with pytest.raises(SystemExit) as e:
        man.main([str(tmp_path / "nope")])
    assert "not found" in e.value.code


@pytest.mark.parametrize("bad", ["A1 | 1", "A1 | x | ans", "    indented first"])
def test_manual_malformed_line_names_file_and_line(tmp_path, monkeypatch, bad):
    _manual_setup(tmp_path, monkeypatch, 1.0, md=f"# c\n{bad}\n")
    with pytest.raises(SystemExit) as e:
        man.main([str(tmp_path)])
    assert "exam-01.md:2:" in e.value.code
