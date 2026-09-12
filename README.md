# Duo Semantle

A daily word-guessing game inspired by [Semantle](https://semantle.com/), with a twist: every guess is scored against **two** hidden target words at once, using semantic similarity from pretrained word embeddings.

## How it works

Each day, two semantically dissimilar target words are chosen automatically. Players submit guesses; each guess is scored against both targets using cosine similarity between fastText word embeddings. The game ends for the day once both targets have been found.

## Architecture

The system is built as a set of independent, single-purpose AWS Lambda functions, each backing its own API Gateway route, all provisioned as infrastructure-as-code via AWS CDK (TypeScript).

| Slice | What it does | Key AWS services |
|---|---|---|
| **Word validation** | Checks whether a guess is a real English word | Lambda, S3, API Gateway |
| **Similarity scoring** | Computes cosine similarity between two words' embeddings | Lambda, S3, API Gateway, Lambda Layer (numpy) |
| **Daily target selection** | Picks two dissimilar target words each day, avoiding repeats from the last 30 days | Lambda, S3, DynamoDB, EventBridge (scheduled) |
| **Rank-among-vocabulary** | Computes each target's similarity against the full ~228K-word vocabulary, stores the top 1000 closest words | Same Lambda as target selection |
| **Guess & session history** | Validates + scores a guess against both targets in one call, persists per-session guess history | Lambda, DynamoDB, shared Lambda Layer |
| **Frontend hosting** | Serves the game UI | S3, CloudFront |

### Data pipeline

- **Word list**: derived from [ESDB/SCOWL](https://github.com/en-wl/wordlist), filtered to exclude proper nouns, abbreviations, multi-word phrases, and non-ASCII entries ? ~270K validated English words.
- **Embeddings**: generated from Facebook's pretrained `cc.en.300.bin` fastText model, restricted to the validated word list only (not the full multi-million-word model) to keep Lambda cold starts fast. Partitioned by two-letter prefix so each request only loads the ~1-2 files it actually needs.
- **Target pool**: the validated word list intersected with a word-frequency corpus (Peter Norvig's Google Trillion Word Corpus list), minus stop words, to ensure daily targets are common enough to be guessable.

### Design decisions worth noting

- **Shared logic, not duplicated logic**: validation and scoring logic live in a shared Lambda Layer, imported by multiple functions, rather than being copy-pasted or called via Lambda-to-Lambda invocation (an anti-pattern that adds latency and coupling).
- **Precomputed, not shipped raw**: the original fastText model is 2.6GB; only word-specific precomputed vectors for the validated word list are shipped to Lambda (~240MB total, lazily loaded by prefix partition).
- **Client-side rank display**: the top-1000 rank table for each day's targets is computed once (server-side) and sent to the client, so per-guess "how close am I" lookups happen instantly in the browser rather than requiring a server round-trip.

## Repo structure
app/ Local prototyping: word validation, embedding generation, scoring logic, game orchestration
infra/ AWS CDK stack: Lambda functions, DynamoDB tables, API Gateway, EventBridge schedule, CloudFront frontend
## Local development

See `app/` for the local prototyping scripts used to build and validate word lists, generate embeddings, and test scoring logic before deployment.

## Infrastructure

See `infra/` for the full CDK stack definition (`infra/lib/duo-semantle-infra-stack.ts`). Deploy with:

```bash
cd infra
npm install
npx cdk deploy
```

## Data sources

- Word list: [en-wl/wordlist (ESDB/SCOWL)](https://github.com/en-wl/wordlist)
- Word embeddings: [fastText pretrained vectors](https://fasttext.cc/docs/en/crawl-vectors.html) (`cc.en.300.bin`)
- Word frequency: [Peter Norvig's Google Trillion Word Corpus list](https://norvig.com/ngrams/)
