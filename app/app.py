"""Minimal local Duo-Semantle UI. Run with: python app.py"""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.embeddings import FallbackEmbeddingProvider, FastTextFallback, PrefixEmbeddingStore
from src.game import DailyTargetRepository, DuoSemantleGame
from src.validator import WordValidator
from src.embeddings import PrefixEmbeddingStore

ROOT = Path(__file__).parent
TARGETS = json.loads((ROOT / "data/daily_targets.json").read_text(encoding="utf-8"))["targets"]
validator = WordValidator(ROOT / "data/dictionary/words_full.txt")

embeddings = PrefixEmbeddingStore(ROOT / "data/embeddings")
games = {}
for target in TARGETS:
    game = DuoSemantleGame(validator, embeddings, DailyTargetRepository({}))
    game.start(target)
    games[target] = game


def page(guess: str, results: list[str]) -> bytes:
    result_html = "".join(results) or "<p class='hint'>Enter a valid English word to score it against both daily targets.</p>"
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Duo Semantle</title>
<style>body{{font-family:system-ui;max-width:680px;margin:4rem auto;padding:0 1rem;background:#f5f8f7;color:#1b2724}} input{{font-size:1.1rem;padding:.65rem;width:60%}}button{{padding:.7rem 1rem;background:#19745f;color:white;border:0;border-radius:4px}}.card{{background:white;margin:1rem 0;padding:1rem;border-radius:8px}}.score{{font-size:1.8rem;font-weight:700}}</style>
</head><body><h1>Duo Semantle</h1><p>Today has two targets. Your guess is scored against each one.</p>
<form><input name='guess' autofocus value='{html.escape(guess)}' placeholder='Enter a word'><button>Guess</button></form>{result_html}</body></html>""".encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        guess = parse_qs(urlparse(self.path).query).get("guess", [""])[0]
        results = []
        if guess.strip():
            for target, game in games.items():
                result = game.guess(guess)
                if not result.valid:
                    results.append(f"<div class='card'><strong>{html.escape(result.word or guess)}</strong>: {html.escape(result.reason or 'invalid')}</div>")
                    break
                results.append(f"<div class='card'><strong>Target: {html.escape(target)}</strong><div class='score'>{result.score}</div><small>cosine {result.similarity:.4f}</small></div>")
        body = page(guess, results)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Duo Semantle is running at http://127.0.0.1:8000")
    server.serve_forever()
