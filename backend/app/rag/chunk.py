"""Cut page text into searchable pieces. The model sees about 128 tokens, so pieces stay short."""

MAX_CHARS = 600


def split(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Pack lines into pieces of at most `limit` characters; a longer single line is cut."""
    pieces: list[str] = []
    cur = ""
    for line in (ln.strip() for ln in text.splitlines()):
        while len(line) > limit:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(line[:limit])
            line = line[limit:]
        if not line:
            continue
        if cur and len(cur) + 1 + len(line) > limit:
            pieces.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        pieces.append(cur)
    return pieces
