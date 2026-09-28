"""Composition root for local knowledge, TD service and checkpointed workflow."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hermes_edu.application.ports.chat import (
    ChatReferencePort,
    ChatTaskRunnerPort,
    ProjectContextPort,
)
from hermes_edu.application.ports.embeddings import EmbeddingPort
from hermes_edu.application.ports.llm import LLMPort
from hermes_edu.application.ports.references import (
    ReferenceFilesPort,
    ReferenceParserPort,
    ReferenceRepositoryPort,
    ReferenceVectorPort,
)
from hermes_edu.application.services.chat_tools import (
    DelegateTool,
    DocumentSearchTool,
    DraftTool,
    FileSearchTool,
    ReferenceTool,
    ToolDiscoveryTool,
)
from hermes_edu.application.services.helper_agent import HelperAgent
from hermes_edu.application.services.reference_fingerprints import ReferencePipelineVersions
from hermes_edu.application.services.tools import ToolRegistry, ToolRouter
from hermes_edu.application.use_cases.adapt_course_wording import AdaptCourseWording
from hermes_edu.application.use_cases.browser import BrowserService, BrowserTool
from hermes_edu.application.use_cases.chat import ChatService
from hermes_edu.application.use_cases.create_course import CreateCourse
from hermes_edu.application.use_cases.create_td import CreateTD
from hermes_edu.application.use_cases.reference_library import ReferenceLibrary
from hermes_edu.config.paths import resolved_path
from hermes_edu.config.settings import Settings
from hermes_edu.documents.latex.pipeline import LatexDocumentAdapter
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.agent import AgentSkillSpec
from hermes_edu.domain.models.browser import BrowserViewport
from hermes_edu.domain.models.chat import (
    ChatSession,
    ChatStatus,
    ProducedArtifact,
    ProjectContext,
    TaskDraft,
)
from hermes_edu.domain.models.course import CourseRequest
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.reference import ReferenceSearchResult
from hermes_edu.domain.models.request import TDRequest
from hermes_edu.knowledge.embeddings.base import DeterministicEmbedding
from hermes_edu.knowledge.embeddings.deepinfra import DeepInfraEmbedding
from hermes_edu.knowledge.retrieval.vector import SQLiteVectorRetriever
from hermes_edu.knowledge.stores.sqlite import SQLiteKnowledgeStore
from hermes_edu.llm.providers.deepseek import DeepSeekAdapter
from hermes_edu.observability.logging import StructlogReferenceEvents
from hermes_edu.orchestration.state import encode_request
from hermes_edu.persistence.checkpoints.sqlite import sqlite_checkpointer
from hermes_edu.persistence.repositories.chat_json import JSONChatSessionRepository

if TYPE_CHECKING:
    from langgraph.graph import StateGraph

    from hermes_edu.orchestration.graphs.course import CourseState
    from hermes_edu.orchestration.state import TDState


@dataclass(frozen=True, slots=True)
class Runtime:
    service: CreateTD
    knowledge: SQLiteKnowledgeStore
    checkpoint_path: Path
    approval_required: bool
    max_revision_loops: int


def repository_root() -> Path:
    """Use the caller's working directory as a portable project root."""
    return Path.cwd().resolve()


def build_knowledge(settings: Settings, *, root: Path | None = None) -> SQLiteKnowledgeStore:
    base = root or repository_root()
    embedding = build_embedding(settings)
    return SQLiteKnowledgeStore(
        resolved_path(base, settings.hermes_db_path),
        embedding,
        chunk_size=settings.hermes_rag_chunk_size,
        overlap=settings.hermes_rag_chunk_overlap,
    )


def build_embedding(settings: Settings) -> EmbeddingPort:
    """Share one provider choice across TD retrieval and reference ingestion."""
    if settings.hermes_embedding_provider == "deterministic":
        return DeterministicEmbedding()
    if settings.hermes_embedding_provider == "deepinfra":
        return DeepInfraEmbedding(
            api_key=settings.deepinfra_api_key,
            base_url=settings.deepinfra_base_url,
            model=settings.hermes_embedding_model,
        )
    raise ValidationError("HERMES_EMBEDDING_PROVIDER must be deterministic or deepinfra")


