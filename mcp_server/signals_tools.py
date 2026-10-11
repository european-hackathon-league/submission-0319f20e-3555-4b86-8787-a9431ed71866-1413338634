"""Pod A signals and sentiment tools. Anything touching Exa repeats the data-boundary rule:
queries come only from PM watchlist templates; never BMW records, verbatims or personal data.

Tools call the API through the injected api_request(method, path, *, params=None, payload=None) and
use identifier(value) to encode path segments. Registered by mcp_server/main.py.
"""


def register_signals_tools(mcp, api_request, identifier):
    """Stub: the pod registers its tools here."""
