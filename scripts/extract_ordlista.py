"""Turn a Rivstart "Ordlista (engelska)" PDF into flashcards for the app.

Usage:
    python scripts/extract_ordlista.py PDF_PATH --level B1/B2 [--chapters 1] [--out docs/cards.json]

--chapters takes "1", "1-5", "1,3,7" or "all" (default: all). Chapters already in the
output file for the same level are replaced; everything else is kept, so you can add
chapters and books one run at a time.

Output format (compact, to keep the app light):
    {"B1/B2": {"Ordlista": {"1": [["associera med (-r, -de, -t)", "associate with"], ...], ...}}, ...}
Chapter keys are the chapter number, or a section name such as "Klassrum".

In these PDFs the Swedish entry is set in 9pt regular type and the English
meaning in 8.5pt bold, which is how the two halves of a line are told apart.
"""
import argparse
import json
import re
from pathlib import Path

import pymupdf

SV_SIZE, EN_SIZE, SECTION_SIZE = 9.0, 8.5, 18.0
INDENT = 4  # points; wrapped lines are indented relative to their column

# Typesetting slips in the PDFs, where part of the Swedish is set in the English style:
# (swedish, english) as extracted -> as it should be.
FIXES = {
    ("kryssa för (-r, -de, -t)", "för tick, cross"): ("kryssa för (-r, -de, -t)", "tick, cross"),
    ("sluta (-r, -de, -t)", "på end with"): ("sluta (-r, -de, -t) på", "end with"),
    ("göra (gör, gjorde, gjort)", "slut break up"): ("göra (gör, gjorde, gjort) slut", "break up"),
    ("skriva (-er, skrev, skrivit)", "sign up"): ("skriva (-er, skrev, skrivit) upp sig", "sign up"),
}


def parse_chapters(spec):
    if spec == "all":
        return None
    out = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.update(str(n) for n in range(int(a), int(b or a) + 1))
    return out


def section_key(text):
    """'KAPITEL 1 CHAPTER 1' -> '1'; 'KLASSRUM' -> 'Klassrum'."""
    m = re.match(r"KAPITEL\s+(\d+)", text, re.IGNORECASE)
    return m.group(1) if m else text.strip().capitalize()


def page_lines(page):
    """Yield (line, indented) in reading order: left column top-to-bottom, then right."""
    mid = page.rect.width / 2
    lines = [l for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])]
    lines.sort(key=lambda l: (l["bbox"][0] >= mid, l["bbox"][1]))
    lefts = {}
    for l in lines:
        col = l["bbox"][0] >= mid
        lefts[col] = min(lefts.get(col, l["bbox"][0]), l["bbox"][0])
    for l in lines:
        yield l, l["bbox"][0] - lefts[l["bbox"][0] >= mid] > INDENT


def line_pairs(spans):
    """Split a line's spans into (sv, en) pairs. A Swedish span that follows an
    English one starts a new pair (the PDF occasionally puts two entries on one line)."""
    pairs = []
    for s in spans:
        size, text = round(s["size"], 1), s["text"]
        if not text.strip():
            # Whitespace can carry either font; it never marks a boundary.
            if pairs:
                pairs[-1][1 if pairs[-1][1] else 0] += text
            continue
        if size == SV_SIZE:
            if not pairs or pairs[-1][1]:
                pairs.append(["", ""])
            pairs[-1][0] += text
        elif size == EN_SIZE:
            if not pairs:
                pairs.append(["", ""])
            pairs[-1][1] += text
    return [(sv.strip(), en.strip()) for sv, en in pairs if (sv + en).strip()]


def extract(pdf_path):
    """Return {chapter_key: [[sv, en], ...]} in book order."""
    chapters, section = {}, None
    for page in pymupdf.open(pdf_path):
        for line, indented in page_lines(page):
            spans = line["spans"]
            if any(round(s["size"], 1) == SECTION_SIZE for s in spans):
                section = section_key("".join(s["text"] for s in spans))
                chapters.setdefault(section, [])
                continue
            if section is None:
                continue
            cards = chapters[section]
            for sv, en in line_pairs(spans):
                prev = cards[-1] if cards else None
                if not sv:
                    # The English meaning wrapped onto a second line.
                    if prev:
                        prev[1] = f"{prev[1]} {en}".strip()
                elif prev and not prev[1] and (indented or prev[0].count("(") > prev[0].count(")")):
                    # The Swedish entry wrapped onto a second line.
                    prev[0] = f"{prev[0]} {sv}"
                    prev[1] = en
                else:
                    cards.append([sv, en])
    for cards in chapters.values():
        for c in cards:
            c[0] = re.sub(r"\s+", " ", c[0]).lstrip("/ ")
            c[1] = re.sub(r"\s+", " ", c[1])
            # A few meanings aren't bolded in the PDF: "stat (-en, -er, -erna) state".
            m = re.match(r"^(.*\))\s+([^()]+)$", c[0])
            if not c[1] and m:
                c[0], c[1] = m.group(1), m.group(2)
            c[0], c[1] = FIXES.get((c[0], c[1]), (c[0], c[1]))
    return chapters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--level", required=True, help='Shown on the card, e.g. "B1/B2" or "A1/A2"')
    ap.add_argument("--chapters", default="all")
    ap.add_argument("--out", default="docs/cards.json")
    args = ap.parse_args()

    wanted = parse_chapters(args.chapters)
    new = {k: v for k, v in extract(args.pdf).items() if wanted is None or k in wanted}

    out = Path(args.out)
    deck = json.loads(out.read_text()) if out.exists() else {}
    level = deck.setdefault(args.level, {}).setdefault("Ordlista", {})
    for key, cards in new.items():
        missing = [sv for sv, en in cards if not en]
        level[key] = [c for c in cards if c[1]]
        print(f"{args.level} {key}: {len(level[key])} cards")
        if missing:
            print(f"  skipped (no English in the PDF): {missing}")
    # Keep chapters in book order: named sections first, then by number.
    deck[args.level]["Ordlista"] = dict(sorted(level.items(), key=lambda kv: (kv[0].isdigit(), int(kv[0]) if kv[0].isdigit() else 0)))
    out.write_text(json.dumps(dict(sorted(deck.items())), ensure_ascii=False, separators=(",", ":")))
    total = sum(len(c) for lv in deck.values() for c in lv.get("Ordlista", {}).values())
    print(f"{total} Ordlista cards total in {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
