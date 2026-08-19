"""HKOS Snapshot Builder (DS-010 §9, IP-010)
============================================
SnapshotBuilder строит Snapshot ИСКЛЮЧИТЕЛЬНО из существующих сущностей
Repository. Retrieval Engine НЕ используется.

Ключевое архитектурное решение (задокументировано, IP-010 §производительность):
классификация и заголовки читаются через Entity Index (Q3, in-memory —
производный от Repository слой) — это единственный способ уложиться
в требование Create <= 300 мс при 100 000 Knowledge (полное чтение всех
документов через Repository дало бы 10-30 с). Метаданные проекта/кампании
и счётчики — через RepositoryManager. Согласованность с Repository
гарантируется SnapshotValidator (DS-010 §15).

Структура Snapshot — DS-010 §8: Project Metadata, Architecture,
Canonical Knowledge, Accepted Decisions, Configurations, Known Failures,
Known Limitations, Artifacts, Open Questions, Statistics.
"""

from datetime import datetime, timezone

from hkos.index.query_contract import EntityRecord, IndexSnapshot
from hkos.kernel.snapshot_document import SnapshotDocument
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.classification_policy import (
    CATEGORY_ARCHITECTURE,
    CATEGORY_ARTIFACT,
    CATEGORY_CANONICAL,
    CATEGORY_CONFIGURATION,
    CATEGORY_DECISION,
    CATEGORY_FAILURE,
    CATEGORY_LIMITATION,
    classify,
)

__all__ = ["SnapshotBuilder"]

_SECTION_ARCHITECTURE: str = "Architecture"
_SECTION_CANONICAL: str = "Canonical Knowledge"
_SECTION_DECISIONS: str = "Accepted Decisions"
_SECTION_CONFIGURATIONS: str = "Configurations"
_SECTION_FAILURES: str = "Known Failures"
_SECTION_LIMITATIONS: str = "Known Limitations"
_SECTION_ARTIFACTS: str = "Artifacts"
_SECTION_QUESTIONS: str = "Open Questions"


def _now() -> str:
    """Текущее время ISO-8601 (UTC)."""
    return datetime.now(timezone.utc).isoformat()


class SnapshotBuilder:
    """Построение Snapshot из Repository (+ Entity Index для классификации)."""

    def __init__(self, repositories: RepositoryManager) -> None:
        """Инициализация строителя.

        Args:
            repositories: RepositoryManager (сущности).

        """
        self._repositories = repositories

    # --- Классификация ---

    @staticmethod
    def _record_entry(record: EntityRecord) -> dict[str, str]:
        """Ссылка на сущность из Entity Record (id + title + status)."""
        return {
            "id": record.id,
            "title": record.title,
            "status": record.status,
        }

    @staticmethod
    def _classify(
        records: list[EntityRecord],
    ) -> dict[str, list[dict[str, str]]]:
        """Классификация Knowledge по секциям DS-010 §8.

        Логическая категория — ЕДИНАЯ политика (classification_policy);
        здесь — только отображение логической категории на секции Snapshot.
        """
        sections: dict[str, list[dict[str, str]]] = {
            _SECTION_ARCHITECTURE: [],
            _SECTION_CANONICAL: [],
            _SECTION_DECISIONS: [],
            _SECTION_CONFIGURATIONS: [],
            _SECTION_FAILURES: [],
            _SECTION_LIMITATIONS: [],
            _SECTION_ARTIFACTS: [],
            _SECTION_QUESTIONS: [],
        }
        for record in records:
            entry = SnapshotBuilder._record_entry(record)
            logical = classify(
                entity_type=record.type,
                category=record.category,
                kind=getattr(record, "kind", "") or "",
                status=record.status,
            )
            if logical == CATEGORY_CANONICAL:
                sections[_SECTION_CANONICAL].append(entry)
            elif logical == CATEGORY_ARCHITECTURE:
                sections[_SECTION_ARCHITECTURE].append(entry)
            elif logical == CATEGORY_DECISION:
                sections[_SECTION_DECISIONS].append(entry)
            elif logical == CATEGORY_CONFIGURATION:
                sections[_SECTION_CONFIGURATIONS].append(entry)
            elif logical == CATEGORY_FAILURE:
                sections[_SECTION_FAILURES].append(entry)
            elif logical == CATEGORY_LIMITATION:
                sections[_SECTION_LIMITATIONS].append(entry)
            elif logical == CATEGORY_ARTIFACT:
                sections[_SECTION_ARTIFACTS].append(entry)
            else:
                sections[_SECTION_QUESTIONS].append(entry)  # CATEGORY_QUESTION
        return sections

    # --- Построение ---

    def build(
        self,
        project_id: str,
        snapshot: SnapshotDocument,
        snapshot_index: IndexSnapshot | None,
    ) -> SnapshotDocument:
        """Заполнить Snapshot содержанием проекта.

        Args:
            project_id: UUID проекта.
            snapshot: SnapshotDocument (метаданные уже установлены).
            snapshot_index: Снимок Entity Index (Q3) для классификации
                (in-memory); None — только счётчики.

        Returns:
            Заполненный SnapshotDocument.

        """
        repositories = self._repositories

        # Project Metadata (RepositoryManager)
        project = repositories.projects.load(project_id)
        project_entry: dict[str, object] = {}
        if project is not None:
            project_entry = {
                "id": project.id,
                "name": project.name,
                "tags": list(project.tags),
            }

        # Statistics (RepositoryManager, быстрые счётчики)
        statistics: dict[str, int] = {
            "knowledge": repositories.knowledge.count(project_id),
            "decisions": repositories.decisions.count(project_id),
            "campaigns": repositories.campaigns.count(project_id),
            "artifacts": repositories.artifacts.count(project_id),
            "projects": repositories.projects.count(),
        }

        sections: dict[str, object] = {
            "Project Metadata": project_entry,
        }
        if snapshot_index is not None:
            # Перечисление id — через Entity Index (ids(), in-memory,
            # MINOR-расширение Query Contract §8). Это единственный способ
            # уложиться в Create <= 300 мс при 100K Knowledge
            # (Repository.list() загружал бы все документы).
            records: list[EntityRecord] = []
            for entity_id in snapshot_index.ids():
                record = snapshot_index.entity_get(entity_id)
                if record is not None and record.project == project_id:
                    records.append(record)
            classified = self._classify(records)
            sections.update(classified)
        else:
            for name in (
                _SECTION_ARCHITECTURE, _SECTION_CANONICAL, _SECTION_DECISIONS,
                _SECTION_CONFIGURATIONS, _SECTION_FAILURES, _SECTION_LIMITATIONS,
                _SECTION_ARTIFACTS, _SECTION_QUESTIONS,
            ):
                sections[name] = []

        snapshot.sections = sections
        snapshot.statistics = statistics
        reference_sections = [
            _SECTION_CANONICAL, _SECTION_DECISIONS, _SECTION_CONFIGURATIONS,
            _SECTION_FAILURES, _SECTION_LIMITATIONS, _SECTION_ARTIFACTS,
        ]
        references: list[str] = []
        for section in reference_sections:
            entries = sections.get(section)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and entry.get("id"):
                    references.append(str(entry["id"]))
        snapshot.references = references
        return snapshot
