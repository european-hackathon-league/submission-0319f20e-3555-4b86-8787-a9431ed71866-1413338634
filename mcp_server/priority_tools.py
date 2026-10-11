"""Pod D prioritization v2 tools. The rubric switch is a human gate and is not exposed here.

Tools call the API through the injected api_request(method, path, *, params=None, payload=None) and
use identifier(value) to encode path segments. Registered by mcp_server/main.py.
"""


def register_priority_tools(mcp, api_request, identifier):
    """Stub: the pod registers its tools here."""
