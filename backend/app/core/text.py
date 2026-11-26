def clean(name: str | None, length: int = 100) -> str | None:
    """Client text for a Subject, title or filename: Postgres text rejects NUL, so drop it, cap, strip; None when nothing is left."""
    return (name or "").replace("\x00", "")[:length].strip() or None
