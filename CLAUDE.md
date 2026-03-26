# CLAUDE.md

This project uses `AGENTS.md` instead of a `CLAUDE.md` file.

Please see @AGENTS.md in this same directory and treat its content as the primary reference for this project.

## Lint Checklist

Before considering any work done, run **all four** of these — both `check` and `format --check` are required:

```bash
uv run --directory mcp ruff check src/
uv run --directory mcp ruff format --check src/
uv run ruff check agent/ pipecat_outbound/
uv run ruff format --check agent/ pipecat_outbound/
```

`ruff check` catches lint errors; `ruff format --check` catches formatting issues. They are separate and both must pass.
