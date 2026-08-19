"""HKOS Librarian (DS-006, IP-006)
===============================
Librarian — единственная точка принятия решений о жизненном цикле
Knowledge. Оркестратор: классификация, канонизация, объединение,
обнаружение конфликтов, confidence, история, статусы.

Librarian НЕ является: хранилищем, поисковой системой, интеллектуальным
агентом. Запрещены: семантический поиск, embedding, similarity, изменение
индекса, выбор знаний для Context Builder, решение «какое знание лучше»,
изменение Campaign/Project (IP-006 §1, §3).

Работает ТОЛЬКО через RepositoryManager.knowledge (IP-006 §9).
"""

import uuid

from hkos.core.logger import HKOSLogger
from hkos.repository.exceptions import RepositoryNotFoundError
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.models import Knowledge, KnowledgeHistoryEntry
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian.confidence_engine import ConfidenceEngine
from hkos.services.librarian.conflict_detector import ConflictDetector
from hkos.services.librarian.exceptions import (
    KnowledgeNotFoundError,
    LibrarianError,
)
from hkos.services.librarian.knowledge_classifier import KnowledgeClassifier
from hkos.services.librarian.knowledge_history import (
    EVENT_ARCHIVED,
    EVENT_CANONICALIZED,
    EVENT_CONFIDENCE_CHANGED,
    EVENT_CONFLICT_DETECTED,
    EVENT_CREATED,
    EVENT_REJECTED,
    EVENT_RESTORED,
    EVENT_UPDATED,
    KnowledgeHistory,
)
from hkos.services.librarian.knowledge_merger import KnowledgeMerger
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_CANONICAL,
    KNOWLEDGE_STATUS_CONFLICT,
    KNOWLEDGE_STATUS_NEW,
    KNOWLEDGE_STATUS_REJECTED,
    KNOWLEDGE_STATUS_VERIFIED,
    KnowledgeStatus,
)
from hkos.services.project_validator import ValidationResult

__all__ = ["Librarian"]


