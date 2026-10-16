# svenska-flashcard

Flashcards for the *Rivstart* word lists (Ordlista, engelska). Front: the Swedish entry with its
forms, e.g. `associera med (-r, -de, -t)`. Back: the English meaning, `associate with`. The book
level and chapter are shown top-left on each card.

The app is a PWA (web app) you install on Android from Chrome. It works offline.

## 1. Setup (once)

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Add chapters

```sh
D="/Users/kunaldeoskar/personel/Swedish course"

# One chapter
python scripts/extract_ordlista.py "$D/Rivstart B1B2 Ordlista.pdf" --level B1/B2 --chapters 1

# Several, or a whole book ("1-5", "1,3,7", "all")
python scripts/extract_ordlista.py "$D/Rivstart B1B2 Ordlista.pdf" --level B1/B2 --chapters all
python scripts/extract_ordlista.py "$D/Rivstart A1 A2 Ordlista.pdf" --level A1/A2 --chapters all
```

`docs/cards.json` already contains every chapter of both books. Re-running a chapter replaces only
that chapter's cards. Entries with no English meaning in the PDF are skipped and listed.

## 3. Try it on your computer

```sh
python -m http.server -d docs 8000   # open http://localhost:8000
```

## 4. Put it on your phone

1. Commit and push to GitHub.
2. On GitHub: **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`** → Save
   (the repo must be public on a free account).
3. On your Android phone, open `https://kund17.github.io/svenska-flashcard/` in Chrome.
4. Chrome menu (⋮) → **Add to Home screen / Install app**.

The app saves itself on the phone on the first visit and then works fully offline. After you push
changes, open it once while online; the update appears the time after that.

## Using the app

- Choose the book (A1/A2 or B1/B2) and the chapter.
- Tap the card to flip it. **← Back** / **Next →** move through the chapter.
- **Learnt ✓** hides the word for good (saved on the phone). Tap **"N learnt · reset"** to bring a
  chapter's learnt words back.
- 🔀 shuffles.
