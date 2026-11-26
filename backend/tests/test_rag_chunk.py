from app.rag.chunk import MAX_CHARS, split


def test_split_packs_lines_and_respects_limit():
    text = "\n".join(["alpha " * 20] * 12)
    pieces = split(text)
    assert len(pieces) > 1
    assert all(len(p) <= MAX_CHARS for p in pieces)
    assert " ".join(pieces).split() == text.split()


def test_split_cuts_a_single_huge_line_and_skips_blanks():
    assert split("\n\n  \n") == []
    pieces = split("x" * (MAX_CHARS * 2 + 5))
    assert [len(p) for p in pieces] == [MAX_CHARS, MAX_CHARS, 5]
