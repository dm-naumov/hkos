"""HKOS Doctor (DS-017): production-safe проверка консистентности.

Repository (SSOT) == Index (проекция) == Snapshot (состояние).

Проверки (через инжектируемые публичные фасады, без прямого доступа
к Repository/Storage — граница слоёв integration соблюдена):
- campaign consistency:  repository_campaigns == index_campaigns;
- knowledge consistency: repository_knowledge == index_knowledge;
- snapshot consistency:  snapshot counters == repository counters (все типы);
- orphans:               index entity без repository / repository entity без индекса.

CLI: python3 scripts/doctor_cli.py --project <id|name>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from hkos.core.logger import HKOSLogger
from hkos.index import IndexSnapshot

__all__ = ["ConsistencyIssue", "ConsistencyReport", "HkosDoctor"]


class ReposLike(Protocol):
    """Инжектируемый RepositoryManager (граница: без импорта repository)."""

    @property
    def knowledge(self) -> Any: ...

    @property
    def decisions(self) -> Any: ...

    @property
    def artifacts(self) -> Any: ...

    @property
    def campaigns(self) -> Any: ...

    @property
    def projects(self) -> Any: ...


@dataclass
class ConsistencyIssue:
    """Одна проверка doctor (check: PASS/FAIL + причина)."""

    check: str
    status: str
    expected: int = -1
    actual: int = -1
    detail: str = ""

    @property
    def ok(self) -> bool:
        """Статус проверки: True если PASS."""
        return self.status == "PASS"


@dataclass
class ConsistencyReport:
    """Результат проверки проекта (все issues + вердикт)."""

    project_id: str
    issues: list[ConsistencyIssue] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """Итоговый вердикт отчёта (PASS/FAIL)."""
        return "PASS" if all(issue.ok for issue in self.issues) else "FAIL"

    def summary(self) -> str:
        """Текстовое представление отчёта (построчно)."""
        lines = [f"HKOS DOCTOR - project {self.project_id} - {self.verdict}"]
        for issue in self.issues:
            if issue.status == "PASS":
                lines.append(f"  [PASS] {issue.check}")
            else:
                lines.append(
                    f"  [FAIL] {issue.check}: expected={issue.expected} "
                    f"actual={issue.actual} - {issue.detail}"
                )
        return "\n".join(lines)


class HkosDoctor:
    """Проверка Repository == Index == Snapshot (публичный API, DS-017)."""

    def __init__(
        self,
        repos: ReposLike,
        index: Any,
        snapshots: Any,
        store: Any,
        logger: HKOSLogger | None = None,
    ) -> None:
        """Инициализация (все зависимости инжектируются)."""
        self._repos = repos
        self._index = index
        self._snapshots = snapshots
        self._store = store
        self._logger = logger or HKOSLogger()

    def _check_counts(
        self, label: str, repository_count: int, index_count: int
    ) -> ConsistencyIssue:
        """Сравнить счётчики repository и index (PASS/FAIL)."""
        if repository_count == index_count:
            return ConsistencyIssue(
                check=label, status="PASS",
                expected=repository_count, actual=index_count)
        return ConsistencyIssue(
            check=label, status="FAIL",
            expected=repository_count, actual=index_count,
            detail="Index projection desync (incident 001 family); "
                   "fix: index.update/rebuild")

    def check(self, project_id: str) -> ConsistencyReport:
        """Полная проверка проекта (4 группы проверок)."""
        report = ConsistencyReport(project_id=project_id)

        # 1) Campaign consistency: repository == index
        repo_campaigns = self._repos.campaigns.count(project_id)
        index_campaigns = int(self._index.statistics(project_id).get(
            "campaigns", -1))
        report.issues.append(self._check_counts(
            "campaign consistency (repository == index)",
            repo_campaigns, index_campaigns))

        # 2) Knowledge consistency: repository == index
        repo_knowledge = self._repos.knowledge.count(project_id)
        index_knowledge = int(self._index.statistics(project_id).get(
            "knowledge", -1))
        report.issues.append(self._check_counts(
            "knowledge consistency (repository == index)",
            repo_knowledge, index_knowledge))

        # 3) Snapshot consistency: counters == repository counters
        snapshot = self._snapshots.load(project_id)
        if snapshot is None:
            report.issues.append(ConsistencyIssue(
                check="snapshot consistency", status="FAIL", detail=(
                    "snapshot missing (create(force=True) required)")))
        else:
            for entity_type, repo in (
                ("knowledge", self._repos.knowledge),
                ("decisions", self._repos.decisions),
                ("campaigns", self._repos.campaigns),
                ("artifacts", self._repos.artifacts),
            ):
                expected = repo.count(project_id)
                actual = int(snapshot.statistics.get(entity_type, -1))
                ok = expected == actual
                report.issues.append(ConsistencyIssue(
                    check=f"snapshot {entity_type} == repository",
                    status="PASS" if ok else "FAIL",
                    expected=expected, actual=actual,
                    detail=("snapshot stale; create(force=True) to refresh"
                            if not ok else "")))

        # 4) Orphans: index без repository / repository без индекса.
        # Проект исключён: корневой контейнер индексируется лениво (build/rebuild)
        # и не может «потеряться»; orphans считаются по содержательным типам.
        index_ids = set(IndexSnapshot(self._store, project_id).ids())
        index_ids.discard(project_id)  # проект — корневой контейнер
        repo_ids: set[str] = set()
        for repo in (
            self._repos.knowledge,
            self._repos.decisions,
            self._repos.artifacts,
            self._repos.campaigns,
        ):
            repo_ids.update(entity.id for entity in repo.list(project_id))
        index_without_repo = index_ids - repo_ids
        repo_without_index = repo_ids - index_ids
        if index_without_repo:
            report.issues.append(ConsistencyIssue(
                check="orphans: index entity without repository",
                status="FAIL", expected=0, actual=len(index_without_repo),
                detail=f"ids: {sorted(index_without_repo)[:5]}"))
        else:
            report.issues.append(ConsistencyIssue(
                check="orphans: index entity without repository",
                status="PASS", expected=0, actual=0))
        if repo_without_index:
            report.issues.append(ConsistencyIssue(
                check="orphans: repository entity without index",
                status="FAIL", expected=0, actual=len(repo_without_index),
                detail=f"ids: {sorted(repo_without_index)[:5]}"))
        else:
            report.issues.append(ConsistencyIssue(
                check="orphans: repository entity without index",
                status="PASS", expected=0, actual=0))

        return report
