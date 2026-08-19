"""Unit tests for QueryParser (DS-008 §8)."""

from hkos.core.config import ConfigLoader
from hkos.retrieval.query_parser import QueryParser


def _parser() -> QueryParser:
    cfg = ConfigLoader(profile="development")
    cfg.load()
    return QueryParser(cfg)


class TestQueryParser:
    """Детерминированный анализ текста без I/O."""

    def test_project_hint(self) -> None:
        parsed = _parser().parse("Исправить маршрутизацию UDP в OpenWrt")
        assert parsed.project_hint == "OpenWrt"

    def test_phoenix_hint(self) -> None:
        parsed = _parser().parse("подобрать аналог Phoenix Contact")
        assert parsed.project_hint == "Phoenix Contact"

    def test_topic_detection(self) -> None:
        parsed = _parser().parse("настроить tproxy в OpenWrt")
        assert parsed.topic == "tproxy"

    def test_entities_detection(self) -> None:
        parsed = _parser().parse("udp tproxy nftables")
        assert "udp" in parsed.entities
        assert "tproxy" in parsed.entities

    def test_keywords_extraction(self) -> None:
        parsed = _parser().parse("исправить маршрутизацию")
        assert "исправить" in parsed.keywords
        assert "маршрутизацию" in parsed.keywords

    def test_task_type(self) -> None:
        parsed = _parser().parse("почему не работает udp")
        assert parsed.task_type == "diagnostics"

    def test_task_type_implementation(self) -> None:
        parsed = _parser().parse("реализовать tproxy")
        assert parsed.task_type == "implementation"

    def test_include_history_constraint(self) -> None:
        parsed = _parser().parse("показать историю udp")
        assert parsed.include_history is True

    def test_no_history_by_default(self) -> None:
        parsed = _parser().parse("udp routing")
        assert parsed.include_history is False

    def test_campaign_hint(self) -> None:
        parsed = _parser().parse("результаты кампании tproxy")
        assert parsed.campaign_hint == "tproxy"

    def test_deterministic(self) -> None:
        parser = _parser()
        a = parser.parse("udp tproxy в OpenWrt")
        b = parser.parse("udp tproxy в OpenWrt")
        assert a.as_dict() == b.as_dict()

    def test_no_io_access(self) -> None:
        """Парсер не обращается к Repository/Index (чистый текст)."""
        import inspect

        source = inspect.getsource(QueryParser)
        assert "repository" not in source.lower()
        assert "index" not in source.lower() or "retrieval.parser" in source
