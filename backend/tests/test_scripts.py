from pathlib import Path

import pytest

from app.pipeline.extract import extract, fold_scripts, split_words
from app.pipeline.structure import group

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def ch(text, x0, size=10.0, base=100.0, color=(0, 0, 0), font="CMR10"):
    w = size * 0.5
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + w,
        "size": size,
        "top": base - size,
        "bottom": base,
        "matrix": (1, 0, 0, 1, x0, -base),
        "upright": True,
        "fontname": font,
        "non_stroking_color": color,
        "doctop": base - size,
    }


def line(chars):
    return {
        "text": "".join(c["text"] for c in chars),
        "chars": chars,
        "x0": chars[0]["x0"],
        "x1": chars[-1]["x1"],
        "top": min(c["top"] for c in chars),
        "bottom": max(c["bottom"] for c in chars),
    }


def texts(lines):
    return [ln["text"] for ln in fold_scripts(lines)]


def test_superscript():
    assert texts([line([ch("2", 0), ch("2", 5.2, 6.5, 95)])]) == ["2^{2}"]


def test_subscript_on_own_line():
    base = line([ch("(", 0), ch("x", 5), ch(" ", 10), ch(",", 15), ch("y", 25), ch(" ", 30), ch(")", 35)])
    sub = line([ch("0", 10.2, 6.5, 104), ch("0", 30.2, 6.5, 104)])
    assert texts([base, sub]) == ["(x_{0} , y_{0} )"]


def test_multi_char_script():
    out = texts([line([ch("e", 0), ch("-", 5.2, 6.5, 95), ch("x", 7.5, 6.5, 95)])])
    assert out == ["e^{-x}"]


def test_labels_untouched():
    for label in ("a)", "1.2", "(a)"):
        chars = [ch(c, 5 * i) for i, c in enumerate(label)]
        chars.append(ch("*", 5 * len(label), 6.5, 94))
        assert texts([line(chars)]) == [label + "*"]
    chars = [ch(c, 5 * i) for i, c in enumerate("(a)")]
    assert texts([line(chars)]) == ["(a)"]


def test_footnote_star_untouched():
    chars = [ch(c, 5 * i) for i, c in enumerate("Note")] + [ch("*", 20, 6.5, 94)]
    assert texts([line(chars)]) == ["Note*"]


def test_script_after_text_with_parens_folds():
    chars = [ch(t, 5 * i) for i, t in enumerate("O(n)")] + [ch("2", 20.2, 6.5, 95)]
    assert texts([line(chars)]) == ["O(n)^{2}"]


def test_digit_right_after_label_not_folded():
    chars = [ch("a", 0), ch(")", 5), ch("2", 10.2, 6.5, 95)]
    assert texts([line(chars)]) == ["a)2"]


def test_option_word_gets_script():
    folded = fold_scripts([line([ch("x", 0), ch("2", 5.2, 6.5, 95)])])[0]
    assert [w.text for w in split_words(folded["chars"], 90, 100)] == ["x^{2}"]


def test_run_over_limit_stays():
    chars = [ch("x", 0)] + [ch(t, 5.2 + 3.3 * i, 6.5, 95) for i, t in enumerate("abcdefg")]
    assert len(fold_scripts([line(chars)])[0]["chars"]) == 8


def test_other_colour_not_folded():
    chars = [ch("x", 0), ch("2", 5.2, 6.5, 95, color=(0, 0, 1))]
    assert texts([line(chars)]) == ["x2"]


def test_stacked_is_uncertain_and_plain():
    ln = fold_scripts([line([ch("x", 0), ch("1", 5.2, 6.5, 95), ch("2", 5.2, 6.5, 105)])])[0]
    assert ln["scripts_uncertain"] and "{" not in ln["text"]


def test_operator_base_is_uncertain_and_plain():
    ln = fold_scripts([line([ch("\u2212", 0), ch("1", 5.2, 6.5, 95)])])[0]
    assert ln["scripts_uncertain"] and "{" not in ln["text"]


def test_big_operator_font_base():
    ln = fold_scripts([line([ch("P", 0, font="CMEX10"), ch("n", 5.2, 6.5, 105)])])[0]
    assert ln["scripts_uncertain"] and "{" not in ln["text"]


def test_script_inside_word_refused():
    # limit written under "lim": the script sits between the letters of the word
    ln = fold_scripts([line([ch("l", 0), ch("i", 5), ch("m", 10), ch("n", 5.2, 6.5, 105)])])[0]
    assert ln["scripts_uncertain"] and "{" not in ln["text"]


NUMPROG = SAMPLES / "numprog" / "numprog-2026-endterm.pdf"


@pytest.mark.skipif(not NUMPROG.exists(), reason="sample missing")
def test_numprog_3a_subscripts():
    exam = group(extract(NUMPROG), str(NUMPROG), pdf_path=NUMPROG)
    sub = next(s for t in exam.tasks if t.number == "3" for s in t.subtasks if s.label == "a)*")
    assert "x_{0}" in sub.text and "0 0 1 1" not in sub.text


def test_fold_across_closing_paren_refused():
    # (a_n)_n: the second script must not merge into "(a_{nn})"
    close = dict(ch(")", 13.5), x1=16.5)  # narrow, so the second script chains onto the first
    chars = [ch("(", 0), ch("a", 5), ch("n", 10.2, 6.5, 103), close, ch("n", 16.7, 6.5, 103)]
    ln = fold_scripts([line(chars)])[0]
    assert ln["scripts_uncertain"] and "{" not in ln["text"]
    # (3^9)^5
    chars = [ch("(", 0), ch("3", 5), ch("9", 10.2, 6.5, 95), close, ch("5", 16.7, 6.5, 95)]
    ln = fold_scripts([line(chars)])[0]
    assert ln["scripts_uncertain"] and "{" not in ln["text"]


def test_clean_fold_before_gap_still_folds():
    chars = [ch("x", 0), ch("0", 5.2, 6.5, 103), ch(" ", 8.5), ch("=", 12), ch("2", 20), ch("8", 25.2, 6.5, 95)]
    assert texts([line(chars)]) == ["x_{0} = 2^{8}"]
