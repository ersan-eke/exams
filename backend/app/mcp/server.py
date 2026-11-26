"""The MCP server: tool wrappers that bind the token's user and a DB session to the logic in tools."""

import json

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from ..db.session import SessionLocal
from . import tools
from .auth import BearerAuth, current_user_id

mcp = MCPServer(
    "exam-sim",
    instructions=(
        "These are the user's own past exams, synced from the exam-sim app. Before the first question of a session, "
        "ask once whether the user wants hints, and keep to the answer for the rest of the session. "
        "With hints: when the user doesn't know or is stuck, give one hint that points the way without giving the "
        "answer (for MC you may rule out wrong options); if they still don't know, show the solution and explain it. "
        "Without hints: when the user doesn't know, show the solution and explain it right away. "
        "To quiz: show a question from get_task "
        "(never from find_tasks, whose preview is cut short) with its full text and every MC option, numbered. "
        "Fetch the solution with get_task(include_solution=true) only after the user has answered, and never reveal it before. "
        "Then give feedback: when the answer is wrong or partly right, explain why the correct answer is right and what "
        "the user's answer got wrong. Save it with record_practice (for MC pass ticks, the chosen option indices; 'I don't "
        "know' is ticks [] and 0 points), "
        "then show the next question right away, from get_task's `next` (the exam's order) unless the user asked for "
        "a random or a specific one, and mention they can say stop."
    ),
)


@mcp.tool()
def list_subjects() -> list[dict]:
    """The user's subjects (courses) with exam count, handed-in attempt count and score share (0..1, null if nothing graded)."""
    return _run(tools.list_subjects)


def _run(fn, *args):
    with SessionLocal() as db:
        try:
            return fn(db, current_user_id.get(), *args)
        except (tools.NotFound, tools.BadInput) as e:  # meant for the model; other errors stay opaque
            raise ToolError(str(e)) from e


@mcp.tool()
def progress(subject: str | None = None) -> list[dict]:
    """How the user is doing: per subject the overall score share (0..1), tasks weakest first, the last 5 attempts
    and exams not attempted yet. Call it to decide what to practice next. subject narrows to one (case-insensitive)."""
    return _run(tools.progress, subject)


@mcp.tool()
def find_tasks(subject: str, query: str | None = None, filter: str | None = None) -> list[dict]:
    """Subtasks of a subject to quiz on (at most 20); `preview` is the start of the text only, so show a question
    through get_task. query matches the subtask text, label or task title.
    filter: "unattempted", "scored_below:<0..1>" (last score share below it) or "has_solution".
    Pass a row's id to get_task."""
    return _run(tools.find_tasks, subject, query, filter)


@mcp.tool()
def get_task(ref: str, include_solution: bool = False) -> list[str | Image]:
    """One subtask (ref = an id from find_tasks) as JSON plus its exam crops; the crops often hold figures or formulas
    the text misses. `next` is the following subtask's ref in exam order (null at the end). Show it and let the user
    answer first: call again with include_solution=true only after the user has answered. The solution has the
    uploaded solution's text, mc_key (0-based indices into mc_options) and its crops, where the ticked boxes or
    handwritten answers mark the correct solution."""
    task, paths = _run(tools.get_task, ref, include_solution)
    return [json.dumps(task, ensure_ascii=False), *(Image(path=p) for p in paths)]


@mcp.tool()
def my_history(ref: str) -> list[dict]:
    """The user's past handed-in answers to one subtask (ref as in get_task), newest first, with points, max, the
    grader's comment and LLM feedback. Use it to point out recurring mistakes."""
    return _run(tools.my_history, ref)


@mcp.tool()
def record_practice(results: list[tools.PracticeResult]) -> dict:
    """Save the user's practice on one task after grading their answers against the solution from
    get_task(include_solution=true). Each result: subtask_id (an id from find_tasks), the user's answer, the points
    you gave (clamped to 0..max), short feedback and, for an MC subtask, ticks: the options the user chose as 0-based
    indices into mc_options (the app shows them as ticked boxes); ticks [] and 0 points when the user didn't answer or
    didn't know, so it still counts. Never tick an option the user didn't choose. Practice at one exam within 3 hours goes into one handed-in
    attempt in the user's app; saving a subtask again replaces its earlier answer there."""
    return _run(tools.record_practice, results)


@mcp.tool()
def set_points(ref: str, points: float) -> dict:
    """Fix a subtask's max points (ref as in get_task) when the printed value is wrong. 0 < points <= 1000."""
    return _run(tools.set_points, ref, points)


http_app = BearerAuth(
    mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        # bearer auth protects it, and a browser page cannot attach the token
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
)
