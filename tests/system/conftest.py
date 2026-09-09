"""System-suite policy fixtures.

System scenarios exercise trusted operational data unless a test explicitly
covers lifecycle eligibility. Promote data registered through Librarian so
ordinary retrieval observes the production CANONICAL-only boundary.
"""

from collections.abc import Generator

import pytest
from pytest import MonkeyPatch

from hkos.repository.models import Knowledge
from hkos.services.librarian import Librarian


@pytest.fixture(autouse=True)
def canonical_system_knowledge(
    monkeypatch: MonkeyPatch,
) -> Generator[None, None, None]:
    """Treat generic system-test corpus entries as trusted knowledge."""
    original_register = Librarian.register

    def register_canonical(
        self: Librarian,
        project_id: str,
        knowledge: Knowledge,
        category: str | None = None,
    ) -> Knowledge:
        """Register and promote trusted system-test knowledge."""
        saved = original_register(self, project_id, knowledge, category)
        return self.canonicalize(project_id, saved.id)

    monkeypatch.setattr(Librarian, "register", register_canonical)
    yield
