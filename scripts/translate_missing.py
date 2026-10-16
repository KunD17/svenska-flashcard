"""Translate Ordkort words that have no Ordlista meaning, using the DeepL API.

Usage:
    export DEEPL_AUTH_KEY=your-key        # free keys end in ":fx"
    python scripts/translate_missing.py [--missing data/missing.json] [--out data/deepl.json]
    # then re-run extract_ordkort.py for both books to put the translations into the app

Translations are saved in data/deepl.json ({"swedish word": "meaning"}) and never sent
again, so re-running only costs characters for new words. Edit that file by hand to
correct a translation; your edit is kept.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path


def deepl_translate(texts, key):
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    req = urllib.request.Request(
        f"https://{host}/v2/translate",
        data=json.dumps({"text": texts, "source_lang": "SV", "target_lang": "EN-GB"}).encode(),
        headers={"Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return [t["text"] for t in json.load(resp)["translations"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing", default="data/missing.json")
    ap.add_argument("--out", default="data/deepl.json")
    args = ap.parse_args()

    key = os.environ.get("DEEPL_AUTH_KEY")
    if not key:
        sys.exit("Set DEEPL_AUTH_KEY first (free key: https://www.deepl.com/pro-api).")

    out = Path(args.out)
    done = json.loads(out.read_text()) if out.exists() else {}
    todo = list(dict.fromkeys(m["sv"] for m in json.loads(Path(args.missing).read_text())
                              if m["sv"] not in done))
    # "(en) läsk" -> "läsk", "ngt"/"ngn" -> "something"/"someone": cleaner input for DeepL.
    clean = lambda w: re.sub(r"^\((en|ett)\)\s*", "", w).replace("ngt", "något").replace("ngn", "någon")
    for i in range(0, len(todo), 50):  # DeepL takes up to 50 texts per request
        batch = todo[i:i + 50]
        done.update(zip(batch, deepl_translate([clean(w) for w in batch], key)))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(done, ensure_ascii=False, indent=1) + "\n")
    print(f"Translated {len(todo)} words; {len(done)} saved in {out}")


if __name__ == "__main__":
    main()
