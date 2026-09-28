"""Local, content-free history of model validation outcomes."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from hermes_edu.application.ports.llm import ModelOutcome, ModelOutcomeStorePort


@dataclass(frozen=True, slots=True)
class ModelOutcomeSummary:
    task: str
    provider: str
    model: str
    validated: int
    invalid: int
    errors: int
    timeouts: int
    mean_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float | None


class SQLiteModelOutcomeStore(ModelOutcomeStorePort):
    """Store no prompts, completions, citations or private document text."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, outcome: ModelOutcome) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        usage = outcome.usage
        with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS model_outcomes (
                    id INTEGER PRIMARY KEY,
                    task TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    outcome TEXT NOT NULL CHECK (outcome IN ('validated', 'invalid', 'error')),
                    latency_ms INTEGER NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cached_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL,
                    timed_out INTEGER NOT NULL DEFAULT 0
                )"""
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(model_outcomes)")}
            if "timed_out" not in columns:
                connection.execute(
                    "ALTER TABLE model_outcomes ADD COLUMN timed_out INTEGER NOT NULL DEFAULT 0"
                )
            connection.execute(
                """INSERT INTO model_outcomes
                (task, provider, model, outcome, latency_ms, input_tokens,
                 output_tokens, cached_tokens, estimated_cost_usd, timed_out)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    outcome.task,
                    outcome.provider,
                    outcome.model,
                    outcome.outcome,
                    outcome.latency_ms,
                    usage.input_tokens if usage else 0,
                    usage.output_tokens if usage else 0,
                    usage.cached_tokens if usage else 0,
                    usage.estimated_cost_usd if usage else None,
                    int(outcome.timed_out),
                ),
            )

    def summary(self) -> tuple[ModelOutcomeSummary, ...]:
        """Return observed outcomes; samples do not establish mathematical correctness."""
        if not self.path.exists():
            return ()
        with closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(model_outcomes)")}
            timeout_expression = "SUM(timed_out)" if "timed_out" in columns else "0"
            rows = connection.execute(
                f"""SELECT task, provider, model,
                    SUM(outcome = 'validated'), SUM(outcome = 'invalid'),
                    SUM(outcome = 'error'), {timeout_expression}, AVG(latency_ms),
                    SUM(input_tokens), SUM(output_tokens),
                    CASE WHEN COUNT(*) = COUNT(estimated_cost_usd)
                         THEN SUM(estimated_cost_usd) ELSE NULL END
                FROM model_outcomes
                GROUP BY task, provider, model
                ORDER BY task, provider, model"""
            ).fetchall()
        return tuple(ModelOutcomeSummary(*row) for row in rows)
