"""The autouse `block_network` fixture in conftest.py must stop any real connection (SC-003)."""

import socket

import httpx2
import pytest

REMOTE_IP = "93.184.216.34"


def test_a_sync_connect_to_a_remote_host_is_refused() -> None:
    with socket.socket() as sock, pytest.raises(RuntimeError, match="network access"):
        sock.connect((REMOTE_IP, 80))


def test_a_name_lookup_for_a_remote_host_is_refused() -> None:
    with pytest.raises(RuntimeError, match="network access"):
        socket.getaddrinfo("api.anthropic.com", 443)


@pytest.mark.anyio
async def test_an_async_http_call_to_a_remote_ip_is_refused() -> None:
    async with httpx2.AsyncClient() as client:
        with pytest.raises(BaseException) as raised:
            await client.get(f"http://{REMOTE_IP}/")
    assert "network access" in repr(raised.value)


@pytest.mark.anyio
async def test_an_async_http_call_to_a_remote_hostname_is_refused() -> None:
    async with httpx2.AsyncClient() as client:
        with pytest.raises(BaseException) as raised:
            await client.get("https://api.anthropic.com/")
    assert "network access" in repr(raised.value)
