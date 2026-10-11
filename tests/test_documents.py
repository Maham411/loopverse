"""Traps 5 and 7: old vs new guidance, and the trick document."""
import shutil

from smogguard import config as C
from smogguard.documents import DocumentStore, load_document, parse_frontmatter


def test_frontmatter_found_after_preamble():
    meta, body = parse_frontmatter((C.DOCS_DIR / "DOC-03_provincial_education_directive.md").read_text())
    assert meta["status"] == "current" and meta["supersedes"] == "DOC-02"


def test_superseded_document_is_never_searchable():
    store = DocumentStore()
    assert store.docs["DOC-02"].status == "superseded"
    assert store.superseded() == {"DOC-02": "DOC-03"}
    assert all(c.doc_id != "DOC-02" for c in store.searchable)
    assert not any(c.doc_id == "DOC-02" for _, c in store.search("schools close 300 two consecutive days", top_k=50))


def test_current_school_thresholds_present():
    text = (C.DOCS_DIR / "DOC-03_provincial_education_directive.md").read_text()
    assert "165–249" in text and "250 µg/m³ or above" in text  # constants used by the assistant


def test_hidden_comment_injection_removed():
    doc = load_document(C.DOCS_DIR / "DOC-07_community_bulletin.md")
    assert doc.hidden_removed and "Ignore all previous instructions" in doc.hidden_removed[0]
    assert all("SYSTEM NOTE" not in c.text and "below 50" not in c.text for c in doc.chunks)


def test_visible_injection_is_quarantined(tmp_path):
    for p in C.DOCS_DIR.glob("*.md"):
        shutil.copy(p, tmp_path / p.name)
    p = tmp_path / "DOC-07_community_bulletin.md"
    p.write_text(p.read_text().replace("<!--", "").replace("-->", ""))  # make the attack visible text
    store = DocumentStore(tmp_path)
    assert len(store.docs["DOC-07"].quarantined) == 1
    assert all("Ignore all previous" not in c.text for c in store.searchable)
