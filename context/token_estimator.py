"""HKOS Token Estimator (DS-009 §12, IP-009)
===========================================
Оценка размера будущего контекста: Characters, Words, Estimated Tokens.

Коэффициенты — ТОЛЬКО из конфигурации (context.token_estimator.*).
В коде НЕТ захардкоженных коэффициентов (архитектурный тест №9).

Оценка независима от конкретной LLM.
"""

from dataclasses import dataclass

__all__ = ["TokenEstimate", "TokenEstimator"]


@dataclass
class TokenEstimate:
    """Результат оценки размера текста."""

    characters: int = 0
    words: int = 0
    estimated_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        """Оценка как словарь."""
        return {
            "characters": self.characters,
            "words": self.words,
            "estimated_tokens": self.estimated_tokens,
        }


class TokenEstimator:
    """Оценка размера текста (конфигурируемые коэффициенты)."""

    def __init__(
        self,
        characters_per_token: float,
        words_per_token: float,
    ) -> None:
        """Инициализация оценки.

        Args:
            characters_per_token: Символов на токен (ИЗ КОНФИГУРАЦИИ).
            words_per_token: Слов на токен (ИЗ КОНФИГУРАЦИИ).

        """
        self._characters_per_token = characters_per_token
        self._words_per_token = words_per_token

    def estimate(self, text: str) -> TokenEstimate:
        """Оценить размер текста.

        Args:
            text: Текст (сериализованный контекст или секция).

        Returns:
            TokenEstimate (characters, words, estimated_tokens).

        """
        characters = len(text)
        words = len(text.split())
        if self._characters_per_token <= 0:
            tokens_by_chars = words
        else:
            tokens_by_chars = -(-characters // max(1, int(self._characters_per_token)))
        if self._words_per_token <= 0:
            tokens_by_words = characters
        else:
            tokens_by_words = -(-words // max(1, int(self._words_per_token)))
        estimated = max(tokens_by_chars, tokens_by_words)
        return TokenEstimate(
            characters=characters,
            words=words,
            estimated_tokens=estimated,
        )
