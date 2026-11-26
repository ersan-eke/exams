"""Port of the app's scoring (frontend/src/lib/scoring.ts, mcKeys/matchSolution in lib/solution.ts), so server-side
summaries such as MCP progress show the same numbers as the app. Change both together."""

from ..pipeline.models import ExamStructure, McRule, Subtask, Task
from .sync import AnswerWire, AttemptWire


def mc_points(rule: McRule, ticks: list[int], key: list[int], mx: float) -> float:
    t, k = set(ticks), set(key)
    if rule.kind == "all_or_nothing":
        return mx if t == k else 0
    right, wrong = len(t & k), len(t - k)
    total = rule.right * right + rule.wrong * wrong
    # a single-answer question worth more than one tick (grnvs: 1 P, 0.5 P per tick otherwise): all or nothing
    if len(k) == 1 and mx > rule.right:
        return mx if right == 1 and wrong == 0 else max(rule.floor, min(0, total))
    return min(mx, max(rule.floor, total))


def _is_mc(s: Subtask) -> bool:
    return len(s.mc_options) > 0


def max_points(task: Task, s: Subtask, rule: McRule | None, key: list[int] | None) -> float | None:
    """A subtask's max points; an MC subtask without its own gets an equal share of what its task has left (see scoring.ts)."""
    if s.points is not None:
        return s.points
    effective = task.mc_rule or rule
    if _is_mc(s) and effective is not None and effective.kind == "per_tick":
        if not key:
            return None
        return effective.single if len(key) == 1 and effective.single is not None else len(key) * effective.right
    if task.points is None or not _is_mc(s):
        return None
    open_ = [x for x in task.subtasks if x.points is None]
    if not all(_is_mc(x) for x in open_):
        return None
    share = max(0, task.points - sum(x.points or 0 for x in task.subtasks)) / len(open_)
    return share if (share * 2).is_integer() else None


def match_solution(exam: ExamStructure, solution: ExamStructure) -> dict[str, Subtask]:
    """Each exam subtask id to its solution subtask: same id, else same task number + label."""
    by_id = {s.id: s for t in solution.tasks for s in t.subtasks}
    by_label = {(t.number, s.label): s for t in solution.tasks for s in t.subtasks}
    return {s.id: m for t in exam.tasks for s in t.subtasks if (m := by_id.get(s.id) or by_label.get((t.number, s.label)))}


def mc_keys(exam: ExamStructure, solution: ExamStructure | None) -> dict[str, list[int]]:
    """MC answer key per subtask id: the exam's own key, else the matched solution subtask's key."""
    matches = match_solution(exam, solution) if solution else {}
    out = {}
    for t in exam.tasks:
        for s in t.subtasks:
            key = s.mc_key or (matches[s.id].mc_key if s.id in matches else None)
            if key:
                out[s.id] = key
    return out


def with_overrides(exam: ExamStructure, overrides: dict | None) -> ExamStructure:
    """The structure with the hand-set max points (Exam.point_overrides) in place, like withPointOverrides."""
    o = {k: float(v) for k, v in (overrides or {}).items() if v is not None}
    if not o:
        return exam
    tasks = [
        t.model_copy(update={"subtasks": [s.model_copy(update={"points": o[s.id]}) if s.id in o else s for s in t.subtasks]}) for t in exam.tasks
    ]
    return exam.model_copy(update={"tasks": tasks})


def _auto(a: AttemptWire, task: Task, mx: float, key: list[int] | None, answer: AnswerWire | None) -> float:
    return mc_points(task.mc_rule or a.mc_rule, answer.ticks if answer else [], key, mx) if key else 0


def subtask_scores(a: AttemptWire, exam: ExamStructure, keys: dict[str, list[int]]) -> dict[str, tuple[float, float | None]]:
    """(main points, max or None) per subtask of the attempt's tasks: the hand grade, else automatic MC points."""
    answers = a.snapshot if a.snapshot is not None else a.answers
    out = {}
    for task in exam.tasks:
        if task.id not in a.included_task_ids:
            continue
        for s in task.subtasks:
            if a.time_limit_ms == 0 and s.id not in a.grades:  # a practice attempt from MCP covers only what it graded
                continue
            key = keys.get(s.id)
            mx = max_points(task, s, a.mc_rule, key)
            g = a.grades.get(s.id)
            out[s.id] = (g.main if g and g.main is not None else _auto(a, task, mx or 0, key, answers.get(s.id)), mx)
    return out
