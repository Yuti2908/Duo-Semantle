# Duo Semantle

The local engine accepts an English-word guess and returns either `invalid English
word` or a deterministic semantic score (0–1000) against the selected daily
target.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

Populate `data/dictionary/english_words.txt` with a complete licensed English
word list before production use. Put the common embedding archive at
`data/embeddings/common_vectors.npz`; it must contain aligned `words` and
`vectors` NumPy arrays. Configure a FastText model through `FastTextFallback`
to generate vectors for valid words missing from that archive.

FastText is optional for the base engine. On Windows, use 64-bit CPython 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-fasttext.txt
```

PyPI supplies a prebuilt Windows wheel for CPython 3.12. Python 3.14 has no
compatible prebuilt wheel and attempts a native C++ build instead.

AWS remains intentionally outside this phase. `DailyTargetRepository` is the
single persistence boundary to replace when targets move to a managed store.

## Local game and compact embedding cache

With a FastText `.bin` model at `data/embeddings/fasttext-en.bin`, create local
two-letter cache partitions for common words:

```powershell
python -m scripts.build_embedding_dataset --fasttext-bin data/embeddings/fasttext-en.bin
```

This produces files such as `el.bin` for `elephant`. Missing valid words still
receive a vector through FastText. The configured two daily targets are
`respect` and `coral` in `data/daily_targets.json`.

Start the local UI with the Python 3.12 environment:

```powershell
python app.py
```

Then open http://127.0.0.1:8000 and enter a guess. It returns a deterministic
score for each target.
