"""Output contract of the pipeline: the exam structure the frontend consumes.

Coordinates are PDF points with a top-left origin (same as pdfplumber), pages are 0-based.
"""

from typing import Literal

from pydantic import BaseModel


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def height(self) -> float:
        return self.y1 - self.y0


class Region(BaseModel):
    page: int
    bbox: BBox
    image: str | None = None  # crop file name, filled in by the renderer
    # figures, tables, formulas, code or sub/superscripts: the crop says more than the text.
    # None for exams processed before this flag existed; treat as True.
    visual: bool | None = None


class McOption(BaseModel):
    region: int  # index into the subtask's regions
    bbox: BBox  # checkbox, relative 0..1 to that region's bbox (x to width, y to height)
    text: str  # option text printed right of the box


class AnswerBox(BaseModel):
    region: int  # index into the subtask's regions
    bbox: BBox  # relative 0..1 to that region's bbox, like McOption.bbox


class Subtask(BaseModel):
    id: str  # e.g. "A2b"
    label: str  # as printed, e.g. "b)*"
    points: float | None = None
    independent: bool = False  # marked with * = solvable without previous results
    regions: list[Region]
    text: str = ""
    solution_text: str = ""  # solution ink found inside the regions (solution PDFs only)
    mc_options: list[McOption] = []  # set when the subtask has >= 2 checkboxes
    mc_key: list[int] | None = None  # ticked option indices (solution PDFs only)
    answer_boxes: list[AnswerBox] = []  # printed answer areas, at most one per region (non-MC only)


class Context(BaseModel):
    """Shared material shown alongside subtasks: the task stem, or text between two subtasks
    that introduces the following ones ("Knoten 1 sende nun ...")."""

    id: str
    applies_from: str | None = None  # first subtask id this is relevant for; None = whole task
    regions: list[Region]
    text: str = ""


class McRule(BaseModel):
    kind: Literal["all_or_nothing", "per_tick"]
    right: float = 1
    wrong: float = 0
    floor: float = 0
    single: float | None = None  # points of a single-answer question, when the exam states them (grnvs: 1 P)


class Task(BaseModel):
    id: str  # e.g. "A2"
    number: str
    title: str = ""
    points: float | None = None
    context: list[Context] = []
    subtasks: list[Subtask]
    mc_rule: McRule | None = None  # stated in the task's intro; overrides ExamStructure.mc_rule


class Issue(BaseModel):
    level: Literal["warn", "error"]
    message: str


class ExamStructure(BaseModel):
    source: str
    page_count: int
    page_sizes: list[tuple[float, float]]
    kind: Literal["digital", "scanned", "mixed"]
    is_solution: bool
    total_points_stated: float | None = None
    duration_minutes: int | None = None
    mc_rule: McRule | None = None
    tasks: list[Task]
    issues: list[Issue] = []

    @property
    def status(self) -> Literal["ok", "warn", "error"]:
        if any(i.level == "error" for i in self.issues):
            return "error"
        return "warn" if self.issues else "ok"
