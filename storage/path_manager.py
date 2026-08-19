"""HKOS Path Manager
=================
Построение путей файловой структуры HKOS (DS-002).

Path Manager отвечает ИСКЛЮЧИТЕЛЬНО за построение путей.
Запрещается вручную конструировать пути строками — только через PathManager.
Никакой работы с файловой системой здесь не выполняется.
"""

import os

from hkos.storage.exceptions import StoragePathError

__all__ = ["PathManager"]


class PathManager:
    """Строит пути рабочей области HKOS по спецификации HKOS-02/DS-002.

    Все компоненты пути (имена проектов, кампаний, каталогов) валидируются:
    запрещены пустые имена, разделители путей и переходы на уровень выше.
    """

    # Каталоги верхнего уровня рабочей области (HKOS-02).
    ROOT_PROJECTS: str = "projects"
    ROOT_GLOBAL: str = "global"

    # Имя файла метаданных проекта (HKOS-08).
    PROJECT_FILE: str = "project.json"

    # Каталоги внутри проекта (HKOS-02, раздел 5).
    PROJECT_CAMPAIGNS: str = "campaigns"
    PROJECT_KNOWLEDGE: str = "knowledge"
    PROJECT_SNAPSHOTS: str = "snapshots"
    PROJECT_DECISIONS: str = "decisions"
    PROJECT_ARTIFACTS: str = "artifacts"
    PROJECT_INDEXES: str = "indexes"

    # Имя файла метаданных кампании.
    CAMPAIGN_FILE: str = "campaign.json"

    @staticmethod
    def _validate_component(component: str, what: str) -> None:
        """Проверить, что компонент является допустимым именем пути.

        Args:
            component: Проверяемое имя (проект, кампания и т.п.).
            what: Название сущности для сообщения об ошибке.

        Raises:
            StoragePathError: Если имя пустое, содержит разделители
                или является переходом на уровень выше.
        """
        if not component:
            raise StoragePathError(f"{what} name must not be empty")
        if component in (".", ".."):
            raise StoragePathError(f"Invalid {what} name: '{component}'")
        if "/" in component or "\\" in component:
            raise StoragePathError(
                f"{what} name must not contain path separators: '{component}'"
            )

    @staticmethod
    def workspace(root: str) -> str:
        """Вернуть нормализованный путь рабочей области HKOS."""
        return os.path.normpath(root)

    @staticmethod
    def project(root: str, project_name: str) -> str:
        """Вернуть путь каталога проекта: <root>/projects/<project>."""
        PathManager._validate_component(project_name, "Project")
        return os.path.join(
            PathManager.workspace(root),
            PathManager.ROOT_PROJECTS,
            project_name,
        )

    @staticmethod
    def project_file(root: str, project_name: str) -> str:
        """Вернуть путь файла метаданных проекта: <project>/project.json."""
        return os.path.join(
            PathManager.project(root, project_name),
            PathManager.PROJECT_FILE,
        )

    @staticmethod
    def campaign(root: str, project_name: str, campaign_name: str) -> str:
        """Вернуть путь кампании: <project>/campaigns/<campaign>."""
        PathManager._validate_component(campaign_name, "Campaign")
        return os.path.join(
            PathManager.project(root, project_name),
            PathManager.PROJECT_CAMPAIGNS,
            campaign_name,
        )

    @staticmethod
    def knowledge(root: str, project_name: str) -> str:
        """Вернуть путь хранилища знаний проекта: <project>/knowledge."""
        return os.path.join(
            PathManager.project(root, project_name),
            PathManager.PROJECT_KNOWLEDGE,
        )

    @staticmethod
    def snapshot(root: str, project_name: str) -> str:
        """Вернуть путь каталога снимков проекта: <project>/snapshots."""
        return os.path.join(
            PathManager.project(root, project_name),
            PathManager.PROJECT_SNAPSHOTS,
        )

    @staticmethod
    def global_dir(root: str) -> str:
        """Вернуть путь каталога глобальных знаний: <root>/global."""
        return os.path.join(PathManager.workspace(root), PathManager.ROOT_GLOBAL)

    @staticmethod
    def projects(root: str) -> str:
        """Вернуть путь каталога проектов: <root>/projects."""
        return os.path.join(PathManager.workspace(root), PathManager.ROOT_PROJECTS)

    @staticmethod
    def campaigns(root: str, project_name: str) -> str:
        """Вернуть путь каталога кампаний проекта: <project>/campaigns."""
        return os.path.join(
            PathManager.project(root, project_name),
            PathManager.PROJECT_CAMPAIGNS,
        )

    @staticmethod
    def campaign_file(
        root: str, project_name: str, campaign_name: str
    ) -> str:
        """Вернуть путь файла кампании: <campaign>/campaign.json."""
        return os.path.join(
            PathManager.campaign(root, project_name, campaign_name),
            PathManager.CAMPAIGN_FILE,
        )

    @staticmethod
    def decisions(root: str, project_name: str) -> str:
        """Вернуть путь каталога решений проекта: <project>/decisions."""
        return os.path.join(
            PathManager.project(root, project_name),
            PathManager.PROJECT_DECISIONS,
        )

    @staticmethod
    def artifacts(root: str, project_name: str) -> str:
        """Вернуть путь каталога артефактов проекта: <project>/artifacts."""
        return os.path.join(
            PathManager.project(root, project_name),
            PathManager.PROJECT_ARTIFACTS,
        )

    @staticmethod
    def knowledge_file(root: str, project_name: str, object_id: str) -> str:
        """Вернуть путь файла знания: <project>/knowledge/<id>.json."""
        PathManager._validate_component(object_id, "Knowledge id")
        return os.path.join(
            PathManager.knowledge(root, project_name), f"{object_id}.json"
        )

    @staticmethod
    def decision_file(root: str, project_name: str, decision_id: str) -> str:
        """Вернуть путь файла решения: <project>/decisions/<id>.json."""
        PathManager._validate_component(decision_id, "Decision id")
        return os.path.join(
            PathManager.decisions(root, project_name), f"{decision_id}.json"
        )

    @staticmethod
    def artifact_file(root: str, project_name: str, artifact_id: str) -> str:
        """Вернуть путь файла артефакта: <project>/artifacts/<id>.json."""
        PathManager._validate_component(artifact_id, "Artifact id")
        return os.path.join(
            PathManager.artifacts(root, project_name), f"{artifact_id}.json"
        )

    @staticmethod
    def indexes(root: str, project_name: str) -> str:
        """Вернуть путь каталога индексов проекта: <project>/indexes."""
        return os.path.join(
            PathManager.project(root, project_name),
            PathManager.PROJECT_INDEXES,
        )

    @staticmethod
    def index_file(root: str, project_name: str, index_name: str) -> str:
        """Вернуть путь файла индекса: <project>/indexes/<name>.idx.

        Args:
            index_name: Имя индекса (keyword, tags, entities, relations,
                statistics).
        """
        PathManager._validate_component(index_name, "Index name")
        return os.path.join(
            PathManager.indexes(root, project_name), f"{index_name}.idx"
        )
