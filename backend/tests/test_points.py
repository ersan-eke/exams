from conftest import SAMPLES
from test_mc import EXAM, needs, subtasks

from app.pipeline.extract import extract
from app.pipeline.models import BBox, McOption, Subtask, Task
from app.pipeline.structure import group, split_mc_points

GBS = SAMPLES / "gbs" / "gbs_2023 Endterm Lösungsvorschlag.pdf"


def mc_sub(sid, points=None, text=""):
    opt = McOption(region=0, bbox=BBox(x0=0, y0=0, x1=0.1, y1=0.1), text="x")
    return Subtask(id=sid, label=f"{sid[-1]})*", points=points, regions=[], mc_options=[opt, opt], text=text)


def test_unprinted_mc_points_split_evenly():
    task = Task(id="A6", number="6", points=3, subtasks=[mc_sub("A6a"), mc_sub("A6b"), mc_sub("A6c")])
    assert split_mc_points(task)
    assert [s.points for s in task.subtasks] == [1, 1, 1]


def test_split_needs_half_point_steps():
    task = Task(id="A6", number="6", points=2, subtasks=[mc_sub("A6a"), mc_sub("A6b"), mc_sub("A6c")])
    assert not split_mc_points(task)
    assert all(s.points is None for s in task.subtasks)


def test_inline_points_note_then_remainder_split():
    task = Task(
        id="A7",
        number="7",
        points=4,
        subtasks=[mc_sub("A7a", text="a)* Welche?"), mc_sub("A7b", text="b)* 2 Punkte: Welche Ausgaben?"), mc_sub("A7c", text="c)* Welche?")],
    )
    assert split_mc_points(task)
    assert [s.points for s in task.subtasks] == [1, 2, 1]


def test_remainder_split_keeps_printed_points():
    task = Task(id="A6", number="6", points=3, subtasks=[mc_sub("A6a", 2), mc_sub("A6b")])
    assert split_mc_points(task)
    assert [s.points for s in task.subtasks] == [2, 1]


def test_split_leaves_mixed_or_complete_tasks_alone():
    printed = Task(id="A6", number="6", points=3, subtasks=[mc_sub("A6a", 2), mc_sub("A6b", 1)])
    free = Task(id="A6", number="6", points=2, subtasks=[mc_sub("A6a"), Subtask(id="A6b", label="b)", regions=[])])
    unknown = Task(id="A6", number="6", points=None, subtasks=[mc_sub("A6a"), mc_sub("A6b")])
    for t in (printed, free, unknown):
        assert not split_mc_points(t)
    assert free.subtasks[0].points is None


@needs(EXAM)
def test_grnvs_2019_mc_subtasks_get_one_point_each():
    subs = subtasks(EXAM)
    assert [subs[f"A6{c}"].points for c in "abcdefghijklmno"] == [1.0] * 15


@needs(GBS)
def test_gbs_2023_mc_points_from_note_and_header():
    exam = group(extract(GBS), str(GBS), pdf_path=GBS)
    pts = {s.id: s.points for s in exam.tasks[6].subtasks}
    assert pts["A7e"] == 2 and sum(pts.values()) == 18
    assert all(p == 1 for k, p in pts.items() if k != "A7e")


def test_inline_note_keeps_multi_digit_points():
    task = Task(
        id="A7",
        number="7",
        points=12,
        subtasks=[mc_sub("A7a", text="a)10 Punkte: Welche?"), mc_sub("A7b", text="b)* Welche?"), mc_sub("A7c", text="c)* Welche?")],
    )
    assert split_mc_points(task)
    assert [s.points for s in task.subtasks] == [10, 1, 1]


def test_inline_note_needs_a_label():
    task = Task(id="A7", number="7", points=12, subtasks=[mc_sub("A7a", text="12 Punkte: x"), mc_sub("A7b")])
    assert split_mc_points(task)
    assert [s.points for s in task.subtasks] == [6, 6]  # "12 Punkte" not read as a note


def test_bad_inline_note_gives_up():
    for note in ("a) 0 Punkte: x", "a) 1.3 Punkte: x"):
        task = Task(id="A7", number="7", points=3, subtasks=[mc_sub("A7a", text=note), mc_sub("A7b")])
        assert not split_mc_points(task)
        assert all(s.points is None for s in task.subtasks)


