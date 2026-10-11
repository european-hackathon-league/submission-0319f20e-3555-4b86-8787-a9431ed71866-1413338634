"""Pod B market balancer tools. Resolving a conflict is a human gate and is not exposed here.

Tools call the API through the injected api_request(method, path, *, params=None, payload=None) and
use identifier(value) to encode path segments. Registered by mcp_server/main.py.
"""


def register_markets_tools(mcp, api_request, identifier):
    """Stub: the pod registers its tools here."""
