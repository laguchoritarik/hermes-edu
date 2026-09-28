"""Environment configuration for the first runnable slice."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    hermes_env: str = "development"
    hermes_log_level: str = "INFO"
    hermes_data_dir: Path = Path("data")
    hermes_workspace_dir: Path = Path("workspace")
    hermes_chat_sessions_dir: Path = Path(".hermes/sessions")
    hermes_browser_sessions_dir: Path = Path(".hermes/browser/sessions")
    hermes_project_dir: Path = Path("data/projects")
    hermes_chat_auto_confirm: bool = False
    hermes_agent_enabled: bool = True
    hermes_agent_max_steps: int = Field(default=12, ge=1, le=30)
    hermes_helper_provider: Literal["deepseek", "deepinfra", "openrouter"] = "deepseek"
    hermes_helper_model: str = ""
    hermes_helper_max_output_tokens: int = Field(default=1200, ge=128, le=8000)
    hermes_helper_context_token_budget: int = Field(default=2500, ge=512, le=12000)
    hermes_browser_enabled: bool = False
    hermes_browser_headless: bool = True
    hermes_browser_allowed_domains: str = ""
    hermes_browser_blocked_domains: str = ""
    hermes_browser_max_steps: int = Field(default=50, ge=1, le=200)
    hermes_browser_max_snapshot_chars: int = Field(default=12000, ge=1000, le=50000)
    hermes_browser_downloads_enabled: bool = True
    hermes_browser_screenshots_enabled: bool = True
    hermes_browser_timeout_ms: int = Field(default=10000, ge=1000, le=60000)
    hermes_browser_viewport_width: int = Field(default=1280, ge=320, le=7680)
    hermes_browser_viewport_height: int = Field(default=900, ge=240, le=4320)
    hermes_db_path: Path = Path(".local/hermes.db")
    hermes_checkpoint_db_path: Path = Path(".local/checkpoints.db")
    hermes_human_approval_required: bool = True
    hermes_max_revision_loops: int = Field(default=3, ge=0, le=10)
    hermes_rag_top_k: int = Field(default=8, ge=1, le=20)
    hermes_course_example_top_k: int = Field(default=6, ge=0, le=20)
    hermes_rag_chunk_size: int = Field(default=1200, ge=200, le=5000)
    hermes_rag_chunk_overlap: int = Field(default=150, ge=0, le=1000)
    hermes_reference_dir: Path = Path(".local/reference-files")
    hermes_reference_hnsw_dir: Path = Path(".local/reference-hnsw")
    hermes_reference_max_pdf_bytes: int = Field(default=20_000_000, ge=1000, le=200_000_000)
    hermes_reference_pdf_mode: Literal["latex", "text"] = "latex"
    hermes_reference_soft_max_tokens: int = Field(default=1000, ge=100, le=5000)
    hermes_reference_hard_max_tokens: int = Field(default=1400, ge=100, le=10000)
    hermes_reference_default_top_k: int = Field(default=5, ge=1, le=100)
    hermes_reference_max_top_k: int = Field(default=30, ge=1, le=100)
    hermes_reference_min_score: float = Field(default=0.35, ge=-1, le=1)
    hermes_reference_embedding_batch_size: int = Field(default=16, ge=1, le=128)
    hermes_reference_embedding_dimension: int = Field(default=0, ge=0, le=10000)
    hermes_reference_example_context_alpha: float = Field(default=0.8, ge=0, le=1)
    hermes_reference_hnsw_collection: str = "references"
    hermes_reference_hnsw_m: int = Field(default=16, ge=4, le=64)
    hermes_reference_hnsw_ef_construct: int = Field(default=200, ge=16, le=1000)
    hermes_reference_hnsw_ef_search: int = Field(default=64, ge=1, le=1000)
    hermes_context_token_budget: int = Field(default=3000, ge=256, le=50000)
    hermes_default_provider: str = "deepseek"
    hermes_default_model: str = "deepseek-flash"
    hermes_generation_model: str = ""
    hermes_audit_model: str = ""
    hermes_audit_provider: Literal["", "deepseek", "deepinfra", "openrouter"] = ""
    hermes_revision_provider: Literal["", "deepseek", "deepinfra", "openrouter"] = ""
    hermes_revision_model: str = ""
    hermes_audit_fallback_models: str = ""
    hermes_revision_fallback_models: str = ""
    hermes_plan_fallback_models: str = ""
    hermes_generation_fallback_models: str = ""
    hermes_llm_metrics_db_path: Path = Path(".local/llm-metrics.db")
    hermes_deepinfra_timeout_seconds: float = Field(default=60.0, ge=1, le=600)
    hermes_deepinfra_max_attempts: int = Field(default=3, ge=1, le=5)
    hermes_deepseek_timeout_seconds: float = Field(default=60.0, ge=1, le=600)
    hermes_deepseek_max_attempts: int = Field(default=3, ge=1, le=5)
    deepinfra_input_cost_per_million_usd: float | None = Field(default=None, ge=0)
    deepinfra_cached_input_cost_per_million_usd: float | None = Field(default=None, ge=0)
    deepinfra_output_cost_per_million_usd: float | None = Field(default=None, ge=0)
    hermes_plan_reasoning_effort: Literal["none", "low", "high", "max"] = "none"
    hermes_generation_reasoning_effort: Literal["none", "low", "high", "max"] = "low"
    hermes_audit_reasoning_effort: Literal["none", "low", "high", "max"] = "low"
    hermes_max_output_tokens: int = Field(default=3000, ge=128, le=16000)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    hermes_embedding_provider: str = "deterministic"
    hermes_embedding_model: str = "Qwen/Qwen3-Embedding-8B"
    deepinfra_api_key: str = ""
    deepinfra_base_url: str = "https://api.deepinfra.com/v1/openai"
    deepinfra_model: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = ""
    hermes_openrouter_timeout_seconds: float = Field(default=60.0, ge=1, le=600)
    hermes_openrouter_max_attempts: int = Field(default=3, ge=1, le=5)
    ilovemylatex_api_key: str = ""
    ilovemylatex_base_url: str = "https://app.ilovemylatex.com/api/v1"
    hermes_reference_ocr_timeout_seconds: int = Field(default=120, ge=10, le=600)
    hermes_latex_engine: str = "xelatex"
    hermes_latex_timeout_seconds: int = Field(default=60, ge=1, le=300)
    hermes_latex_repair_loops: int = Field(default=1, ge=0, le=3)
    hermes_course_template_path: Path | None = None
    hermes_mcp_allowed_roots: str = "data,workspace"
    langgraph_strict_msgpack: bool = True
    hermes_input_cost_per_million_usd: float | None = Field(default=None, ge=0)
    hermes_cached_input_cost_per_million_usd: float | None = Field(default=None, ge=0)
    hermes_output_cost_per_million_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_chunking(self) -> "Settings":
        if self.hermes_rag_chunk_overlap >= self.hermes_rag_chunk_size:
            raise ValueError("HERMES_RAG_CHUNK_OVERLAP must be smaller than chunk size")
        if self.hermes_reference_soft_max_tokens > self.hermes_reference_hard_max_tokens:
            raise ValueError("Reference soft chunk limit must not exceed hard limit")
        if self.hermes_reference_default_top_k > self.hermes_reference_max_top_k:
            raise ValueError("Reference default top_k must not exceed maximum")
        for configured in (
            self.hermes_audit_fallback_models,
            self.hermes_revision_fallback_models,
            self.hermes_plan_fallback_models,
            self.hermes_generation_fallback_models,
        ):
            if not configured.strip():
                continue
            names = tuple(name.strip() for name in configured.split(","))
            if len(names) > 4 or not all(names) or len(set(names)) != len(names):
                raise ValueError("Fallback models must be 1-4 distinct nonempty names")
        return self


def load_settings() -> Settings:
    """Load settings at the composition boundary, never at import time."""
    return Settings()
