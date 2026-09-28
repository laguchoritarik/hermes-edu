# Start Hermes Edu with Codex

1. Copy this control pack **into the root of the extracted `hermes-edu` repository**, preserving paths.
2. From the repository root:

```bash
cp .env.example .env
uv lock
uv sync --all-extras --all-groups
uv run pre-commit install
```

3. Initialize Git if the archive was not already a repository:

```bash
git init
git add .
git commit -m "chore: establish Hermes Edu architecture scaffold"
```

4. Start Codex from the repository root.
5. Paste the entire contents of `CODEX_MASTER_PROMPT.md` as the first implementation task.

Do not paste the whole architecture documentation into the prompt. `AGENTS.md` is intentionally a
compact map/rules file; Codex is instructed to read the repository documentation as the source of truth.

Recommended development model:
- one Codex thread for the v0.1 implementation;
- new threads for independent audits/reviews if desired;
- do not ask Codex to blindly fill all placeholder files;
- keep vertical-slice acceptance criteria green at each phase.
