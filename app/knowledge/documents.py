"""Load SOP documents and split them into passages, one per numbered section."""

import re
from dataclasses import dataclass
from pathlib import Path

# A section longer than this is split into overlapping pieces.
MAX_WORDS = 300
OVERLAP_WORDS = 50

HEADING = re.compile(r"^## +(\d+\.\d+) +(.+)$", re.MULTILINE)


@dataclass
class Passage:
    id: str
    text: str
    metadata: dict


def _front_matter(raw: str) -> tuple[dict, str]:
    match = re.match(r"---\n(.*?)\n---\n", raw, re.DOTALL)
    if not match:
        raise ValueError("document has no front matter")
    fields = dict(line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    return {key.strip(): value.strip() for key, value in fields.items()}, raw[match.end():]


def _pieces(body: str) -> list[str]:
    words = body.split()
    if len(words) <= MAX_WORDS:
        return [body]
    step = MAX_WORDS - OVERLAP_WORDS
    return [" ".join(words[start:start + MAX_WORDS]) for start in range(0, len(words) - OVERLAP_WORDS, step)]


def split_document(raw: str) -> list[Passage]:
    header, body = _front_matter(raw.replace("\r\n", "\n"))
    headings = list(HEADING.finditer(body))
    passages = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        section, title = heading.group(1), heading.group(2).strip()
        pieces = _pieces(body[heading.end():end].strip())
        for number, piece in enumerate(pieces, start=1):
            suffix = f"/{number}" if len(pieces) > 1 else ""
            passages.append(
                Passage(
                    id=f"{header['document']}#{section}{suffix}",
                    # The document and section titles travel with the text so a passage is searchable on its own.
                    text=f"{header['document']} {header['title']} - {section} {title}\n\n{piece}",
                    metadata={
                        "document": header["document"],
                        "title": header["title"],
                        "revision": header["revision"],
                        "effective": header["effective"],
                        "plant": header["plant"],
                        "section": section,
                        "section_title": title,
                    },
                )
            )
    return passages


def load_passages(directory: str) -> list[Passage]:
    passages = []
    for path in sorted(Path(directory).glob("*.md")):
        passages.extend(split_document(path.read_text(encoding="utf-8")))
    return passages