def build_reference_library(
    settings: Settings,
    *,
    root: Path | None = None,
    embedding: EmbeddingPort | None = None,
    repository: ReferenceRepositoryPort | None = None,
    parser: ReferenceParserPort | None = None,
    vectors: ReferenceVectorPort | None = None,
    reference_files: ReferenceFilesPort | None = None,
) -> ReferenceLibrary:
    """Wire the personal library without changing the v0.1 TD store or graph."""
    # PDF/HNSW stay optional until this use case is requested.
    from hermes_edu.knowledge.chunking.semantic import MathSemanticChunker
    from hermes_edu.knowledge.ingestion.ocr import ILoveMyLatexOCR
    from hermes_edu.knowledge.ingestion.reference_files import LocalReferenceFiles
    from hermes_edu.knowledge.ingestion.structured_pdf import StructuredPDFParser
    from hermes_edu.knowledge.stores.hnsw import HNSWReferenceIndex
    from hermes_edu.persistence.repositories.sqlite import SQLiteReferenceRepository

    base = root or repository_root()
    chosen_embedding = embedding or build_embedding(settings)
    chosen_repository = repository or SQLiteReferenceRepository(
        resolved_path(base, settings.hermes_db_path)
    )
    chosen_files = reference_files or LocalReferenceFiles(
        resolved_path(base, settings.hermes_data_dir),
        resolved_path(base, settings.hermes_reference_dir),
        max_bytes=settings.hermes_reference_max_pdf_bytes,
    )
    ocr = (
        ILoveMyLatexOCR(
            api_key=settings.ilovemylatex_api_key,
            base_url=settings.ilovemylatex_base_url,
            timeout_seconds=settings.hermes_reference_ocr_timeout_seconds,
        )
        if settings.ilovemylatex_api_key or settings.hermes_reference_pdf_mode == "latex"
        else None
    )
    chosen_parser = parser or StructuredPDFParser(
        ocr, require_conversion=settings.hermes_reference_pdf_mode == "latex"
    )
    chunker = MathSemanticChunker(
        soft_max_tokens=settings.hermes_reference_soft_max_tokens,
        hard_max_tokens=settings.hermes_reference_hard_max_tokens,
    )
    chosen_vectors = vectors or HNSWReferenceIndex(
        resolved_path(base, settings.hermes_reference_hnsw_dir),
        collection=settings.hermes_reference_hnsw_collection,
        m=settings.hermes_reference_hnsw_m,
        ef_construct=settings.hermes_reference_hnsw_ef_construct,
        ef_search=settings.hermes_reference_hnsw_ef_search,
    )
    versions = ReferencePipelineVersions(
        parser=chosen_parser.version,
        ocr=chosen_parser.ocr_version,
        chunker=f"{chunker.version}:{chunker.soft_max_tokens}:{chunker.hard_max_tokens}:{chunker.overlap_tokens}",
        embedding_model=chosen_embedding.model_id,
        index=(
            f"hnsw-v1:{settings.hermes_embedding_provider}:{settings.hermes_reference_hnsw_m}:"
            f"{settings.hermes_reference_hnsw_ef_construct}:"
            f"{chunker.version}:{chunker.soft_max_tokens}:{chunker.hard_max_tokens}:"
            f"example-alpha={settings.hermes_reference_example_context_alpha:g}"
        ),
    )
    return ReferenceLibrary(
        repository=chosen_repository,
        files=chosen_files,
        parser=chosen_parser,
        chunker=chunker,
        embedding=chosen_embedding,
        vectors=chosen_vectors,
        events=StructlogReferenceEvents(),
        versions=versions,
        default_top_k=settings.hermes_reference_default_top_k,
        max_top_k=settings.hermes_reference_max_top_k,
        minimum_score=settings.hermes_reference_min_score,
        embedding_batch_size=settings.hermes_reference_embedding_batch_size,
        expected_dimension=settings.hermes_reference_embedding_dimension,
        embedding_provider=settings.hermes_embedding_provider,
        example_context_alpha=settings.hermes_reference_example_context_alpha,
    )


