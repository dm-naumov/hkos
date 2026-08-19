"""Unit tests for TokenEstimator (DS-009 §12)."""

from hkos.context.token_estimator import TokenEstimator


class TestTokenEstimator:
    """Оценка размера: Characters/Words/Estimated Tokens."""

    def _estimator(self) -> TokenEstimator:
        return TokenEstimator(characters_per_token=4, words_per_token=1)

    def test_empty(self) -> None:
        estimate = self._estimator().estimate("")
        assert estimate.characters == 0
        assert estimate.words == 0
        assert estimate.estimated_tokens == 0

    def test_characters_and_words(self) -> None:
        estimate = self._estimator().estimate("hello world")
        assert estimate.characters == 11
        assert estimate.words == 2

    def test_tokens_by_characters(self) -> None:
        estimate = self._estimator().estimate("a" * 10)
        assert estimate.estimated_tokens == 3  # ceil(10/4)

    def test_tokens_never_zero_for_text(self) -> None:
        estimate = self._estimator().estimate("word")
        assert estimate.estimated_tokens >= 1

    def test_deterministic(self) -> None:
        estimator = self._estimator()
        first = estimator.estimate("some text").as_dict()
        second = estimator.estimate("some text").as_dict()
        assert first == second

    def test_as_dict(self) -> None:
        estimate = self._estimator().estimate("hello")
        d = estimate.as_dict()
        assert set(d.keys()) == {"characters", "words", "estimated_tokens"}
