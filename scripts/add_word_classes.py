"""Work out each card's word class (noun, verb, adjective, ...) for the app.

Usage:
    python scripts/add_word_classes.py [--cards docs/cards.json] [--out docs/classes.json]

Run it after the extract scripts. Word classes come from Folkets lexikon
(https://folkets-lexikon.csc.kth.se/folkets/, CC BY-SA 2.5), which is downloaded to
data/folkets_sv_en_public.xml on the first run. For each card, in order of preference:
  1. a "class" set by hand in data/overrides.json;
  2. the lexikon entry for the card's word (for Ordkort, its Ordlista entry: "går" -> "gå"),
     using the card's forms, then its English meaning, to choose when the word has several
     classes ("vad (-en, ...)" is the noun "calf", "med" = "with" the preposition);
  3. the forms alone: "(-t, -a)" is an adjective, "en/ett ..." a noun, and so on.
Phrases and words that still have no class get no label.

Output: {"noun": [swedish card text, ...], "verb": [...], ...}
"""
import argparse
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

LEXIKON_URL = "https://folkets-lexikon.csc.kth.se/folkets/folkets_sv_en_public.xml"
# Lexikon class codes (and SALDO codes, used when an entry has no class) -> label on the card.
LABELS = {"nn": "noun", "vb": "verb", "jj": "adjective", "av": "adjective", "ab": "adverb",
          "pp": "preposition", "pn": "pronoun", "hp": "pronoun", "ps": "pronoun",
          "kn": "conjunction", "sn": "conjunction", "in": "interjection", "rg": "numeral",
          "ro": "numeral", "ie": "infinitive marker", "article": "article", "pm": "proper noun"}
# When the meaning doesn't settle it either, small words win: "vad" is "what" before "calf".
NO_FORMS_ORDER = ["pronoun", "preposition", "adverb", "conjunction", "interjection", "numeral",
                  "infinitive marker", "article", "adjective", "verb", "noun", "proper noun"]


def load_lexikon(path):
    """word or inflected form -> {label: set of English translations}. Headwords and
    inflections are kept apart, so "är" (a form of "vara") doesn't hide behind a headword."""
    if not path.exists():
        print(f"downloading Folkets lexikon to {path} ...")
        urllib.request.urlretrieve(LEXIKON_URL, path)
    heads, forms = {}, {}
    for word in ET.parse(path).getroot().iter("word"):
        value = (word.get("value") or "").lower().strip()
        code = word.get("class") or ""
        if not code:  # e.g. <see type="saldo" value="bege sig||bege_sig..1||bege_sig..vbm.1">
            saldo = [s.get("value", "") for s in word.iter("see") if s.get("type") == "saldo"]
            m = re.search(r"\.\.([a-z]{2})m?\.\d", " ".join(saldo))
            code = m.group(1) if m else ""
        label = LABELS.get(code)
        if not value or not label:
            continue
        meanings = {meaning(t.get("value", "")) for t in word.findall("translation")}
        heads.setdefault(value, {}).setdefault(label, set()).update(meanings)
        for inf in word.iter("inflection"):
            forms.setdefault((inf.get("value") or "").lower().strip(), {}).setdefault(label, set()).update(meanings)
    return heads, forms


def meaning(text):
    """Comparable English: "to have a cold" ~ "have a cold", "(the) book" ~ "book"."""
    text = re.sub(r"\([^)]*\)", " ", text.lower())
    text = re.sub(r"^\s*(to|a|an|the)\s+", "", text)
    return re.sub(r"\s+", " ", text).strip(" .!?")


def by_meaning(en, found):
    """The one class whose lexikon translations match the card's meaning best, or None."""
    parts = {meaning(p) for p in re.split(r"[,;/]", en)} - {""}
    words = {w for p in parts for w in p.split()}
    scores = {label: (len(parts & ts), len(words & {w for t in ts for w in t.split()}))
              for label, ts in found.items()}
    best = max(scores.values())
    winners = [label for label, sc in scores.items() if sc == best]
    return winners[0] if best > (0, 0) and len(winners) == 1 else None


def split(entry):
    """"att fråga (-r, -de, -t)" -> ("fråga", ["-r", "-de", "-t"]); article/att dropped."""
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*(.*)$", entry)
    head, forms = (f"{m.group(1)} {m.group(3)}", [f.strip() for f in m.group(2).split(",")]) if m else (entry, [])
    head = re.sub(r"^(en|ett|att)\s+", "", head.lower()).strip(" .!?")
    return re.sub(r"\s+", " ", head), forms


def from_forms(word, forms):
    """Word class from the forms alone, or None."""
    if re.match(r"^(en|ett)\s", word):
        return "noun"
    if len(forms) == 2:
        return "adjective"                 # förkyld (-t, -a)
    if len(forms) >= 3:
        # Verbs: present tense first, "-r", "-er", "kan", "går"; nouns: definite "-en", "kapitlet".
        return "verb" if re.search(r"(^-?e?r$|r$|^kan$|^vill$|^ska$|^bör$)", forms[0]) else "noun"
    if len(forms) == 1:
        return "noun"                      # svenska (-n)
    return None


def word_class(sv, en, ref, heads, forms_index):
    entry = ref or sv  # Ordkort: the Ordlista entry has the infinitive and the forms
    head, forms = split(entry)
    guess = from_forms(sv, forms) or from_forms(entry, forms)
    found = heads.get(head) or heads.get(split(sv)[0]) or forms_index.get(split(sv)[0]) or {}
    if guess and (guess in found or not found):
        return guess
    if len(found) == 1:
        return next(iter(found))
    if found and not forms:
        return by_meaning(en, found) or next(c for c in NO_FORMS_ORDER if c in found)
    return guess  # forms and lexikon disagree: trust the book


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", default="docs/cards.json")
    ap.add_argument("--out", default="docs/classes.json")
    ap.add_argument("--lexikon", default="data/folkets_sv_en_public.xml")
    ap.add_argument("--overrides", default="data/overrides.json")
    args = ap.parse_args()

    heads, forms_index = load_lexikon(Path(args.lexikon))
    overrides_path = Path(args.overrides)
    overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}

    classes, unknown, total = {}, [], 0
    for lists in json.loads(Path(args.cards).read_text()).values():
        for chapters in lists.values():
            for cards in chapters.values():
                for sv, en, *rest in cards:
                    total += 1
                    label = overrides.get(sv, {}).get("class") or word_class(sv, en, rest[0] if rest else "", heads, forms_index)
                    if label:
                        classes.setdefault(label, set()).add(sv)
                    else:
                        unknown.append(sv)
    out = Path(args.out)
    out.write_text(json.dumps({k: sorted(v) for k, v in sorted(classes.items())}, ensure_ascii=False, separators=(",", ":")))
    labelled = total - len(unknown)
    print(f"{labelled} of {total} cards have a word class ({out}, {out.stat().st_size // 1024} KB): "
          + ", ".join(f"{k} {len(v)}" for k, v in sorted(classes.items(), key=lambda kv: -len(kv[1]))))
    print(f"no class ({len(unknown)}), mostly phrases, e.g.: {unknown[:15]}")


if __name__ == "__main__":
    main()