def test_reason_states_the_assumption():
    even = Task(id="A6", number="6", points=15, subtasks=[mc_sub(f"A6{c}") for c in "abcdefghijklmno"])
    assert split_mc_points(even) == "assumed 1 P each (from 15 P task total)"
    noted = Task(
        id="A7", number="7", points=4, subtasks=[mc_sub("A7a", text="a)* x"), mc_sub("A7b", text="b)* 2 Punkte: x"), mc_sub("A7c", text="c)* x")]
    )
    assert split_mc_points(noted) == "2 P for b)* from notes in the question; assumed 1 P each for the others (from 4 P task total)"


NUMPROG = SAMPLES / "numprog" / "numprog-2026-endterm.pdf"


@needs(NUMPROG)
def test_credits_count_as_points():
    exam = group(extract(NUMPROG), str(NUMPROG), pdf_path=NUMPROG)
    assert exam.total_points_stated == 42
    assert [t.points for t in exam.tasks][:3] == [8, 7, 8]
    assert [s.points for s in exam.tasks[0].subtasks] == [1.0] * 8


# ---------- Phase 2b: points from every stated source (wordings from the samples) ----------

from app.pipeline.meta import parse_mc_rule
from app.pipeline.models import Context, McRule
from app.pipeline.structure import (
    apply_header_points,
    derive_mc,
    fill_remainder,
    header_points,
    inline_points,
    two_value_split,
)


def sub(sid, points=None, text="", mc=False, key=None):
    opt = McOption(region=0, bbox=BBox(x0=0, y0=0, x1=0.1, y1=0.1), text="x")
    return Subtask(id=sid, label=f"{sid[-1]})", points=points, regions=[], text=text, mc_options=[opt, opt] if mc else [], mc_key=key)


def intro_task(intro, subs, points=None):
    return Task(id="A1", number="1", points=points, subtasks=subs, context=[Context(id="A1_ctx0", regions=[], text=intro)])


def test_header_sum_in_order():
    hp = header_points("2P+2P+2P+3P=9P")  # ds_15_endterm-sol, Aufgabe 6
    assert (hp.points, hp.parts) == (9, [2, 2, 2, 3])
    task = Task(id="A6", number="6", points=hp.points, subtasks=[sub(f"A6{c}") for c in "abcd"])
    assert apply_header_points(task, hp) == []
    assert [s.points for s in task.subtasks] == [2, 2, 2, 3]
    hp = header_points("(14 = 2 + 2 + 2 + 2 + 4 + 2 Punkte)")  # ana_2016_Main
    assert (hp.points, hp.parts, hp.title) == (14, [2, 2, 2, 2, 4, 2], "")
    hp = header_points("Vererbung (2 + 5 + 3 = 10 Punkte)")  # Eidi-2007-retake
    assert (hp.points, hp.parts, hp.title) == (10, [2, 5, 3], "Vererbung")
    assert header_points("(2+1,5+1,5 Punkte)").parts == [2, 1.5, 1.5]  # ana_2017


def test_header_sum_count_mismatch_is_an_issue():
    task = Task(id="A3", number="3", points=10, subtasks=[sub("A3a"), sub("A3b")])
    msgs = apply_header_points(task, header_points("Vererbung (2 + 5 + 3 = 10 Punkte)"))
    assert msgs and "3 parts" in msgs[0]
    assert all(s.points is None for s in task.subtasks)


def test_header_sum_contradicting_total_is_an_issue():
    hp = header_points("(2 + 3 = 6 Punkte)")
    assert hp.points == 6 and hp.parts is None and hp.issue


def test_je_each_with_total():
    hp = header_points("je 1P = 4P")  # ds_13_endterm "je 1P = 6P"
    assert (hp.points, hp.each) == (4, 1)
    task = Task(id="A9", number="9", points=hp.points, subtasks=[sub(f"A9{c}") for c in "abcd"])
    assert apply_header_points(task, hp) == []
    assert [s.points for s in task.subtasks] == [1, 1, 1, 1]
    task = Task(id="A9", number="9", points=hp.points, subtasks=[sub(f"A9{c}") for c in "abc"])
    assert apply_header_points(task, hp)  # 3 x 1 P is not 4 P
    assert all(s.points is None for s in task.subtasks)


