# Backend tests

The default `pytest backend/` run is **fast** — it never imports BabelDOC,
never invokes MinerU, never reaches out to any LLM provider. All heavy
integration scenarios are gated behind explicit `pytest` markers so they
only run when you opt in.

## Default run

```
pytest backend/ -x -q
```

Runs every unit test (~280 tests at time of writing). Should complete in
under a minute on a modern laptop. CI uses this command.

## Marker-gated integration tests

| Marker | Path | What it exercises | Cost |
|---|---|---|---|
| `babeldoc` | `backend/tests/integration/test_babeldoc_real_run.py` | Loads real `babeldoc==0.6.2`, runs `init()` + `async_warmup()` + a one-page translation against a synthetic PDF with an identity translator. | First run: ~2–5 min (downloads ~80 MB to `~/.cache/babeldoc/`). Subsequent runs: a few seconds. |
| `mineru` | (tests that depend on the MinerU CLI) | Real MinerU subprocess against a fixture PDF. | Requires `mineru` on PATH; ~30 s per run. |

Run a single marker:

```
pytest -m babeldoc backend/tests/integration/ -x -q
pytest -m mineru backend/ -x -q
```

Combine markers with `or`:

```
pytest -m "babeldoc or mineru" backend/ -x -q
```

## Adding a new integration scenario

1. Register the marker in `pyproject.toml`
   (`[tool.pytest.ini_options].markers`) so unregistered markers don't
   trip pytest's strict mode.
2. Place the test under `backend/tests/integration/`.
3. Apply the marker at module level via
   `pytestmark = pytest.mark.<name>` so the whole file is skipped by
   default.
4. Document the new marker in the table above (what it exercises +
   approximate cost).

## Why the gating?

These tests would fail or be flaky in CI without specific local state:

- `babeldoc`: requires network for first-run asset download, ~80 MB of
  disk, and a Python build that supports `hyperscan` (no native ARM
  wheels for Apple Silicon).
- `mineru`: requires the MinerU CLI to be installed and on PATH; the CI
  image doesn't ship it.

Local development and pre-release checks gate on them; the default `pytest
backend/` run does not.
