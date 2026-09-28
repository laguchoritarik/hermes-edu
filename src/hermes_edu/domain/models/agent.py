"""Provider-neutral records for the conversational helper agent."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from hermes_edu.domain.models.usage import ModelUsage

if TYPE_CHECKING:
    from hermes_edu.domain.models.chat import ProjectContext, TaskDraft


def _empty_str_mapping() -> Mapping[str, str]:
    return {}


def _empty_object_mapping() -> Mapping[str, object]:
    return {}


class AgentDecisionType(StrEnum):
    TOOL_CALL = "TOOL_CALL"
    TOOL_CALLS = "TOOL_CALLS"
    UPDATE_STATE = "UPDATE_STATE"
    ASK_USER = "ASK_USER"
    DELEGATE = "DELEGATE"
    RESPOND = "RESPOND"
    FINISH = "FINISH"


@dataclass(frozen=True, slots=True)
class AgentToolSpec:
    name: str
    description: str
    actions: Mapping[str, str] = field(default_factory=_empty_str_mapping)


@dataclass(frozen=True, slots=True)
class AgentSkillSpec:
    name: str
    goal: str
    when_to_use: str
    tools: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    tool: str
    action: str
    arguments: Mapping[str, object] = field(default_factory=_empty_object_mapping)


@dataclass(frozen=True, slots=True)
class AgentObservation:
    id: str
    kind: str
    summary: str
    metadata: Mapping[str, str] = field(default_factory=_empty_str_mapping)


@dataclass(frozen=True, slots=True)
class AgentMetrics:
    helper_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    delegated_calls: int = 0
    estimated_cost_usd: float | None = 0.0

    def with_usage(self, usage: ModelUsage) -> AgentMetrics:
        cost: float | None
        if self.estimated_cost_usd is None or usage.estimated_cost_usd is None:
            cost = None
        else:
            cost = self.estimated_cost_usd + usage.estimated_cost_usd
        return AgentMetrics(
            helper_calls=self.helper_calls + 1,
            tool_calls=self.tool_calls,
            tokens_in=self.tokens_in + usage.input_tokens,
            tokens_out=self.tokens_out + usage.output_tokens,
            delegated_calls=self.delegated_calls,
            estimated_cost_usd=cost,
        )

    def with_tool_call(self) -> AgentMetrics:
        return AgentMetrics(
            helper_calls=self.helper_calls,
            tool_calls=self.tool_calls + 1,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            delegated_calls=self.delegated_calls,
            estimated_cost_usd=self.estimated_cost_usd,
        )

    def with_delegation(self) -> AgentMetrics:
        return AgentMetrics(
            helper_calls=self.helper_calls,
            tool_calls=self.tool_calls,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            delegated_calls=self.delegated_calls + 1,
            estimated_cost_usd=self.estimated_cost_usd,
        )


@dataclass(frozen=True, slots=True)
class AgentDecision:
    type: AgentDecisionType
    tool_calls: tuple[AgentToolCall, ...] = ()
    patch: Mapping[str, object] = field(default_factory=_empty_object_mapping)
    question: str = ""
    response: str = ""
    agent: str = ""
    capability: str = ""
    task: Mapping[str, object] = field(default_factory=_empty_object_mapping)
    intent_summary: str = ""
    skill: str = ""


@dataclass(frozen=True, slots=True)
class AgentContext:
    user_message: str
    draft: TaskDraft
    project: ProjectContext | None = None
    session_summary: str = ""
    recent_observations: tuple[AgentObservation, ...] = ()
    available_skills: tuple[AgentSkillSpec, ...] = ()
    selected_tools: tuple[AgentToolSpec, ...] = ()
    permissions: tuple[str, ...] = ()
    token_budget: int = 3000