def build_runtime(
    settings: Settings,
    *,
    root: Path | None = None,
    llm: LLMPort | None = None,
    knowledge: SQLiteKnowledgeStore | None = None,
    tex_only: bool = False,
    approval_required: bool | None = None,
) -> Runtime:
    """Wire production adapters or explicit offline test doubles."""
    if not settings.langgraph_strict_msgpack:
        raise ValidationError("LANGGRAPH_STRICT_MSGPACK must remain true")
    os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
    base = root or repository_root()
    llm = llm or build_llm(settings, root=base)
    store = knowledge or build_knowledge(settings, root=base)
    documents = LatexDocumentAdapter(
        resolved_path(base, settings.hermes_workspace_dir),
        engine=settings.hermes_latex_engine,
        timeout_seconds=settings.hermes_latex_timeout_seconds,
        compile_pdf=not tex_only,
    )
    service = CreateTD(
        llm=llm,
        retriever=SQLiteVectorRetriever(store, store.embedding),
        documents=documents,
        top_k=settings.hermes_rag_top_k,
        context_token_budget=settings.hermes_context_token_budget,
        max_output_tokens=settings.hermes_max_output_tokens,
    )
    return Runtime(
        service=service,
        knowledge=store,
        checkpoint_path=resolved_path(base, settings.hermes_checkpoint_db_path),
        approval_required=settings.hermes_human_approval_required
        if approval_required is None
        else approval_required,
        max_revision_loops=settings.hermes_max_revision_loops,
    )


def build_graph(runtime: Runtime) -> StateGraph[TDState]:
    """Import LangGraph only after strict checkpoint settings are applied."""
    from hermes_edu.orchestration.graphs.main import build_main_graph

    return build_main_graph(
        runtime.service,
        approval_required=runtime.approval_required,
        max_revision_loops=runtime.max_revision_loops,
    )


