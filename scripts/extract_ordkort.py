"""Turn a Rivstart "Ordkort" PDF into flashcards, taking meanings from the Ordlista.

Usage:
    python scripts/extract_ordkort.py PDF_PATH --level A1/A2 [--out docs/cards.json]

Run extract_ordlista.py for both books first: meanings are looked up in the Ordlista
cards already in the output file. For each word card, in order of preference:
  1. an Ordlista entry with the same word (same chapter, then same book, then other book),
     ignoring articles ("ett barn" ~ "barn (-et, -, -en)") and grammar forms;
  2. the same, after turning a present-tense verb into its infinitive ("pluggar" -> "plugga");
  3. a DeepL translation saved in data/deepl.json (see translate_missing.py).
Words with no meaning yet are left out of the app and listed in data/missing.json.

Output: cards.json[level]["Ordkort"][chapter] = [[word, meaning, ordlista_entry], ...]
(ordlista_entry is "" when the meaning came from DeepL).
"""
import argparse
import json
import re
from pathlib import Path

import pymupdf

HEADING_SIZE = 22.0
# Irregular present tense -> infinitive.
IRREGULAR = {"är": "vara", "gör": "göra", "vet": "veta", "kan": "kunna", "vill": "vilja",
             "ska": "skola", "ser": "se", "ber": "be", "dör": "dö", "tar": "ta", "får": "få",
             "har": "ha", "blir": "bli", "ler": "le"}


def norm(s):
    """Comparable form: lowercase, no (forms)/(article), no leading en/ett."""
    s = re.sub(r"\([^)]*\)", " ", s.lower())
    s = re.sub(r"^\s*(en|ett)\s+", "", s)
    s = re.sub(r"[^\w\-\s./]", " ", s)
    s = re.sub(r"\b(ngt|ngn|ngns)\b", " ", s)  # "ägna sig åt ngt" ~ "ägna sig åt"
    return re.sub(r"\s+", " ", s).strip()


def infinitives(word):
    """Possible infinitives of a present-tense verb phrase: 'lägger sig' -> ['lägga sig', ...]."""
    first, _, rest = word.partition(" ")
    out = []
    if first in IRREGULAR:
        out.append(IRREGULAR[first])
    if first.endswith(("er", "ar")):
        out.append(first[:-2] + "a")   # pratar -> prata, dricker -> dricka
    if first.endswith("r"):
        out.append(first + "a")        # kör -> köra
        out.append(first[:-1])         # går -> gå, bor -> bo
    if first.endswith("s") and not first.endswith("as"):
        out.append(first[:-1] + "as")  # trivs -> trivas, finns -> finnas
    return [f"{c} {rest}".strip() for c in out]


def extract_words(pdf_path):
    """Return {chapter: [word, ...]} in page order."""
    chapters, chapter = {}, None
    for page in pymupdf.open(pdf_path):
        for block in page.get_text("dict")["blocks"]:
            cells = []  # each line is one card; a card whose text wraps continues below
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if "Acumin" in s["font"]]
                text = "".join(s["text"] for s in spans).strip()
                if not text:
                    continue
                if any(round(s["size"], 1) == HEADING_SIZE for s in spans):
                    if text.startswith("Kapitel"):
                        chapter = text.split()[1]
                        chapters.setdefault(chapter, [])
                    continue
                if chapter is None or max(round(s["size"], 1) for s in spans) < 10:
                    continue  # header/footer
                # Card text is centred, so compare line centres, not left edges.
                x0, y0 = (line["bbox"][0] + line["bbox"][2]) / 2, line["bbox"][1]
                above = next((c for c in cells if abs(c["x"] - x0) < 40 and 0 < y0 - c["y"] < 40), None)
                if above:  # wrapped card text, e.g. "en trädgårdsmäs-" + "tare"
                    above["text"] = above["text"][:-1] + text if above["text"].endswith("-") else f"{above['text']} {text}"
                    above["y"] = y0
                else:
                    cells.append({"x": x0, "y": y0, "text": text})
            if chapter:
                chapters[chapter] += [c["text"] for c in cells]
    return chapters


def build_index(deck):
    """norm(ordlista entry) -> [(level, chapter, meaning, entry), ...]"""
    index = {}
    for level, lists in deck.items():
        for chapter, entries in lists.get("Ordlista", {}).items():
            for sv, en in entries:
                index.setdefault(norm(sv), []).append((level, chapter, en, sv))
    return index


def lookup(word, level, chapter, index):
    for key in [norm(word)] + infinitives(norm(word)):
        hits = index.get(key)
        if hits:
            best = min(hits, key=lambda h: (h[0] != level, h[1] != chapter))
            return best[2], best[3]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--level", required=True, help='e.g. "A1/A2" or "B1/B2"')
    ap.add_argument("--out", default="docs/cards.json")
    ap.add_argument("--deepl", default="data/deepl.json")
    ap.add_argument("--missing", default="data/missing.json")
    args = ap.parse_args()

    out = Path(args.out)
    deck = json.loads(out.read_text())
    index = build_index(deck)
    deepl_path = Path(args.deepl)
    deepl = json.loads(deepl_path.read_text()) if deepl_path.exists() else {}

    result, missing, stats = {}, [], {"ordlista": 0, "deepl": 0, "missing": 0}
    for chapter, words in extract_words(args.pdf).items():
        cards = []
        for word in dict.fromkeys(words):  # drop duplicates within a chapter, keep order
            hit = lookup(word, args.level, chapter, index)
            if hit:
                cards.append([word, hit[0], hit[1]])
                stats["ordlista"] += 1
            elif word in deepl:
                cards.append([word, deepl[word], ""])
                stats["deepl"] += 1
            else:
                missing.append({"level": args.level, "chapter": chapter, "sv": word})
                stats["missing"] += 1
        result[chapter] = cards
    deck.setdefault(args.level, {})["Ordkort"] = dict(sorted(result.items(), key=lambda kv: int(kv[0])))
    out.write_text(json.dumps(dict(sorted(deck.items())), ensure_ascii=False, separators=(",", ":")))

    # Keep the other book's missing words; replace this book's.
    missing_path = Path(args.missing)
    old = json.loads(missing_path.read_text()) if missing_path.exists() else []
    missing = [m for m in old if m["level"] != args.level] + missing
    missing_path.parent.mkdir(parents=True, exist_ok=True)
    missing_path.write_text(json.dumps(missing, ensure_ascii=False, indent=1) + "\n")

    print(f"{args.level} Ordkort: {sum(map(len, result.values()))} cards in {len(result)} chapters "
          f"(meaning from Ordlista: {stats['ordlista']}, DeepL: {stats['deepl']}, no meaning yet: {stats['missing']})")
    if stats["missing"]:
        print(f"  words without a meaning are listed in {missing_path}")


if __name__ == "__main__":
    main()
