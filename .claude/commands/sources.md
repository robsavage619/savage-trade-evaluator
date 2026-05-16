---
description: Browse stat-source catalog — what's ingested, what's available, what's blocked.
argument-hint: [optional filter terms]
---

Show the catalog of stat sources we know how to fetch. Use `$ARGUMENTS` for filtering.

If `$ARGUMENTS` is empty or `all`, show everything:

```bash
uv run ste catalog
```

If `$ARGUMENTS` is `ingested`, `available`, or `blocked`, show that status:

```bash
uv run ste catalog --status $ARGUMENTS
```

Otherwise treat `$ARGUMENTS` as a substring search across name / notes / columns:

```bash
uv run ste catalog --search "$ARGUMENTS"
```

Format output as it comes back from the CLI. After the listing, briefly note (1) how many sources are ingested vs available vs blocked overall, and (2) which sources Rob most often asks about (transactions, bWAR, Statcast arsenal, front-office).