def build_llm(settings: Settings, *, root: Path | None = None) -> LLMPort:
    """Use one configured provider boundary across educational workflows."""
    if settings.hermes_default_provider != "deepseek":
        raise ValidationError("v0.1 supports DeepSeek generation only")
    fallback_names = {
        "audit": settings.hermes_audit_fallback_models,
        "revise": settings.hermes_revision_fallback_models,
        "plan": settings.hermes_plan_fallback_models,
        "generate": settings.hermes_generation_fallback_models,
        "verify": settings.hermes_generation_fallback_models,
    }
    primary = DeepSeekAdapter(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.hermes_default_model or settings.deepseek_model,
        generation_model=settings.hermes_generation_model,
        audit_model=settings.hermes_audit_model
        if settings.hermes_audit_provider != "deepinfra"
        else "",
        plan_reasoning_effort=settings.hermes_plan_reasoning_effort,
        generation_reasoning_effort=settings.hermes_generation_reasoning_effort,
        audit_reasoning_effort=settings.hermes_audit_reasoning_effort,
        input_cost_per_million_usd=settings.hermes_input_cost_per_million_usd,
        cached_input_cost_per_million_usd=settings.hermes_cached_input_cost_per_million_usd,
        output_cost_per_million_usd=settings.hermes_output_cost_per_million_usd,
        timeout_seconds=settings.hermes_deepseek_timeout_seconds,
        max_attempts=settings.hermes_deepseek_max_attempts,
        fallback_tasks=frozenset(
            task for task, configured in fallback_names.items() if configured.strip()
        ),
    )
    from hermes_edu.llm.providers.deepinfra import DeepInfraChatAdapter
    from hermes_edu.llm.providers.openrouter import OpenRouterChatAdapter
    from hermes_edu.llm.router import TaskRoutedLLM
    from hermes_edu.persistence.model_outcomes import SQLiteModelOutcomeStore

    def deepinfra(model: str, *, has_fallback: bool = False) -> LLMPort:
        if not model:
            raise ValidationError("Set the DeepInfra task model or DEEPINFRA_MODEL")
        return DeepInfraChatAdapter(
            api_key=settings.deepinfra_api_key,
            base_url=settings.deepinfra_base_url,
            model=model,
            input_cost_per_million_usd=settings.deepinfra_input_cost_per_million_usd,
            cached_input_cost_per_million_usd=settings.deepinfra_cached_input_cost_per_million_usd,
            output_cost_per_million_usd=settings.deepinfra_output_cost_per_million_usd,
            timeout_seconds=settings.hermes_deepinfra_timeout_seconds,
            max_attempts=1 if has_fallback else settings.hermes_deepinfra_max_attempts,
        )

    def openrouter(model: str, *, has_fallback: bool = False) -> LLMPort:
        chosen_model = model or settings.openrouter_model
        if not chosen_model:
            raise ValidationError("Set OPENROUTER_MODEL or the OpenRouter task model")
        return OpenRouterChatAdapter(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=chosen_model,
            timeout_seconds=settings.hermes_openrouter_timeout_seconds,
            max_attempts=1 if has_fallback else settings.hermes_openrouter_max_attempts,
        )

    def fallback_port(model: str, *, has_fallback: bool) -> LLMPort:
        if model == "deepseek":
            return primary
        if model.startswith("openrouter:"):
            return openrouter(model.removeprefix("openrouter:"), has_fallback=has_fallback)
        if model.startswith("deepinfra:"):
            return deepinfra(model.removeprefix("deepinfra:"), has_fallback=has_fallback)
        return deepinfra(model, has_fallback=has_fallback)

    def fallback_label(task: str, model: str) -> tuple[str, str]:
        if model == "deepseek":
            return deepseek_label(task)
        if model.startswith("openrouter:"):
            return ("openrouter", model.removeprefix("openrouter:") or settings.openrouter_model)
        if model.startswith("deepinfra:"):
            return ("deepinfra", model.removeprefix("deepinfra:"))
        return ("deepinfra", model)

    audit: LLMPort = primary
    revision: LLMPort = primary
    audit_model = settings.hermes_audit_model or settings.deepinfra_model
    revision_model = settings.hermes_revision_model or settings.deepinfra_model
    if settings.hermes_audit_provider == "deepinfra":
        audit = deepinfra(audit_model, has_fallback=bool(fallback_names["audit"].strip()))
    if settings.hermes_audit_provider == "openrouter":
        audit_model = settings.hermes_audit_model or settings.openrouter_model
        audit = openrouter(audit_model, has_fallback=bool(fallback_names["audit"].strip()))
    if settings.hermes_revision_provider == "deepinfra":
        revision = deepinfra(revision_model, has_fallback=bool(fallback_names["revise"].strip()))
    if settings.hermes_revision_provider == "openrouter":
        revision_model = settings.hermes_revision_model or settings.openrouter_model
        revision = openrouter(revision_model, has_fallback=bool(fallback_names["revise"].strip()))
    alternatives: dict[str, tuple[LLMPort, ...]] = {}
    labels: dict[str, tuple[tuple[str, str], ...]] = {}

    def deepseek_label(task: str) -> tuple[str, str]:
        base_model = settings.hermes_default_model or settings.deepseek_model
        if task in {"generate", "revise"}:
            return ("deepseek", settings.hermes_generation_model or base_model)
        if task in {"audit", "verify"} and settings.hermes_audit_provider != "deepinfra":
            return ("deepseek", settings.hermes_audit_model or base_model)
        return ("deepseek", base_model)

    for task, configured in fallback_names.items():
        if not configured.strip():
            continue
        selected: list[LLMPort] = []
        selected_labels: list[tuple[str, str]] = []
        for name in configured.split(","):
            model = name.strip()
            if not model:
                raise ValidationError(f"HERMES_{task.upper()}_FALLBACK_MODELS has an empty entry")
            selected.append(fallback_port(model, has_fallback=True))
            selected_labels.append(fallback_label(task, model))
        alternatives[task] = tuple(selected)
        if task == "audit" and settings.hermes_audit_provider == "deepinfra":
            preferred = ("deepinfra", audit_model)
        elif task == "audit" and settings.hermes_audit_provider == "openrouter":
            preferred = ("openrouter", audit_model)
        elif task == "revise" and settings.hermes_revision_provider == "deepinfra":
            preferred = ("deepinfra", revision_model)
        elif task == "revise" and settings.hermes_revision_provider == "openrouter":
            preferred = ("openrouter", revision_model)
        else:
            preferred = deepseek_label(task)
        if preferred in selected_labels:
            raise ValidationError(f"{task} fallback repeats its preferred model")
        labels[task] = (preferred, *selected_labels)
    for task in ("plan", "generate", "audit", "revise", "verify", "wording"):
        if task not in labels:
            if task == "audit" and settings.hermes_audit_provider == "deepinfra":
                labels[task] = (("deepinfra", audit_model),)
            elif task == "audit" and settings.hermes_audit_provider == "openrouter":
                labels[task] = (("openrouter", audit_model),)
            elif task == "revise" and settings.hermes_revision_provider == "deepinfra":
                labels[task] = (("deepinfra", revision_model),)
            elif task == "revise" and settings.hermes_revision_provider == "openrouter":
                labels[task] = (("openrouter", revision_model),)
            else:
                labels[task] = (deepseek_label(task),)
    return TaskRoutedLLM(
        primary=primary,
        audit=audit,
        revision=revision,
        alternatives=alternatives,
        labels=labels,
        outcomes=SQLiteModelOutcomeStore(
            resolved_path(root or repository_root(), settings.hermes_llm_metrics_db_path)
        ),
    )


