from pdf_util import L, make_pdf

from app.rag.deck import read_deck

BLUE = (0, 0.4, 0.74)


def footer(label, section="Kapitel 3: Vermittlungsschicht"):
    return L(f"{section} {label}", size=6, y=15)


def structured(n=4):
    return make_pdf(
        [
            [
                L(f"Titel {i}", 24, BLUE, y=790),
                L("Ein Kollisionsdomaene Begriff", 12, BLUE, y=700),
                L("Normaler Text hier", 12, y=650),
                footer(f"3-{i}"),
            ]
            for i in range(1, n + 1)
        ]
    )


def test_structured_pages_give_label_title_section_and_headings(tmp_path):
    f = tmp_path / "d.pdf"
    f.write_bytes(structured())
    p = read_deck(f)[1]
    assert (p.page, p.label, p.title, p.section) == (2, "3-2", "Titel 2", "Kapitel 3: Vermittlungsschicht")
    assert p.headings == ["Ein Kollisionsdomaene Begriff"] and "Normaler Text hier" in p.body and "3-2" not in p.body


def test_a_deck_without_structure_still_has_its_text(tmp_path):
    f = tmp_path / "d.pdf"
    f.write_bytes(make_pdf([["alpha beta"], ["gamma delta"]]))
    pages = read_deck(f)
    assert [(p.label, p.title, p.section, p.headings) for p in pages] == [(None, "", "", [])] * 2
    assert pages[1].body == "gamma delta"


def test_a_label_every_page_shares_is_not_a_slide_number(tmp_path):
    f = tmp_path / "d.pdf"
    f.write_bytes(make_pdf([[f"Seite {i}", L("Kurs 2018-25", 6, y=15)] for i in range(12)]))
    assert {p.label for p in read_deck(f)} == {None}


def test_bookmarks_give_the_title(tmp_path):
    f = tmp_path / "d.pdf"
    f.write_bytes(make_pdf([["alpha"], ["beta"]], outline=[("Zweites Kapitel", 2)]))
    assert [p.title for p in read_deck(f)] == ["", "Zweites Kapitel"]
