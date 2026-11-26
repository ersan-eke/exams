import pytest
from conftest import SAMPLES

from app.pipeline import process
from app.pipeline.meta import parse_duration, parse_mc_rule
from app.pipeline.models import McRule


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Uhrzeit: 11:30–13:00", 90),
        ("Uhrzeit: 11:00-12:30", 90),
        ("Die Arbeitszeit beträgt 150 Minuten.", 150),
        ("Bearbeitungszeit: 90 Minuten", 90),
        ("DieArbeitszeitbeträgt150Minuten.", 150),
        ("Name: Mustermann", None),
    ],
)
def test_duration(text, expected):
    assert parse_duration([text]) == expected


def test_per_tick():
    texts = [
        "Teilaufgaben mit mehr als einer richtigen Antwort werden mit 1 Punkt pro richtigem und -1 Punkt pro falschem Kreuz bewertet",
        "Die minimale Punktzahl pro Teilaufgabe beträgt 0 Punkte",
    ]
    assert parse_mc_rule(texts) == McRule(kind="per_tick", right=1, wrong=-1, floor=0)


def test_all_or_nothing():
    r = parse_mc_rule(["Bei Multiple Choice Fragen müssen alle Antworten korrekt angekreuzt sein"])
    assert r == McRule(kind="all_or_nothing")


def test_no_rule():
    assert parse_mc_rule(["Aufgabe 1 Rechnen"]) is None


PDF = SAMPLES / "grnvs" / "grnvs_retake_2024.pdf"


@pytest.mark.skipif(not PDF.exists(), reason="sample missing")
def test_sample_retake_2024(tmp_path):
    exam = process(PDF, tmp_path, debug=False)
    assert exam.duration_minutes == 90
    assert exam.mc_rule is not None and exam.mc_rule.kind == "per_tick"


def test_specific_duration_wins_over_generic():
    texts = ["Die Arbeitszeit beträgt 150 Minuten.", "Zeit pro Aufgabe ca. 20 Minuten"]
    assert parse_duration(texts) == 150
    assert parse_duration(texts[::-1]) == 150


def test_per_tick_missing_spaces():
    r = parse_mc_rule(["1Punktprorichtigemund-1PunktprofalschemKreuz"])
    assert r == McRule(kind="per_tick", right=1, wrong=-1, floor=0)


def test_per_tick_wrong_without_sign_is_a_deduction():
    r = parse_mc_rule(["1 Punkt pro richtigem und 1 Punkt pro falschem Kreuz"])
    assert r == McRule(kind="per_tick", right=1, wrong=-1, floor=0)


@pytest.mark.parametrize(
    "text",
    [
        "If the wrong answer or multiple answers are marked, no credit will be given.",
        "Ifthewronganswerormultipleanswersaremarked,nocreditwillbegiven.",
        "If more than one answer is marked, no points are awarded.",
    ],
)
def test_all_or_nothing_english(text):
    assert parse_mc_rule([text]) == McRule(kind="all_or_nothing")
