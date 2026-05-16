---
description: Run the full Rob-conventions check stack (ruff format + check, pyright, pytest).
---

Run the project's standard quality gates in order. Stop and report on the first failure.

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run pyright src/ tests/
uv run pytest
```

Report each step's outcome (pass / fail with the diagnostic line). If everything passes, end with `✅ all clean`.