def build_helper_llm(settings: Settings) -> LLMPort:
    """Build the configurable economical helper model without changing workflow routing."""
    if settings.hermes_helper_provider == "deepseek":
        return DeepSeekAdapter(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.hermes_helper_model
            or settings.hermes_default_model
            or settings.deepseek_model,
            generation_model=settings.hermes_helper_model,
            input_cost_per_million_usd=settings.hermes_input_cost_per_million_usd,
            cached_input_cost_per_million_usd=settings.hermes_cached_input_cost_per_million_usd,
            output_cost_per_million_usd=settings.hermes_output_cost_per_million_usd,
            timeout_seconds=settings.hermes_deepseek_timeout_seconds,
            max_attempts=settings.hermes_deepseek_max_attempts,
        )
    if settings.hermes_helper_provider == "deepinfra":
        from hermes_edu.llm.providers.deepinfra import DeepInfraChatAdapter

        model = settings.hermes_helper_model or settings.deepinfra_model
        if not model:
            raise ValidationError("Set HERMES_HELPER_MODEL or DEEPINFRA_MODEL for helper")
        return DeepInfraChatAdapter(
            api_key=settings.deepinfra_api_key,
            base_url=settings.deepinfra_base_url,
            model=model,
            input_cost_per_million_usd=settings.deepinfra_input_cost_per_million_usd,
            cached_input_cost_per_million_usd=settings.deepinfra_cached_input_cost_per_million_usd,
            output_cost_per_million_usd=settings.deepinfra_output_cost_per_million_usd,
            timeout_seconds=settings.hermes_deepinfra_timeout_seconds,
            max_attempts=settings.hermes_deepinfra_max_attempts,
        )
    from hermes_edu.llm.providers.openrouter import OpenRouterChatAdapter

    model = settings.hermes_helper_model or settings.openrouter_model
    if not model:
        raise ValidationError("Set HERMES_HELPER_MODEL or OPENROUTER_MODEL for helper")
    return OpenRouterChatAdapter(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=model,
        timeout_seconds=settings.hermes_openrouter_timeout_seconds,
        max_attempts=settings.hermes_openrouter_max_attempts,
    )


@dataclass(frozen=True, slots=True)
class CourseRuntime:
    service: CreateCourse
    checkpoint_path: Path
    approval_required: bool
    max_revision_loops: int
    max_latex_repair_loops: int
    wording: AdaptCourseWording | None = None


def build_course_runtime(
    settings: Settings,
    *,
    root: Path | None = None,
    llm: LLMPort | None = None,
    tex_only: bool = False,
    approval_required: bool | None = None,
) -> CourseRuntime:
    """Wire course generation to official-programme and personal-reference retrieval."""
    from hermes_edu.documents.latex.course import LatexCourseAdapter
    from hermes_edu.documents.latex.math_content import validate_math_text

    if not settings.langgraph_strict_msgpack:
        raise ValidationError("LANGGRAPH_STRICT_MSGPACK must remain true")
    os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
    base = root or repository_root()
    store = build_knowledge(settings, root=base)
    course_llm = llm or build_llm(settings, root=base)
    service = CreateCourse(
        llm=course_llm,
        curriculum=SQLiteVectorRetriever(
            store, store.embedding, min_score=settings.hermes_reference_min_score
        ),
        references=build_reference_library(settings, root=base, embedding=store.embedding),
        documents=LatexCourseAdapter(
            resolved_path(base, settings.hermes_workspace_dir),
            engine=settings.hermes_latex_engine,
            timeout_seconds=settings.hermes_latex_timeout_seconds,
            compile_pdf=not tex_only,
            template_path=resolved_path(base, settings.hermes_course_template_path)
            if settings.hermes_course_template_path
            else None,
        ),
        validate_text=validate_math_text,
        top_k=min(settings.hermes_rag_top_k, settings.hermes_reference_max_top_k),
        example_top_k=min(
            settings.hermes_course_example_top_k,
            settings.hermes_reference_max_top_k,
        ),
        context_token_budget=settings.hermes_context_token_budget,
        max_output_tokens=settings.hermes_max_output_tokens,
    )
    return CourseRuntime(
        service,
        resolved_path(base, settings.hermes_checkpoint_db_path),
        settings.hermes_human_approval_required if approval_required is None else approval_required,
        settings.hermes_max_revision_loops,
        settings.hermes_latex_repair_loops,
        AdaptCourseWording(llm=course_llm, max_output_tokens=settings.hermes_max_output_tokens),
    )