def test_points_each():
    assert header_points("Rekursion (je 2 Punkte)").each == 2
    assert header_points("Recursion (2 points each)").each == 2


def test_slash_total_in_title():
    hp = header_points("Kurz und Knapp /21")  # Eidi-2021
    assert (hp.points, hp.title) == (21, "Kurz und Knapp")
    assert header_points("– Grundlagen [29]").bracket == 29  # Eidi-2015-losung: used when other headers do too
    assert header_points("(12)").bracket == 12  # ana_2012_Main
    assert header_points("Bytecode /10.5").points == 10.5


def test_marks_unit():
    assert header_points("Recursion (6 marks)").points == 6


def test_inline_points_in_question():
    # ds-2022-retake-sol: the note wraps onto the question's second line
    assert inline_points("a)* Seien A und B Mengen. Welche\nder folgenden Aussagen ist nicht korrekt? (2 Punkt(e))") == 2
    # gad-endterm-2019-solution
    assert inline_points("b) Welche Rotationsart? (bitte ankreuzen, nur\neine Antwort ist korrekt; 1 Punkt)") == 1
    assert inline_points("1.2: (Un-)Gleichheit [ /3.5]\n1 public class NumberCompare {") == 3.5  # Eidi-2021
    # gbs_2023 Midterm
    assert inline_points("e)* Prüfen Sie, ob das Bit gesetzt ist. (2 Punkte, Teilpunkte möglich)") == 2
    assert inline_points("d)* Ist das Petrinetz lebendig? (1 Punkt; falls nein, Teilpunkte möglich)") == 1
    # a grading scheme or a geometric "Punkt" is not a point value
    assert inline_points("a) 1 Punkt für korrekte Antwort") is None
    assert inline_points("a) Bestimmen Sie den stationären Punkt (x0, y0)") is None


def test_inline_note_with_period_or_after_a_stray_line():
    # gbs_IN0009_WS2021_RT "k) 2 Punkte. Markieren ..."; WS2324_ET "t\ni)* 1.5 Punkte: ..."
    task = Task(
        id="A9",
        number="9",
        points=4,
        subtasks=[mc_sub("A9a", text="a) x"), mc_sub("A9b", text="b) x"), mc_sub("A9k", text="k) 2 Punkte. Markieren Sie")],
    )
    assert split_mc_points(task)
    assert [s.points for s in task.subtasks] == [1, 1, 2]
    task = Task(id="A1", number="1", points=2.5, subtasks=[mc_sub("A1a", text="a)* x"), mc_sub("A1i", text="t\ni)* 1.5 Punkte: x")])
    assert split_mc_points(task)
    assert [s.points for s in task.subtasks] == [1, 1.5]


def test_printed_points_never_overwritten():
    task = Task(id="A6", number="6", points=6, subtasks=[sub("A6a", 3), sub("A6b"), sub("A6c")])
    msgs = apply_header_points(task, header_points("(2 + 2 + 2 Punkte)"))
    assert [s.points for s in task.subtasks] == [3, 2, 2]
    assert msgs and "A6a" in msgs[0]


def test_remainder_for_the_one_open_subtask():
    task = Task(id="A9", number="9", points=11, subtasks=[sub("A9a", 3), sub("A9b", 3), sub("A9c"), sub("A9d", 3)])
    fill_remainder(task, None)
    assert [s.points for s in task.subtasks] == [3, 3, 2, 3]
    two_open = Task(id="A9", number="9", points=11, subtasks=[sub("A9a", 3), sub("A9b"), sub("A9c")])
    fill_remainder(two_open, None)
    assert [s.points for s in two_open.subtasks] == [3, None, None]


def test_two_value_split_from_end():
    task = Task(id="A1", number="1", points=8, subtasks=[sub(f"A1{c}", mc=True) for c in "abcdef"])
    assert two_value_split(task, [1, 2])
    assert [s.points for s in task.subtasks] == [1, 1, 1, 1, 2, 2]


