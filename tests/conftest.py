import asyncio
import socket

import pytest
from fastapi.testclient import TestClient

from disputes.main import app
from disputes.repository import InMemoryDisputeRepository
from disputes.routes import get_repository
from fake_llm import FakeLLMClient


@pytest.fixture
def repository() -> InMemoryDisputeRepository:
    return InMemoryDisputeRepository()


@pytest.fixture
def client(repository: InMemoryDisputeRepository):
    app.dependency_overrides[get_repository] = lambda: repository
    yield TestClient(app)
    app.dependency_overrides.clear()


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _refuse_if_remote(address: object) -> None:
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if host is not None and host not in LOCAL_HOSTS:
        raise RuntimeError(f"network access in a unit test: {host!r}")


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test reaches anything but this machine.

    Creating sockets stays allowed (asyncio and the test client use local ones). Name lookups,
    sync connects and asyncio connects to other hosts are refused, so no unit test can reach a
    real model. The asyncio part matters on Windows, where its event loop does not go through
    `socket.socket.connect`.
    """

    def wrap_socket_method(original):
        def method(self, address, *args, **kwargs):
            _refuse_if_remote(address)
            return original(self, address, *args, **kwargs)

        return method

    def wrap_getaddrinfo(original):
        def getaddrinfo(host, *args, **kwargs):
            _refuse_if_remote(host)
            return original(host, *args, **kwargs)

        return getaddrinfo

    def wrap_create_connection(original):
        async def create_connection(self, protocol_factory, host=None, *args, **kwargs):
            _refuse_if_remote(host)
            return await original(self, protocol_factory, host, *args, **kwargs)

        return create_connection

    def wrap_sock_connect(original):
        async def sock_connect(self, sock, address):
            _refuse_if_remote(address)
            return await original(self, sock, address)

        return sock_connect

    monkeypatch.setattr(socket.socket, "connect", wrap_socket_method(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", wrap_socket_method(socket.socket.connect_ex))
    monkeypatch.setattr(socket, "getaddrinfo", wrap_getaddrinfo(socket.getaddrinfo))
    loop_classes = [asyncio.BaseEventLoop]
    proactor = getattr(asyncio, "ProactorEventLoop", None)
    if proactor is not None:
        loop_classes.append(proactor)
    for cls in loop_classes:
        if "create_connection" in vars(cls):
            wrapped = wrap_create_connection(cls.create_connection)
            monkeypatch.setattr(cls, "create_connection", wrapped)
        if "sock_connect" in vars(cls):
            monkeypatch.setattr(cls, "sock_connect", wrap_sock_connect(cls.sock_connect))


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()
