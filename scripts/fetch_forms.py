"""Look up the forms of Ordkort words that have no Ordlista entry, for the back of the card.

Usage:
    python scripts/fetch_forms.py [--cards docs/cards.json] [--out data/forms.json]

Most Ordkort cards repeat their Ordlista entry on the back, e.g. "skafferi (-et, -er, -erna)".
Words whose meaning came from DeepL have no entry, so this asks Språkbanken's SALDO
(https://spraakbanken.gu.se/en/resources/saldo, CC BY 4.0) for their inflections and writes
them in the same style: "ett avtryck" -> "avtryck (-et, –, -en)", "spottar" -> "spotta (-r, -de, -t)".
Results are saved in data/forms.json ({"ordkort word": "entry"}; edit by hand to fix any) and
never looked up again. Re-run extract_ordkort.py afterwards. Words SALDO doesn't know, and phrases
that don't start with a verb ("i ögonvrån"), are left out and keep just the word on the back.
"""
import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

SALDO = "https://demo.spraakbanken.gu.se/ws/saldo-ws"
# The forms shown in brackets, as in the Rivstart Ordlista, by word class.
SLOTS = {
    "nn": [["sg def nom"], ["pl indef nom"], ["pl def nom"]],
    "vb": [["pres ind aktiv", "pres ind s-form"], ["pret ind aktiv", "pret ind s-form"],
           ["sup aktiv", "sup s-form"]],
    "av": [["pos indef sg n nom"], ["pos indef pl nom"]],
}


def get(path):
    with urllib.request.urlopen(f"{SALDO}/{path}", timeout=30) as resp:
        return json.loads(resp.read())


def short(form, base):
    """Rivstart style: "-et" after the whole word, "-or" after the stem (sida -> sidor), "–" for no
    change, else the whole form (kapitlet, skrev, skrivit)."""
    if form == base:
        return "–"
    if form.startswith(base):
        return "-" + form[len(base):]
    if base[-1] in "ae" and form.startswith(base[:-1]) and form[len(base) - 1] != "i":
        return "-" + form[len(base) - 1:]
    return form


def forms_of(word):
    """Entry for one Ordkort word, or None."""
    noun = bool(re.match(r"^(en|ett)\s", word))
    words = re.sub(r"^\(?(en|ett)\)?\s+", "", word).split()
    first, rest = words[0], re.sub(r"[()]", "", " ".join(words[1:]))  # "smyga sig (på ngn)"
    if noun and rest:
        return None  # "en magisk formel": a phrase, not a single noun
    hits = [h for h in get(f"fl/json/{urllib.parse.quote(first)}") if h["l"].split("..")[1][:-2] in SLOTS]
    if noun:
        hits = [h for h in hits if h["l"].split("..")[1].startswith("nn")]
    # The word itself is a headword ("snarare"), or a present tense of a verb ("spottar" -> "spotta").
    exact = [h for h in hits if h["gf"] == first]
    verbs = [h for h in hits if h["l"].split("..")[1] == "vb.1" and first.endswith(("r", "s"))]
    hit = (exact or verbs or [None])[0]
    if not hit or (rest and not hit["l"].split("..")[1].startswith("vb")):
        return None  # phrases only get forms when they start with a verb: "visa sig (-r, -de, -t)"
    pos, base = hit["l"].split("..")[1][:2], hit["gf"]
    table = get(f"gen/json/{urllib.parse.quote(hit['p'])}/{urllib.parse.quote(base)}")
    shown = []
    for msds in SLOTS[pos]:
        found = next(([t["form"] for t in table if t["msd"] == m] for m in msds
                      if any(t["msd"] == m for t in table)), [])
        # The first form is the standard one: "säger", not the spoken "säjer".
        shown.append(short(found[0], base) if found else "")
    while shown and not shown[-1]:
        shown.pop()  # no plural: "kvällsmat (-en)"
    head = f"{base} {rest}".strip()
    if all(s in ("–", "") for s in shown):
        return head  # no forms (nuvarande) or none that differ
    return f"{head} ({', '.join(s or '–' for s in shown)})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", default="docs/cards.json")
    ap.add_argument("--out", default="data/forms.json")
    args = ap.parse_args()

    out = Path(args.out)
    done = json.loads(out.read_text()) if out.exists() else {}
    deck = json.loads(Path(args.cards).read_text())
    todo = list(dict.fromkeys(sv for lists in deck.values() for cards in lists.get("Ordkort", {}).values()
                              for sv, en, ref in cards if not ref and sv not in done))
    print(f"looking up {len(todo)} words in SALDO ...")
    found = 0
    for k, word in enumerate(todo, 1):
        try:
            entry = forms_of(word)
        except Exception as e:  # network trouble: keep what we have, retry next run
            print(f"  {word}: {e}")
            continue
        if entry:
            done[word] = entry
            found += 1
        if k % 25 == 0:
            out.write_text(json.dumps(done, ensure_ascii=False, indent=1) + "\n")
        time.sleep(0.1)  # be gentle with a free service
    out.write_text(json.dumps(done, ensure_ascii=False, indent=1) + "\n")
    print(f"forms found for {found} of {len(todo)} words, saved in {out}; now re-run extract_ordkort.py")


if __name__ == "__main__":
    main()
