"""Low-cost incremental intent extraction for the chat interface."""

from __future__ import annotations

import re
from dataclasses import replace

from hermes_edu.domain.models.chat import DurationSpec, ParsedIntent, ProjectContext, TaskDraft

_OUTPUT_ALIASES: tuple[tuple[str, str], ...] = (
    ("corrige", "solutions"),
    ("correction", "solutions"),
    ("solutions", "solutions"),
    ("td", "tutorial"),
    ("exercices", "tutorial"),
    ("fiche", "summary"),
    ("synthese", "summary"),
    ("resume", "summary"),
    ("cours", "course"),
    ("beamer", "course"),
)
_REMOVE_WORDS = ("enleve", "retire", "supprime", "sans", "pas de")
_TOPIC_PATTERNS = (
    re.compile(
        r"\b(?:sur|chapitre sur|theme|sujet)\s+"
        r"(?:les?|l['\u2019])?([A-Za-zÀ-ÿ0-9 '\u2019-]{3,80})"
    ),
    re.compile(
        r"\b(?:prepare|fais|cree).{0,30}\b"
        r"(?:les?|l['\u2019])?([A-Za-zÀ-ÿ0-9 '\u2019-]{3,80})"
    ),
)


def _normalize(text: str) -> str:
    return (
        text.lower()
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("ç", "c")
        .replace("ô", "o")
        .replace("î", "i")
        .replace("ï", "i")
        .replace("û", "u")
    )


def _append_unique(values: tuple[str, ...], *new_values: str) -> tuple[str, ...]:
    result = list(values)
    for value in new_values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _without(values: tuple[str, ...], *removed: str) -> tuple[str, ...]:
    denied = set(removed)
    return tuple(value for value in values if value not in denied)


class ChatIntentParser:
    """Extract structured deltas without reparsing the complete conversation."""

    def parse_delta(
        self,
        message: str,
        draft: TaskDraft,
        project: ProjectContext | None = None,
    ) -> tuple[ParsedIntent, TaskDraft]:
        text = message.strip()
        lowered = _normalize(text)
        updated = self._apply_project_defaults(draft, project)
        intent = "update_task"

        outputs = updated.outputs
        removing = any(word in lowered for word in _REMOVE_WORDS)
        for needle, output in _OUTPUT_ALIASES:
            if needle not in lowered:
                continue
            outputs = _without(outputs, output) if removing else _append_unique(outputs, output)

        parsed_topic = self._topic_from(text, lowered)
        output_words = {"td", "cours", "corrige", "corrigé", "fiche", "solutions"}
        topic = (
            parsed_topic
            if parsed_topic and parsed_topic.lower() not in output_words
            else updated.topic
        )
        subject = updated.subject
        if match := re.search(r"\b(?:pour|en)\s+([A-Za-zÀ-ÿ]+(?:\s+[0-9A-Za-zÀ-ÿ]+)?)\b", text):
            candidate = match.group(1).strip(" .")
            if candidate.lower() not in {"cp1", "cp2", "mp", "pc", "psi"}:
                subject = candidate
        if "analyse 1" in lowered:
            subject = "Analyse 1"

        level = updated.level
        track = updated.track
        if "ensam" in lowered and "cp1" in lowered:
            level = "ENSAM CP1"
            track = "CP1"
        elif "cp1" in lowered:
            level = "CP1"
            track = "CP1"
        elif "premiere annee ensam" in lowered or "première annee ensam" in lowered:
            level = "ENSAM CP1"
            track = "CP1"

        duration = self._duration_from(lowered, updated.duration)
        exercise_count = self._exercise_count_from(lowered) or updated.exercise_count
        section_count = self._section_count_from(lowered) or updated.section_count
        constraints = updated.constraints
        preferences = updated.pedagogical_preferences
        document_format = updated.document_format
        if "beamer" in lowered:
            document_format = "beamer"
            constraints = _append_unique(constraints, "cours Beamer a annoter")
        if "pas encore" in lowered or "sans " in lowered:
            constraints = _append_unique(constraints, text)
        if "progressif" in lowered or "beaucoup d'exemples" in lowered:
            preferences = _append_unique(preferences, text)

        if not outputs and any(word in lowered for word in ("cours", "chapitre")):
            outputs = ("course",)
        task_type = self._task_type(outputs, updated.task_type)
        confidence = min(1.0, updated.confidence + 0.25)
        next_draft = replace(
            updated,
            task_type=task_type,
            subject=subject,
            topic=topic,
            level=level,
            duration=duration,
            outputs=outputs,
            constraints=constraints,
            pedagogical_preferences=preferences,
            document_format=document_format,
            track=track or updated.track,
            exercise_count=exercise_count,
            section_count=section_count,
            unresolved_fields=self.required_missing(
                replace(updated, topic=topic, outputs=outputs, subject=subject, track=track)
            ),
            confidence=confidence,
        )
        return ParsedIntent(intent, confidence), replace(
            next_draft, unresolved_fields=self.required_missing(next_draft)
        )

    def required_missing(self, draft: TaskDraft) -> tuple[str, ...]:
        missing: list[str] = []
        if not draft.topic:
            missing.append("topic")
        if not draft.outputs:
            missing.append("outputs")
        return tuple(missing)

    def _apply_project_defaults(
        self, draft: TaskDraft, project: ProjectContext | None
    ) -> TaskDraft:
        if project is None:
            return draft
        return replace(
            draft,
            subject=draft.subject or project.subject,
            level=draft.level or project.level,
            curriculum=draft.curriculum or project.curriculum,
            track=draft.track or project.track,
            pedagogical_preferences=_append_unique(
                draft.pedagogical_preferences, *project.pedagogical_preferences
            ),
            document_format=draft.document_format or project.document_format,
        )

    def _topic_from(self, original: str, lowered: str) -> str:
        for pattern in _TOPIC_PATTERNS:
            match = pattern.search(original)
            if not match:
                continue
            topic = re.split(r"\b(?:pour|en|avec|de|du|et|,|\.)\b", match.group(1), maxsplit=1)[
                0
            ].strip(" .")
            if topic:
                return topic[0].upper() + topic[1:]
        if "integrales" in lowered:
            return "Intégrales"
        return ""

    @staticmethod
    def _duration_from(lowered: str, current: DurationSpec) -> DurationSpec:
        sessions = current.sessions
        minutes = current.minutes_per_session
        if match := re.search(r"\b(?:en\s+)?(\d+|une|deux|trois|quatre|cinq)\s+seances?", lowered):
            words = {"une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5}
            sessions = words.get(
                match.group(1), int(match.group(1)) if match.group(1).isdigit() else sessions
            )
        if match := re.search(r"\b(\d+)h(\d{1,2})\b", lowered):
            minutes = int(match.group(1)) * 60 + int(match.group(2))
        return DurationSpec(sessions=sessions, minutes_per_session=minutes)

    @staticmethod
    def _exercise_count_from(lowered: str) -> int | None:
        if match := re.search(r"\b(\d{1,2})\s+exercices?\b", lowered):
            return int(match.group(1))
        return None

    @staticmethod
    def _section_count_from(lowered: str) -> int | None:
        if match := re.search(r"\b(\d{1,2})\s+sections?\b", lowered):
            return int(match.group(1))
        return None

    @staticmethod
    def _task_type(outputs: tuple[str, ...], current: str) -> str:
        if len(outputs) > 1:
            return "course_bundle"
        if outputs == ("tutorial",):
            return "td"
        if outputs == ("course",):
            return "course"
        return current