def build_course_workflow(runtime: CourseRuntime) -> StateGraph[CourseState]:
    """Keep graph implementation outside the composition contract."""
    from hermes_edu.orchestration.graphs.course import build_course_graph

    return build_course_graph(
        runtime.service,
        approval_required=runtime.approval_required,
        max_revision_loops=runtime.max_revision_loops,
        max_latex_repair_loops=runtime.max_latex_repair_loops,
        wording=runtime.wording,
    )


class StaticProjectContext(ProjectContextPort):
    """Load lightweight local project defaults until a project registry exists."""

    def load(self, project_id: str | None) -> ProjectContext | None:
        if not project_id:
            return None
        normalized = project_id.lower()
        if "ensam" in normalized and "analyse1" in normalized.replace("-", ""):
            return ProjectContext(
                project_id=project_id,
                institution="ENSAM Rabat",
                subject="Analyse 1",
                level="ENSAM CP1",
                curriculum=project_id,
                track="CP1",
            )
        return ProjectContext(project_id=project_id, curriculum=project_id)


class ReferenceLibraryChatAdapter(ChatReferencePort):
    """Expose reference ingestion to chat without duplicating the ingestion pipeline."""

    def __init__(self, library: ReferenceLibrary) -> None:
        self._library = library

    def add_pdf(self, path: Path) -> str:
        return self._library.import_pdf(path).document_id

    def import_pdf_bytes(self, content: bytes, filename: str, *, title: str | None = None) -> str:
        return self._library.import_pdf_bytes(content, filename, title=title).document_id

    def describe(self, document_ids: tuple[str, ...]) -> tuple[str, ...]:
        labels: list[str] = []
        for document_id in document_ids:
            try:
                reference = self._library.get(document_id)
            except Exception:
                labels.append(document_id)
            else:
                labels.append(f"{reference.document_id} - {reference.title}")
        return tuple(labels)

    def search(self, query: str, *, top_k: int | None = None) -> ReferenceSearchResult:
        return self._library.search(query, top_k=top_k)


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


def build_browser_service(
    settings: Settings,
    *,
    root: Path | None = None,
    visible: bool = False,
    reference_ingestion: ReferenceLibraryChatAdapter | None = None,
) -> BrowserService:
    """Wire the generic browser service to the Playwright adapter at the boundary."""
    from hermes_edu.browser.playwright import PlaywrightBrowserAdapter

    base = root or repository_root()
    return BrowserService(
        PlaywrightBrowserAdapter(
            sessions_dir=resolved_path(base, settings.hermes_browser_sessions_dir),
            max_snapshot_chars=settings.hermes_browser_max_snapshot_chars,
        ),
        enabled=True,
        max_steps=settings.hermes_browser_max_steps,
        headless=False if visible else settings.hermes_browser_headless,
        viewport=BrowserViewport(
            settings.hermes_browser_viewport_width,
            settings.hermes_browser_viewport_height,
        ),
        max_snapshot_chars=settings.hermes_browser_max_snapshot_chars,
        downloads_enabled=settings.hermes_browser_downloads_enabled,
        screenshots_enabled=settings.hermes_browser_screenshots_enabled,
        allowed_domains=_csv_tuple(settings.hermes_browser_allowed_domains),
        blocked_domains=_csv_tuple(settings.hermes_browser_blocked_domains),
        references=reference_ingestion,
    )


