---
name: add-embedder
description: Guide for adding a new embedder adapter to claude-almanac. Use when the user asks to add support for a new embedding provider (e.g. "add Cohere embeddings", "support Jina", "wire up a local embedder"), or when editing files under `src/claude_almanac/embedders/`.
---

# add-embedder

Embedders are pluggable via a strict protocol. Adding one is a 4-step mechanical process with one non-mechanical step: the calibration.

## Protocol contract

`src/claude_almanac/embedders/base.py` defines:

```python
class Embedder(Protocol):
    name: str                                # PROVIDER string — "ollama", "openai", "voyage", "<new>"
    dim: int                                 # vector dimension; must match live output
    distance: Literal["l2", "cosine"]        # sqlite-vec metric
    model: str                               # optional but conventional; stored per-DB
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

The adapter exposes `name` as the provider *family*, not the model. The model name is stored alongside the provider in the DB `meta` row. Changing either after index creation forces re-index.

## Steps

1. **Adapter file** — `src/claude_almanac/embedders/<provider>.py`. Use `httpx` for REST providers; use the vendor SDK when one exists. Handle timeouts (5s connect, 30s read), explicit 401/429 exceptions with clear error text, and dim-mismatch detection (compare `len(result[0])` to declared `dim`).
2. **Factory registration** — edit `embedders/__init__.py` to add a branch in `make_embedder(provider, model)`. Import lazily (`from . import <provider>` inside the branch) so optional vendor deps stay optional.
3. **Profile** — add a `(provider, model) -> EmbedderProfile` entry in `embedders/profiles.py`. Fields: `name` ("{provider}:{model}"), `dim`, `distance`, `dedup_distance`.
4. **Calibration (non-mechanical)** — run the harness against the shared fixture corpus before merging:

   ```bash
   source .venv/bin/activate
   claude-almanac calibrate <provider> <model> tests/fixtures/calibration_corpus.jsonl
   ```

   Run `claude-almanac calibrate <provider> <model> <fixture.jsonl>` to derive a
   dedup_distance threshold. Commit the resulting value to
   `src/claude_almanac/embedders/profiles.py` as the new `EmbedderProfile` entry.

   The harness emits a distance histogram and suggests a `dedup_distance` at max × 1.2 of observed duplicate-pair distances. Paste the histogram + the suggested threshold into the PR description. Profiles without a measured threshold are not mergeable — a guessed threshold produces silent dedup misbehavior.

## Threshold reasoning

- L2 embedders (typically Ollama local models like `bge-m3`) have unnormalized distance spaces; thresholds are model-specific and can sit anywhere in the 5–50 range. `bge-m3`'s measured threshold is 17.0.
- Cosine embedders (typically OpenAI/Voyage) have distance ∈ [0, 2]; thresholds usually cluster around 0.25–0.45.
- Never copy a threshold across providers — the distance spaces differ. If you're in doubt, run calibration twice (once on a clean corpus, once on a noisy one) and take the more conservative value.
- The `embedder-calibrator` agent in `.claude/agents/` automates the run + histogram + threshold recommendation.

## Tests + docs

- Unit test: `tests/unit/test_embedders_<provider>.py`. Mock HTTP via `respx` (for httpx) or `unittest.mock.patch` for SDKs. Cover happy path, auth error, rate limit (429), dim mismatch.
- Integration test (optional but encouraged): `tests/integration/test_embedders_<provider>_live.py`, `@pytest.mark.integration`, skipped when the API key env var is unset.
- Update `docs/config.md` profile table and `docs/install.md` install section.
- Add optional extra to `pyproject.toml`: `[project.optional-dependencies].<provider>`.