def test_two_value_split_not_unique_stays_open():
    task = Task(id="A1", number="1", points=8, subtasks=[sub(f"A1{c}", mc=True) for c in "abcdef"])
    assert two_value_split(task, [1, 4]) is None  # (8 - 6) / 3 is not whole
    assert two_value_split(task, [1, 2, 3]) is None  # three values: not guessed
    assert all(s.points is None for s in task.subtasks)
    task = intro_task("Multiple Choice (8 Punkte) Fragen: 1 Punkt oder 4 Punkte.", [sub(f"A1{c}", mc=True) for c in "abcdef"], points=8)
    msgs = derive_mc(task, None, "")
    assert all(s.points is None for s in task.subtasks)
    assert msgs and "not split" in msgs[0]


def test_two_value_split_from_intro():
    task = intro_task(
        "Multiple Choice (8 Punkte) Einfache Fragen 1 Punkt, schwere Fragen 2 Punkte.", [sub(f"A1{c}", mc=True) for c in "abcdef"], points=8
    )
    assert derive_mc(task, None, "")
    assert [s.points for s in task.subtasks] == [1, 1, 1, 1, 2, 2]


def test_mc_total_split_without_half_steps():
    # gad-retake-2024: "Multiple Choice (18 Punkte)" over 15 questions, nothing else stated
    task = intro_task(
        "Aufgabe 1\nMultiple Choice (18 Punkte)\nWählen Sie jeweils genau eine Antwort aus.",
        [sub(f"A1{chr(97 + i)}", mc=True) for i in range(15)],
        points=18,
    )
    msgs = derive_mc(task, None, "")
    assert all(s.points is None for s in task.subtasks)
    assert msgs and "not split" in msgs[0]


def test_task_level_mc_rule():
    # grnvs_midterm_2020
    intro = (
        "Aufgabe 1 Multiple Choice (3 Punkte) Die nachfolgenden Teilaufgaben sind Multiple Choice Single Answer "
        "mit 1 Punkt wenn richtig beantwortet und 0 Punkten sonst."
    )
    task = intro_task(intro, [sub(f"A1{c}", mc=True) for c in "abc"], points=3)
    derive_mc(task, McRule(kind="per_tick", right=1, wrong=-1), "")
    assert task.mc_rule == McRule(kind="all_or_nothing")
    assert [s.points for s in task.subtasks] == [1, 1, 1]
    # theo-endterm-2026
    intro = "Pro Teilaufgabe kann 1 Punkt erreicht werden. Sie erhalten diesen, wenn alle Antwortmöglichkeiten korrekt gewählt sind."
    task = intro_task(intro, [sub(f"A1{c}", mc=True) for c in "ab"], points=2)
    derive_mc(task, None, "")
    assert task.mc_rule == McRule(kind="all_or_nothing")
    assert [s.points for s in task.subtasks] == [1, 1]


GRNVS_TICK = (
    "Teilaufgaben mit nur einer richtigen Antwort werden mit 1 Punkt bewertet, wenn richtig. Teilaufgaben "
    "mit mehr als einer richtigen Antwort werden mit 0,5 Punkten pro richtigem Kreuz und −0,5 Punkten pro "
    "falscher Antwort bewertet. Die minimale Punktzahl pro Teilaufgabe beträgt 0 Punkte."
)  # grnvs_midterm_2021


def test_per_tick_max_is_correct_boxes():
    task = intro_task(GRNVS_TICK, [sub("A1a", mc=True, key=[1]), sub("A1b", mc=True, key=[0, 2, 3, 5])], points=3)
    assert derive_mc(task, None, "") == []
    assert task.mc_rule == McRule(kind="per_tick", right=0.5, wrong=-0.5, floor=0, single=1)
    assert [s.points for s in task.subtasks] == [1, 2]  # single answer 1 P, else 4 x 0.5 P
    nokey = intro_task(GRNVS_TICK, [sub(f"A1{c}", mc=True) for c in "abc"], points=3)
    msgs = derive_mc(nokey, None, "")
    assert all(s.points is None for s in nokey.subtasks)  # never 3 / 3
    assert msgs and "depend on the answer key" in msgs[0]


def test_per_tick_rule_from_the_cover():
    task = Task(id="A2", number="2", points=None, subtasks=[sub("A2a", mc=True, key=[0, 1])])
    derive_mc(task, McRule(kind="per_tick", right=1, wrong=-1), "")
    assert task.mc_rule is None and task.subtasks[0].points == 2