class Librarian:
    """Оркестратор жизненного цикла Knowledge (единственная точка изменений).

    Публичный API (ровно эти методы):
        register, update, canonicalize, merge, archive, restore, reject,
        detect_conflicts, recalculate_confidence, history, validate
    """

    def __init__(
        self,
        repositories: RepositoryManager,
        logger: HKOSLogger,
    ) -> None:
        """Инициализация Librarian.

        Args:
            repositories: RepositoryManager — доступ через .knowledge.
            logger: HKOSLogger (Sprint 1) — системное журналирование.

        """
        self._repositories = repositories
        self._knowledge: KnowledgeRepository = repositories.knowledge
        self._logger = logger

    # --- Внутренние операции ---

    def _load(self, project_id: str, knowledge_id: str) -> Knowledge:
        """Загрузить Knowledge или поднять KnowledgeNotFoundError."""
        try:
            return self._knowledge.load(project_id, knowledge_id)
        except RepositoryNotFoundError as e:
            raise KnowledgeNotFoundError(
                f"Knowledge not found: {knowledge_id} in project {project_id}"
            ) from e

    def _save(self, knowledge: Knowledge) -> Knowledge:
        """Сохранить Knowledge через Repository."""
        return self._knowledge.update(knowledge)

    def _transition(self, knowledge: Knowledge, target: str) -> Knowledge:
        """Проверить и применить переход статуса (KnowledgeStatus)."""
        knowledge.status = KnowledgeStatus.transition(
            knowledge.status, target
        )
        return knowledge

    def _log(self, message: str) -> None:
        """Системный журнал."""
        self._logger.info(message)

    # --- Публичный API ---

    def register(
        self,
        project_id: str,
        knowledge: Knowledge,
        category: str | None = None,
    ) -> Knowledge:
        """Зарегистрировать новое Knowledge.

        Классификация категории (если не задана), статус NEW,
        confidence рассчитывается, история: Created.

        Raises:
            LibrarianError: Если knowledge.id уже занят.

        """
        if knowledge.id and self._knowledge.exists(project_id, knowledge.id):
            raise LibrarianError(
                f"Knowledge already exists: {knowledge.id}"
            )
        knowledge.id = knowledge.id or str(uuid.uuid4())
        knowledge.project = project_id
        knowledge.category = category or KnowledgeClassifier.classify(knowledge)
        if not KnowledgeClassifier.is_valid(knowledge.category):
            raise LibrarianError(
                f"Invalid category: {knowledge.category!r}"
            )
        knowledge.status = KNOWLEDGE_STATUS_NEW
        knowledge.confidence = ConfidenceEngine.calculate(knowledge)
        KnowledgeHistory.append(knowledge, EVENT_CREATED)
        saved = self._knowledge.save(knowledge)
        self._log(f"KnowledgeRegistered: {knowledge.id} ({knowledge.category})")
        return saved

    def update(
        self,
        project_id: str,
        knowledge: Knowledge,
    ) -> Knowledge:
        """Обновить Knowledge.

        Неизменяемые поля сохраняются: id, created_at, category (после
        канонизации), parent_ids, canonical_id, history. Confidence
        пересчитывается автоматически.

        Raises:
            KnowledgeNotFoundError: Если знание отсутствует.

        """
        if not knowledge.id:
            raise KnowledgeNotFoundError("update requires knowledge with id")
        existing = self._load(project_id, knowledge.id)
        # Валидация замкнутого словаря категорий (Post-Audit Refinement).
        if not KnowledgeClassifier.is_valid(knowledge.category):
            raise LibrarianError(
                f"Invalid category: {knowledge.category!r} "
                f"(closed vocabulary, Post-Audit Refinement)"
            )
        if KnowledgeStatus.is_canonical(existing):
            knowledge.category = existing.category  # категория неизменяема
        knowledge.id = existing.id
        knowledge.project = existing.project
        knowledge.created_at = existing.created_at
        knowledge.parent_ids = existing.parent_ids
        knowledge.canonical_id = existing.canonical_id
        knowledge.history = existing.history
        knowledge.confidence = ConfidenceEngine.calculate(knowledge)
        KnowledgeHistory.append(knowledge, EVENT_UPDATED)
        saved = self._knowledge.update(knowledge)
        self._log(f"KnowledgeUpdated: {knowledge.id}")
        return saved

    def canonicalize(self, project_id: str, knowledge_id: str) -> Knowledge:
        """Канонизировать Knowledge.

        Канонизация включает верификацию: NEW -> VERIFIED -> CANONICAL
        (отдельного публичного метода verify() в API DS-006 нет).
        Из VERIFIED -> CANONICAL напрямую.
        """
        knowledge = self._load(project_id, knowledge_id)
        # Идемпотентность (Post-Audit Refinement): повторная канонизация
        # уже канонического знания — no-op, без исключения.
        if KnowledgeStatus.is_canonical(knowledge):
            return knowledge
        if KnowledgeStatus.is_new(knowledge):
            self._transition(knowledge, KNOWLEDGE_STATUS_VERIFIED)
        self._transition(knowledge, KNOWLEDGE_STATUS_CANONICAL)
        KnowledgeHistory.append(knowledge, EVENT_CANONICALIZED)
        saved = self._save(knowledge)
        self._log(f"KnowledgeCanonicalized: {knowledge_id}")
        return saved

    def merge(
        self,
        project_id: str,
        first_id: str,
        second_id: str,
        reason: str = "",
    ) -> Knowledge:
        """Объединить два Knowledge в новое Canonical Knowledge.

        Исходные A и B не изменяются (immutability, IP-006 §6).
        Создаётся C (новый UUID, CANONICAL, parent_ids=[A, B]).

        Raises:
            KnowledgeNotFoundError: Если источник отсутствует.

        """
        if first_id == second_id:
            raise LibrarianError(
                "merge requires two distinct Knowledge (self-merge is meaningless)"
            )
        a = self._load(project_id, first_id)
        b = self._load(project_id, second_id)
        merged = KnowledgeMerger.merge(a, b, reason=reason)
        merged.project = project_id
        merged.confidence = ConfidenceEngine.calculate(merged)
        saved = self._knowledge.save(merged)
        self._log(f"KnowledgeMerged: {merged.id} (from {first_id}, {second_id})")
        return saved

    def archive(self, project_id: str, knowledge_id: str) -> Knowledge:
        """Архивировать Knowledge (-> ARCHIVED)."""
        knowledge = self._load(project_id, knowledge_id)
        self._transition(knowledge, KNOWLEDGE_STATUS_ARCHIVED)
        KnowledgeHistory.append(knowledge, EVENT_ARCHIVED)
        saved = self._save(knowledge)
        self._log(f"KnowledgeArchived: {knowledge_id}")
        return saved

    def restore(self, project_id: str, knowledge_id: str) -> Knowledge:
        """Восстановить Knowledge (ARCHIVED -> VERIFIED)."""
        knowledge = self._load(project_id, knowledge_id)
        self._transition(knowledge, KNOWLEDGE_STATUS_VERIFIED)
        KnowledgeHistory.append(knowledge, EVENT_RESTORED)
        saved = self._save(knowledge)
        self._log(f"KnowledgeRestored: {knowledge_id}")
        return saved

    def reject(self, project_id: str, knowledge_id: str) -> Knowledge:
        """Отклонить Knowledge (NEW/CONFLICT -> REJECTED)."""
        knowledge = self._load(project_id, knowledge_id)
        self._transition(knowledge, KNOWLEDGE_STATUS_REJECTED)
        KnowledgeHistory.append(knowledge, EVENT_REJECTED)
        saved = self._save(knowledge)
        self._log(f"KnowledgeRejected: {knowledge_id}")
        return saved

    def detect_conflicts(
        self,
        project_id: str,
        knowledge_id: str,
    ) -> list[Knowledge]:
        """Обнаружить конфликты Knowledge с остальными знаниями проекта.

        Если конфликт найден — статус Knowledge переводится в CONFLICT
        (DS-006 §11). Никакое знание не удаляется (IP-006 §14).

        Returns:
            Список конфликтующих Knowledge.

        """
        knowledge = self._load(project_id, knowledge_id)
        candidates = self._knowledge.list(project_id)
        result = ConflictDetector.detect(knowledge, candidates)
        if result.conflict_exists:
            if knowledge.status in (
                KNOWLEDGE_STATUS_NEW,
                KNOWLEDGE_STATUS_VERIFIED,
                KNOWLEDGE_STATUS_CANONICAL,
            ):
                self._transition(knowledge, KNOWLEDGE_STATUS_CONFLICT)
            KnowledgeHistory.append(
                knowledge, EVENT_CONFLICT_DETECTED,
                details="; ".join(k.id for k in result.conflicting),
            )
            saved = self._save(knowledge)
            self._log(f"KnowledgeConflict: {knowledge_id} (conflict found)")
            return [k for k in result.conflicting if k.id != saved.id]
        self._log(f"KnowledgeConflict: {knowledge_id} (no conflicts)")
        return []

    def recalculate_confidence(
        self, project_id: str, knowledge_id: str
    ) -> Knowledge:
        """Пересчитать confidence из инженерных факторов (никогда вручную)."""
        knowledge = self._load(project_id, knowledge_id)
        new_confidence = ConfidenceEngine.calculate(knowledge)
        if new_confidence != knowledge.confidence:
            knowledge.confidence = new_confidence
            KnowledgeHistory.append(
                knowledge, EVENT_CONFIDENCE_CHANGED,
                details=f"confidence={new_confidence}",
            )
            saved = self._save(knowledge)
            self._log(f"ConfidenceChanged: {knowledge_id} -> {new_confidence}")
            return saved
        return knowledge

    def history(
        self, project_id: str, knowledge_id: str
    ) -> list[KnowledgeHistoryEntry]:
        """История Knowledge (только чтение, append-only)."""
        knowledge = self._load(project_id, knowledge_id)
        return KnowledgeHistory.entries(knowledge)

    def validate(self, project_id: str, knowledge_id: str) -> ValidationResult:
        """Проверить Knowledge (структура/статус/категория)."""
        errors: list[str] = []
        warnings: list[str] = []
        if not self._knowledge.exists(project_id, knowledge_id):
            return ValidationResult(
                valid=False,
                errors=[f"Knowledge not found: {knowledge_id}"],
            )
        try:
            knowledge = self._load(project_id, knowledge_id)
        except KnowledgeNotFoundError as e:
            return ValidationResult(valid=False, errors=[str(e)])
        if not knowledge.title:
            errors.append("Knowledge title is empty (mandatory field)")
        if not knowledge.category:
            warnings.append("Knowledge category is not set")
        elif not KnowledgeClassifier.is_valid(knowledge.category):
            errors.append(f"Invalid category: {knowledge.category!r}")
        if not KnowledgeStatus.is_valid(knowledge.status):
            errors.append(f"Invalid status: {knowledge.status!r}")
        if not knowledge.history:
            warnings.append("Knowledge history is empty")
        result = ValidationResult(valid=not errors, errors=errors, warnings=warnings)
        if not result.valid:
            self._logger.warning(f"Validation Failed: {knowledge_id}: {result.errors}")
        return result
