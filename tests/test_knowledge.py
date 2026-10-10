from app.knowledge.documents import MAX_WORDS, Passage, load_passages, split_document
from app.knowledge.store import ChromaPassageStore

DOCUMENT = """---
document: SOP-99
title: Test Procedure
revision: 2
effective: 2026-01-01
plant: PN-01
---

# SOP-99 Test Procedure

## 9.1 First rule

Short rule text.

## 9.2 Long rule

{long}
"""


def test_each_numbered_section_becomes_one_labelled_passage():
    passages = split_document(DOCUMENT.format(long="word"))
    assert [p.id for p in passages] == ["SOP-99#9.1", "SOP-99#9.2"]
    first = passages[0]
    assert "Short rule text." in first.text and "9.1 First rule" in first.text
    assert first.metadata == {
        "document": "SOP-99",
        "title": "Test Procedure",
        "revision": "2",
        "effective": "2026-01-01",
        "plant": "PN-01",
        "section": "9.1",
        "section_title": "First rule",
    }


def test_a_long_section_is_split_into_overlapping_pieces():
    passages = split_document(DOCUMENT.format(long=" ".join(f"w{i}" for i in range(700))))
    pieces = [p for p in passages if p.metadata["section"] == "9.2"]
    assert [p.id for p in pieces] == ["SOP-99#9.2/1", "SOP-99#9.2/2", "SOP-99#9.2/3"]
    assert all(len(p.text.split()) <= MAX_WORDS + 10 for p in pieces)
    assert "w699" in pieces[-1].text and "w250" in pieces[0].text and "w250" in pieces[1].text


def test_the_sop_set_loads_with_tables_kept_whole():
    passages = load_passages("data/sops")
    ids = [p.id for p in passages]
    assert len(ids) == len(set(ids)) == 30
    assert {p.metadata["document"] for p in passages} == {f"SOP-0{n}" for n in range(1, 6)}
    table = next(p for p in passages if p.id == "SOP-03#3.2")
    assert "Sanjay Patil" in table.text and "Farah Sheikh" in table.text


def test_search_is_filtered_by_plant(tmp_path):
    store = ChromaPassageStore(str(tmp_path), "fake-model")
    passages = [
        Passage("A#1", "rule for this plant", {"plant": "PN-01"}),
        Passage("B#1", "rule for another plant", {"plant": "PN-02"}),
    ]
    store.replace_all(passages, [[1.0, 0.0], [1.0, 0.0]])
    assert store.count() == 2
    assert [hit.id for hit in store.search([1.0, 0.0], top_k=5, plant="PN-01")] == ["A#1"]

    store.replace_all(passages[:1], [[1.0, 0.0]])
    assert store.count() == 1
