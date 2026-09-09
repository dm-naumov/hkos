"""Concurrency tests for BaseRepository (KI-008).

Проверяем:
- поле _rev инкрементируется при каждом сохранении;
- оптимистичная блокировка через expected_revision;
- KEY_VERSION (версия формата HKOS-08) никогда не изменяется.
"""

from pathlib import Path
from typing import Any

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.exceptions import RepositoryConcurrencyError
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.models import Knowledge
from hkos.storage import StorageEngine

_REVISION_KEY = "_rev"


class TestBaseRepositoryConcurrency:
    """KI-008: revision counter и оптимистическая блокировка в BaseRepository."""

    def _repo(self, tmp_path: Path) -> tuple[KnowledgeRepository, str]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repo = KnowledgeRepository(engine, engine.json_store)
        repo.storage.mkdir(
            repo.storage.path_manager.project(engine.root, "proj-1")
        )
        return repo, "proj-1"

    def _raw_doc(self, repo: KnowledgeRepository, project: str, oid: str) -> dict[str, Any]:
        """Read the raw JSON envelope from disk without going through _from_data."""
        path = repo._file_path(project, oid)
        return repo.storage.read_json(path)

    # ------------------------------------------------------------------
    # _rev инкрементирование
    # ------------------------------------------------------------------

    def test_rev_starts_at_one_after_create(self, tmp_path: Path) -> None:
        """_rev равен 1 после первого создания."""
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="A"))
        doc = self._raw_doc(repo, project, k.id)
        assert doc[_REVISION_KEY] == 1

    def test_rev_increments_on_each_save(self, tmp_path: Path) -> None:
        """save() увеличивает _rev на 1 при каждом вызове."""
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="B"))

        k.title = "B2"
        repo.save(k)
        doc = self._raw_doc(repo, project, k.id)
        assert doc[_REVISION_KEY] == 2

        k.title = "B3"
        repo.save(k)
        doc = self._raw_doc(repo, project, k.id)
        assert doc[_REVISION_KEY] == 3

    def test_rev_increments_on_update(self, tmp_path: Path) -> None:
        """update() тоже инкрементирует _rev."""
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="C"))
        assert self._raw_doc(repo, project, k.id)[_REVISION_KEY] == 1

        k.confidence = 80
        repo.update(k)
        assert self._raw_doc(repo, project, k.id)[_REVISION_KEY] == 2

    # ------------------------------------------------------------------
    # get_revision
    # ------------------------------------------------------------------

    def test_get_revision_reflects_current_rev(self, tmp_path: Path) -> None:
        """get_revision() возвращает текущее значение _rev."""
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="D"))
        assert repo.get_revision(project, k.id) == 1

        k.title = "D2"
        repo.save(k)
        assert repo.get_revision(project, k.id) == 2

    # ------------------------------------------------------------------
    # Оптимистическая блокировка
    # ------------------------------------------------------------------

    def test_update_succeeds_with_correct_expected_revision(self, tmp_path: Path) -> None:
        """update(…, expected_revision=N) проходит, если N совпадает с текущей."""
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="E"))
        rev = repo.get_revision(project, k.id)  # == 1

        k.confidence = 50
        repo.update(k, expected_revision=rev)  # должен пройти

        loaded = repo.load(project, k.id)
        assert loaded.confidence == 50
        assert repo.get_revision(project, k.id) == 2

    def test_update_raises_on_stale_expected_revision(self, tmp_path: Path) -> None:
        """Сталый expected_revision → RepositoryConcurrencyError."""
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="F"))

        # Симулируем параллельную запись: документ обновляется…
        k.confidence = 30
        repo.update(k)  # _rev становится 2

        # … а мы пытаемся записать с устаревшей ревизией 1
        k.confidence = 99
        with pytest.raises(RepositoryConcurrencyError):
            repo.update(k, expected_revision=1)

    def test_update_without_expected_revision_skips_check(self, tmp_path: Path) -> None:
        """expected_revision=None (по умолчанию) не делает проверку — обратная совместимость."""
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="G"))

        k.confidence = 10
        repo.update(k)  # _rev = 2

        k.confidence = 20
        repo.update(k, expected_revision=None)  # явно: None = нет проверки

        loaded = repo.load(project, k.id)
        assert loaded.confidence == 20

    # ------------------------------------------------------------------
    # Инвариант HKOS-08
    # ------------------------------------------------------------------

    def test_key_version_never_increments(self, tmp_path: Path) -> None:
        """KEY_VERSION (версия формата конверта) никогда не изменяется.

        Если version > 1, validate_envelope() бросит StorageMigrationRequired.
        Поэтому KEY_VERSION всегда должен оставаться == 1 вне зависимости от
        количества сохранений.
        """
        repo, project = self._repo(tmp_path)
        k = repo.create(Knowledge(project=project, title="H"))

        for i in range(5):
            k.confidence = i * 10
            repo.save(k)

        doc = self._raw_doc(repo, project, k.id)
        json_store = repo._json
        assert doc[json_store.KEY_VERSION] == 1, (
            f"KEY_VERSION изменился: {doc[json_store.KEY_VERSION]!r}. "
            "KEY_VERSION — версия формата, а не счётчик ревизий."
        )
        # Счётчик ревизий должен быть > 1
        assert doc[_REVISION_KEY] > 1
