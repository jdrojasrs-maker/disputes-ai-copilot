import pytest
from fastapi.testclient import TestClient

from disputes.main import app
from disputes.repository import InMemoryDisputeRepository
from disputes.routes import get_repository


@pytest.fixture
def repository() -> InMemoryDisputeRepository:
    return InMemoryDisputeRepository()


@pytest.fixture
def client(repository: InMemoryDisputeRepository):
    app.dependency_overrides[get_repository] = lambda: repository
    yield TestClient(app)
    app.dependency_overrides.clear()
