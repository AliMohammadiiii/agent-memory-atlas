import json
import logging
import socket

from server import gateway


def test_provider_failover_is_bounded_and_logs_no_private_input(monkeypatch, caplog):
    g = gateway.Gateway.__new__(gateway.Gateway)
    g.primary_gateway, g.primary = "first", "model-a"
    g.fallback_gateway, g.fallback = "second", "model-b"
    g.gateway_env = {
        "first": {"url_env": "FIRST_URL", "key_env": "FIRST_KEY"},
        "second": {"url_env": "SECOND_URL", "key_env": "SECOND_KEY"},
    }
    for name in ["FIRST_URL", "SECOND_URL"]:
        monkeypatch.setenv(name, "https://example.invalid")
    for name in ["FIRST_KEY", "SECOND_KEY"]:
        monkeypatch.setenv(name, "super-secret-key")
    calls = []

    def fake_post(url, data, key):
        calls.append(url)
        if len(calls) == 1:
            raise socket.timeout("private source and credential")
        return {"model": "model-b", "choices": [{"message": {"content": '{"answer": "ok"}'}}]}

    monkeypatch.setattr(gateway, "post", fake_post)
    with caplog.at_level(logging.WARNING, logger="atlas.gateway"):
        result, _ = g.generate("private system text", {"question": "private source text"})
    assert result == {"answer": "ok"}
    assert len(calls) == 2
    log = json.loads(caplog.records[0].message)
    assert log["category"] == "provider_timeout"
    assert log["stage"] == "generation"
    assert "private" not in caplog.text and "super-secret" not in caplog.text


def test_cancellation_is_not_swallowed(monkeypatch):
    g = gateway.Gateway.__new__(gateway.Gateway)
    g.primary_gateway, g.primary = "first", "model-a"
    g.fallback_gateway, g.fallback = "first", "model-b"
    g.gateway_env = {"first": {"url_env": "URL", "key_env": "KEY"}}
    monkeypatch.setenv("URL", "https://example.invalid")
    monkeypatch.setenv("KEY", "secret")

    def cancel(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(gateway, "post", cancel)
    import pytest

    with pytest.raises(KeyboardInterrupt):
        g.generate("system", {})
