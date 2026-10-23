import csv
import re
from functools import cache
from pathlib import Path

from presidio_analyzer import AnalyzerEngine

# Layer 1 entity types from docs/redaction-approval.md. LOCATION is left out on purpose:
# street names are needed for triage and are not personal data on their own.
ENTITIES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS"]
# Low on purpose: an over-scrubbed word costs triage a little; a missed name leaks to an LLM.
SCORE_THRESHOLD = 0.3

_SUFFIXES = (
    "St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Pl|Place|Plz|Plaza|Ter|Terrace|Way|Ct|Court"
    "|Sq|Square|Pkwy|Parkway|Hwy|Ln|Lane|Dr|Drive|Row|Park|Wharf|Cir|Circle"
)
# "245 Elm St", "700-706 Border St", "97 E Brookline St". Intersections have no house number.
ADDRESS = re.compile(rf"\b(\d+)(?:-\d+)?\s+((?:[A-Z][A-Za-z']*\.?\s+){{1,3}}(?:{_SUFFIXES})\b\.?)")


CATEGORIES_CSV = Path("data/categories.csv")


@cache
def _category_words() -> frozenset[str]:
    words = {"district"}
    with CATEGORIES_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            words.update(re.findall(r"[a-z]+", f"{row['legacy_type']} {row['category']}".lower()))
    return frozenset(words)


def _is_category_phrase(span: str) -> bool:
    # Title-case category names ("Missed Trash: District 07", "Illegal Graffiti") look like
    # names to the NER model; a real name almost always has a word outside this vocabulary.
    tokens = re.findall(r"[a-z]+", span.lower())
    return bool(tokens) and all(t in _category_words() for t in tokens)


@cache
def _analyzer() -> AnalyzerEngine:
    # Loads the spaCy model (about 3 s), so only on first use.
    return AnalyzerEngine()


def generalize_address(house_number: int, street: str) -> str:
    if house_number < 100:
        return f"the unit block of {street}"
    return f"the {house_number // 100 * 100} block of {street}"


def scrub(text: str) -> str:
    """Replace personal data with `[REDACTED: <type>]` and house numbers with their block."""
    spans = [
        (m.start(), m.end(), generalize_address(int(m.group(1)), m.group(2).strip()))
        for m in ADDRESS.finditer(text)
    ]
    for result in _analyzer().analyze(
        text, language="en", entities=ENTITIES, score_threshold=SCORE_THRESHOLD
    ):
        if result.entity_type == "PERSON" and _is_category_phrase(text[result.start : result.end]):
            continue
        spans.append((result.start, result.end, f"[REDACTED: {result.entity_type}]"))

    # Earliest first, longest first on ties; a span overlapping an accepted one is dropped.
    accepted: list[tuple[int, int, str]] = []
    for start, end, replacement in sorted(spans, key=lambda s: (s[0], -s[1])):
        if not accepted or start >= accepted[-1][1]:
            accepted.append((start, end, replacement))
    for start, end, replacement in reversed(accepted):
        text = text[:start] + replacement + text[end:]
    return text
