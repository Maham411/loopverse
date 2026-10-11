"""Document store for the advisory assistant.

Defence in depth for the trick-document trap:
  1. Hidden HTML comments are removed at ingestion (a human reader never sees
     them, so they are never legitimate evidence) and recorded in the audit.
  2. Every chunk is scanned for instruction-like text aimed at an AI
     ("ignore all previous instructions", "system note", ...). Matching chunks
     are quarantined and can never be retrieved.
  3. Retrieved text is only ever quoted as evidence; it is never executed.
Superseded documents (status: superseded) are kept for the audit but are
never searched.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import config as C
from .language import tokenize

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|rules)",
    r"disregard (all |any )?(the )?(previous|prior|above|safety)",
    r"system (note|prompt|message|instruction)",
    r"note to (the )?(assistant|ai|model|chatbot)",
    r"you are now", r"from now on,? (always|you)",
    r"always (respond|answer|say|reply)",
    r"do not (cite|mention|reveal|tell)",
    r"(assistant|ai model|language model)s? (must|should) (ignore|say|respond)",
    r"(override|bypass) (the )?(safety|system|rules)",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)
_HIDDEN_RE = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    status: str
    authority: str
    published_date: str
    section: str
    lead_in: str
    text: str
    kind: str                      # bullet | paragraph | faq | note
    tokens: list = field(default_factory=list)


@dataclass
class Document:
    doc_id: str
    title: str
    status: str
    authority: str
    published_date: str
    path: str
    meta: dict
    hidden_removed: list
    chunks: list
    quarantined: list


def parse_frontmatter(raw):
    """Find the first ---/--- metadata block anywhere (DOC-03 has a preamble before it)."""
    m = re.search(r"^---\s*\n(.*?)\n---\s*$", raw, re.DOTALL | re.MULTILINE)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    body = raw[: m.start()] + raw[m.end():]
    return meta, body


def _chunk_body(body):
    """Split markdown into bullet / paragraph / FAQ chunks with section + lead-in."""
    section, lead_in, pending_q = "", "", None
    out = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            section, lead_in = s.lstrip("#").strip(), ""
            continue
        if s.startswith(">"):
            out.append(("note", section, "", s.lstrip("> ").replace("**", "")))
            continue
        bold = re.fullmatch(r"\*\*(.+?)\*\*", s)
        if bold:
            text = bold.group(1).strip()
            if text.endswith("?"):
                pending_q = text
            else:
                section, lead_in = text, ""
            continue
        if s.startswith(("- ", "* ")):
            out.append(("bullet", section, lead_in, s[2:].strip()))
            continue
        if pending_q:
            out.append(("faq", section, pending_q, f"{pending_q} {s}"))
            pending_q = None
            continue
        if s.endswith(":"):
            lead_in = s
        out.append(("paragraph", section, lead_in if s.endswith(":") else "", s))
    return out


def load_document(path):
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    hidden = [h.strip("<!-> \n") for h in _HIDDEN_RE.findall(raw)]
    raw = _HIDDEN_RE.sub("", raw)
    meta, body = parse_frontmatter(raw)
    doc_id = meta.get("document_id") or re.match(r"(DOC-\d+)", Path(path).name).group(1)
    doc = Document(doc_id=doc_id, title=meta.get("title", doc_id),
                   status=meta.get("status", "unknown").lower(),
                   authority=meta.get("authority", ""), published_date=meta.get("published_date", ""),
                   path=str(path), meta=meta, hidden_removed=hidden, chunks=[], quarantined=[])
    for i, (kind, section, lead_in, text) in enumerate(_chunk_body(body)):
        if kind == "paragraph" and text.endswith(":"):
            continue  # pure lead-in lines are carried on the bullets below them
        ch = Chunk(f"{doc_id}#{i}", doc_id, doc.title, doc.status, doc.authority,
                   doc.published_date, section, lead_in, text, kind)
        # Title counted twice: a document whose title names the topic ranks higher.
        ch.tokens = tokenize(f"{text} {lead_in} {section} {doc.title} {doc.title}")
        if _INJECTION_RE.search(text):
            doc.quarantined.append(ch)
        else:
            doc.chunks.append(ch)
    return doc


class DocumentStore:
    """Loads docs/ and serves BM25 search over current, non-quarantined chunks."""

    def __init__(self, docs_dir=C.DOCS_DIR, k1=1.4, b=0.6):
        self.docs = {}
        for p in sorted(Path(docs_dir).glob("DOC-*.md")):
            d = load_document(p)
            self.docs[d.doc_id] = d
        self.searchable = [c for d in self.docs.values() if d.status == "current" for c in d.chunks]
        self.k1, self.b = k1, b
        self.avgdl = sum(len(c.tokens) for c in self.searchable) / max(len(self.searchable), 1)
        df = Counter(t for c in self.searchable for t in set(c.tokens))
        n = len(self.searchable)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def current_ids(self):
        return [d for d, doc in self.docs.items() if doc.status == "current"]

    def superseded(self):
        return {d: doc.meta.get("superseded_by", "") for d, doc in self.docs.items()
                if doc.status == "superseded"}

    def score(self, chunk, q_tokens):
        tf = Counter(chunk.tokens)
        dl = len(chunk.tokens)
        s = 0.0
        for t in set(q_tokens):
            if t in tf:
                f = tf[t]
                s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        if chunk.kind == "faq" and s > 0:
            # The user's question matches the FAQ's own question -> strong evidence.
            asked = set(tokenize(chunk.lead_in))
            if asked:
                s += 2.0 * len(asked & set(q_tokens)) / len(asked)
        if re.search(r"\(DOC-\d+\)|See DOC-\d+", chunk.text):
            s *= 0.6  # a passage pointing to another document ranks below that document
        if "unofficial" in chunk.authority.lower():
            s *= 0.8  # official guidance outranks community tips
        return s

    def search(self, query, top_k=12, extra_tokens=(), tokens=None):
        q = (list(tokens) if tokens is not None else tokenize(query)) + list(extra_tokens)
        scored = [(self.score(c, q), c) for c in self.searchable]
        scored = [x for x in scored if x[0] > 0]
        scored.sort(key=lambda x: (-x[0], x[1].chunk_id))
        return scored[:top_k]

    def audit(self):
        return [{
            "doc_id": d.doc_id, "title": d.title, "status": d.status,
            "published_date": d.published_date, "authority": d.authority,
            "superseded_by": d.meta.get("superseded_by", ""), "supersedes": d.meta.get("supersedes", ""),
            "chunks": len(d.chunks), "quarantined_chunks": [c.text for c in d.quarantined],
            "hidden_content_removed": d.hidden_removed,
            "searchable": d.status == "current",
        } for d in self.docs.values()]


@lru_cache(maxsize=4)
def get_store(docs_dir=str(C.DOCS_DIR)):
    return DocumentStore(docs_dir)