def build_chat_tool_registry(
    settings: Settings,
    *,
    root: Path,
    references: ReferenceLibraryChatAdapter,
    browser: BrowserService | None,
) -> ToolRegistry:
    """Expose only application-bound tools; policies remain inside each tool/service."""
    allowed_roots = tuple(
        Path(item.strip()) for item in settings.hermes_mcp_allowed_roots.split(",") if item.strip()
    )
    registry = ToolRegistry(
        (
            FileSearchTool(root=root, allowed_roots=allowed_roots or (settings.hermes_data_dir,)),
            ReferenceTool(references),
            DocumentSearchTool(references),
            DraftTool(),
            DelegateTool(),
        )
    )
    if browser is not None:
        registry.register(BrowserTool(browser))
    registry.register(ToolDiscoveryTool(registry))
    return registry


def load_local_skills(root: Path) -> tuple[AgentSkillSpec, ...]:
    """Load compact local skill cards for the helper context."""
    skills_dir = root / "skills"
    specs: list[AgentSkillSpec] = []
    if not skills_dir.exists():
        return ()
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        name = path.parent.name
        goal = _section_after(lines, "## Goal") or (lines[1] if len(lines) > 1 else name)
        workflow = _section_after(lines, "## Workflow")
        constraints = tuple(line.lstrip("0123456789. -") for line in lines if line.startswith("- "))
        tools = tuple(
            tool for tool in ("browser", "references", "documents", "files") if tool in text.lower()
        )
        specs.append(
            AgentSkillSpec(
                name,
                goal=goal[:300],
                when_to_use=workflow[:500] if workflow else goal[:300],
                tools=tools,
                constraints=constraints[:6],
            )
        )
    return tuple(specs)


def _section_after(lines: list[str], header: str) -> str:
    for index, line in enumerate(lines):
        if line.lower() == header.lower() and index + 1 < len(lines):
            return lines[index + 1]
    return ""


class HermesWorkflowChatRunner(ChatTaskRunnerPort):
    """Translate a ready chat draft to the existing checkpointed workflows."""

    def __init__(
        self,
        settings: Settings,
        *,
        root: Path,
        tex_only: bool,
        auto_confirm: bool,
    ) -> None:
        self._settings = settings
        self._root = root
        self._tex_only = tex_only
        self._auto_confirm = auto_confirm

    def preview_plan(self, draft: TaskDraft) -> tuple[str, ...]:
        if not draft.topic:
            return ()
        sessions = draft.duration.sessions or draft.section_count or 4
        if "course" in draft.outputs:
            return tuple(f"Séance {index}: {draft.topic}" for index in range(1, sessions + 1))
        count = draft.exercise_count or 6
        return tuple(f"Exercice {index}: {draft.topic}" for index in range(1, min(count, 12) + 1))

    def run(self, session: ChatSession) -> ChatSession:
        draft = session.task_draft
        if "course" in draft.outputs or draft.task_type == "course_bundle":
            return self._run_course(session)
        if "tutorial" in draft.outputs:
            return self._run_td(session)
        raise ValidationError("Aucun workflow existant ne correspond encore à cette demande")

    def _run_td(self, session: ChatSession) -> ChatSession:
        draft = session.task_draft
        runtime = build_runtime(
            self._settings,
            root=self._root,
            tex_only=self._tex_only,
            approval_required=not self._auto_confirm,
        )
        request = TDRequest(
            draft.topic,
            LearningContext(draft.curriculum or "sample-mp", draft.track or "MP"),
            min(draft.exercise_count or 6, 12),
            include_solutions="solutions" in draft.outputs,
        )
        identifier = session.active_task or session.id
        with sqlite_checkpointer(runtime.checkpoint_path) as saver:
            graph = build_graph(runtime).compile(checkpointer=saver)  # pyright: ignore[reportUnknownMemberType]
            state = cast(
                "dict[str, object]",
                graph.invoke(  # pyright: ignore[reportUnknownMemberType]
                    {"request_json": encode_request(request), "thread_id": identifier},
                    config={"configurable": {"thread_id": identifier}},
                ),
            )
        return _session_from_graph_state(session, state, identifier)

    def _run_course(self, session: ChatSession) -> ChatSession:
        draft = session.task_draft
        runtime = build_course_runtime(
            self._settings,
            root=self._root,
            tex_only=self._tex_only,
            approval_required=not self._auto_confirm,
        )
        request = CourseRequest(
            draft.topic,
            draft.curriculum or "sample-mp",
            draft.track or "MP",
            draft.section_count or min(draft.duration.sessions or 6, 12),
            session.selected_sources,
        )
        identifier = session.active_task or session.id
        with sqlite_checkpointer(runtime.checkpoint_path) as saver:
            graph = build_course_workflow(runtime).compile(  # pyright: ignore[reportUnknownMemberType]
                checkpointer=saver
            )
            state = cast(
                "dict[str, object]",
                graph.invoke(  # pyright: ignore[reportUnknownMemberType]
                    {
                        "workflow": "course",
                        "request_json": json.dumps(asdict(request)),
                        "thread_id": identifier,
                        "tex_only": self._tex_only,
                        "approval_required": runtime.approval_required,
                    },
                    config={"configurable": {"thread_id": identifier}, "recursion_limit": 100},
                ),
            )
        return _session_from_graph_state(session, state, identifier)


