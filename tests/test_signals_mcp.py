"""Signals MCP adapter contracts; no live API or network."""

import pytest

from mcp_server.signals_tools import register_signals_tools


class Registry:
    def __init__(self):
        self.functions = {}

    def tool(self):
        def add(function):
            self.functions[function.__name__] = function
            return function
        return add


@pytest.mark.parametrize(("name", "arguments", "method", "path", "body_key"), [
    ("refresh_signal_watchlist", {"watchlist_id": "w", "actor": "ai:test"}, "POST", "/signals/watchlists/w/refresh", "payload"),
    ("backfill_signal_watchlist", {"watchlist_id": "w", "actor": "ai:test", "weeks": 4}, "POST", "/signals/watchlists/w/backfill", "payload"),
    ("score_signal_sentiment", {"vehicle": "G60", "market": "US", "actor": "ai:test"}, "POST", "/signals/sentiment/score", "payload"),
    ("get_signal_summary", {"market": "CN"}, "GET", "/signals/summary", "params"),
    ("get_sentiment_timeseries", {"method_version": "lexicon-v1"}, "GET", "/signals/sentiment/timeseries", "params"),
])
async def test_adapters_keep_paths_scope_and_provider(name, arguments, method, path, body_key):
    calls = []

    async def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"items": []}

    registry = Registry()
    register_signals_tools(registry, request, lambda value: value)
    assert await registry.functions[name](**arguments) == {"items": []}
    assert calls[0][:2] == (method, path)
    body = calls[0][2][body_key]
    for key, value in arguments.items():
        if key != "watchlist_id":
            assert body[key] == value
    if "sentiment" in name and method == "POST":
        assert body["provider"] == "openai"
    assert len(registry.functions) == 11
    assert not any(word in name for name in registry.functions for word in ("import", "dismiss", "create", "pause", "resume"))
    for public_tool in ("refresh_signal_watchlist", "backfill_signal_watchlist", "list_signal_watchlists"):
        assert "verbatims" in registry.functions[public_tool].__doc__