def test_scoring_scheme_list():
    # Eidi-2016: the minus of "−1 Punkt" is lost in the -wdh-losung extraction
    for wrong in ("−1", "1"):
        text = f"• Richtige Antwort: 1 Punkt\n• Falsche Antwort: {wrong} Punkt\n• Keine Antwort: 0 Punkte"
        assert parse_mc_rule([text]) == McRule(kind="per_tick", right=1, wrong=-1, floor=0)


def test_per_tick_points_with_n():
    assert parse_mc_rule([GRNVS_TICK]) == McRule(kind="per_tick", right=0.5, wrong=-0.5, floor=0)


GRNVS_22 = SAMPLES / "grnvs" / "grnvs_endterm_2022-solution.pdf"
DS_15 = SAMPLES / "ds" / "ds_15_endterm-sol.pdf"
EIDI_21 = SAMPLES / "eidi" / "Eidi-2021.pdf"


@needs(GRNVS_22)
def test_grnvs_2022_per_tick_points_from_key():
    exam = group(extract(GRNVS_22), str(GRNVS_22), pdf_path=GRNVS_22)
    a1 = exam.tasks[0]
    assert all(s.points is not None for s in a1.subtasks)
    assert sum(s.points for s in a1.subtasks) == a1.points == 19


@needs(DS_15)
def test_ds_15_header_sums():
    exam = group(extract(DS_15), str(DS_15), pdf_path=DS_15)
    a6 = next(t for t in exam.tasks if t.number == "6")
    assert a6.points == 9 and [s.points for s in a6.subtasks] == [2, 2, 2, 3]


@needs(EIDI_21)
def test_eidi_2021_slash_totals():
    exam = group(extract(EIDI_21), str(EIDI_21), pdf_path=EIDI_21)
    assert exam.tasks[0].points == 21 and exam.tasks[0].title == "Kurz und Knapp"


def test_per_tick_exceptions():
    # grnvs_endterm_2020
    intro = (
        "Multiple Choice Multiple Answer mit 1 Punkt pro richtigem und -1 Punkt pro falschem Kreuz "
        "(Ausnahme Teilaufgaben c) und d) mit 0,5 Punkten pro Kreuz)."
    )
    task = intro_task(intro, [sub("A1a", mc=True, key=[2, 5]), sub("A1c", mc=True, key=[0, 1, 3])], points=3.5)
    assert derive_mc(task, None, "") == []
    assert [s.points for s in task.subtasks] == [2, 1.5]
    unknown = intro_task("1 Punkt pro richtigem und -1 Punkt pro falschem Kreuz (Ausnahme: siehe Aufgabe 3)", [sub("A1a", mc=True, key=[0])])
    assert derive_mc(unknown, None, "") and unknown.subtasks[0].points is None


def test_two_value_split_needs_both_values():
    task = Task(id="A1", number="1", points=6, subtasks=[sub(f"A1{c}", mc=True) for c in "abcdef"])
    assert two_value_split(task, [0.5, 1]) is None  # all 1 P: not a two-value split


EIDI_21_SOL = SAMPLES / "eidi" / "Eidi-2021-losung.pdf"


@needs(EIDI_21_SOL)
def test_label_points_take_the_whole_number():
    exam = group(extract(EIDI_21_SOL), str(EIDI_21_SOL), pdf_path=EIDI_21_SOL)
    a3 = next(t for t in exam.tasks if t.number == "3")
    assert next(s for s in a3.subtasks if s.id == "A3f").points == 0.5  # "f) (0.5 Punkte): Character"


def test_header_points_need_a_points_context():
    for rest in ("Laufzeit O(1)", "Funktion f(2)", "Array [10]", "Komplexität in O(n)"):
        hp = header_points(rest)
        assert hp.points is None, rest
    assert header_points("Laufzeit O(1)").bracket is None
    hp = header_points("Teil 1 + 2")  # a sum without a unit or a stated total is not points
    assert (hp.points, hp.parts) == (None, None)
    hp = header_points("Teil 1 + 2 (10 Punkte)")
    assert (hp.points, hp.parts) == (10, None)


EIDI_15 = SAMPLES / "eidi" / "Eidi-2015-losung.pdf"


@needs(EIDI_15)
def test_bracket_totals_as_the_exam_notation():
    exam = group(extract(EIDI_15), str(EIDI_15), pdf_path=EIDI_15)
    assert [t.points for t in exam.tasks][:3] == [29, 10, 9]