def _session_from_graph_state(
    session: ChatSession, state: dict[str, object], identifier: str
) -> ChatSession:
    artifacts: tuple[ProducedArtifact, ...] = ()
    status = ChatStatus.COMPLETED
    if "__interrupt__" in state:
        status = ChatStatus.READY
    elif isinstance(state.get("result_json"), str):
        try:
            payload = json.loads(str(state["result_json"]))
        except json.JSONDecodeError:
            artifacts = (ProducedArtifact(str(state["result_json"]), "result"),)
        else:
            if isinstance(payload, dict):
                payload_dict = cast("dict[str, object]", payload)
                raw_artifacts_object = payload_dict.get("artifacts", [])
                raw_artifacts = (
                    cast("list[object]", raw_artifacts_object)
                    if isinstance(raw_artifacts_object, list)
                    else []
                )
                artifacts = tuple(
                    ProducedArtifact(
                        str(cast("dict[str, object]", item).get("path", "")),
                        str(cast("dict[str, object]", item).get("kind", "")),
                    )
                    for item in raw_artifacts
                    if isinstance(item, dict)
                )
    return replace(
        session,
        active_task=identifier,
        status=status,
        produced_artifacts=artifacts,
    )


def build_chat_service(
    settings: Settings,
    *,
    root: Path | None = None,
    tex_only: bool = False,
    auto_confirm: bool | None = None,
    browser_enabled: bool | None = None,
    browser_visible: bool = False,
) -> ChatService:
    """Compose the reusable chat facade over existing Hermes services."""
    base = root or repository_root()
    confirm = settings.hermes_chat_auto_confirm if auto_confirm is None else auto_confirm
    reference_adapter = ReferenceLibraryChatAdapter(build_reference_library(settings, root=base))
    enable_browser = settings.hermes_browser_enabled if browser_enabled is None else browser_enabled
    browser_service = (
        build_browser_service(
            settings,
            root=base,
            visible=browser_visible,
            reference_ingestion=reference_adapter,
        )
        if enable_browser
        else None
    )
    tool_registry = build_chat_tool_registry(
        settings, root=base, references=reference_adapter, browser=browser_service
    )
    return ChatService(
        sessions=JSONChatSessionRepository(resolved_path(base, settings.hermes_chat_sessions_dir)),
        projects=StaticProjectContext(),
        references=reference_adapter,
        runner=HermesWorkflowChatRunner(
            settings,
            root=base,
            tex_only=tex_only,
            auto_confirm=confirm,
        ),
        auto_confirm=confirm,
        browser=browser_service,
        helper_agent=HelperAgent(
            build_helper_llm(settings),
            max_output_tokens=settings.hermes_helper_max_output_tokens,
        )
        if settings.hermes_agent_enabled
        else None,
        tool_registry=tool_registry if settings.hermes_agent_enabled else None,
        tool_router=ToolRouter(tool_registry) if settings.hermes_agent_enabled else None,
        skills=load_local_skills(base),
        agent_max_steps=settings.hermes_agent_max_steps,
        agent_context_token_budget=settings.hermes_helper_context_token_budget,
    )
