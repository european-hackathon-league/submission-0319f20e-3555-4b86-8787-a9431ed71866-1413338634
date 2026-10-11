"""Pod C request intake and triage tools. Request decisions are human gates and are not exposed here.

Tools call the API through the injected api_request(method, path, *, params=None, payload=None) and
use identifier(value) to encode path segments. Registered by mcp_server/main.py.
"""


def register_intake_tools(mcp, api_request, identifier):
    """Stub: the pod registers its tools here."""
