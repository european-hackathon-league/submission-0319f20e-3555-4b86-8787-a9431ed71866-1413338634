"""Static MCP App resources; workflow data stays in existing API-backed tools."""

from pathlib import Path

from mcp.server.mcpserver.exceptions import ResourceError

APP_MIME = "text/html;profile=mcp-app"
SCORING_UI = "ui://bmw-evidence/scoring-panel.html"
TRACE_UI = "ui://bmw-evidence/trace-explorer.html"
UI_DIR = Path(__file__).parent / "ui" / "dist"


def _html(filename: str) -> str:
    # Only the two fixed registrations below select filenames. No URI/path
    # interpolation, environment injection or backend credentials enter the UI.
    try:
        return (UI_DIR / filename).read_text(encoding="utf-8")
    except OSError as exc:
        raise ResourceError(
            f"Cannot read built MCP App {filename}. "
            "Run npm ci && npm run build in mcp_server/ui, or rebuild the MCP Docker image."
        ) from exc


def register_app_resources(mcp) -> None:
    metadata = {"ui": {"prefersBorder": False, "csp": {"connectDomains": [], "resourceDomains": []}}}

    @mcp.resource(SCORING_UI, name="Scoring and decision panel", mime_type=APP_MIME, meta=metadata)
    def scoring_panel_view() -> str:
        return _html("scoring-panel.html")

    @mcp.resource(TRACE_UI, name="Requirement trace explorer", mime_type=APP_MIME, meta=metadata)
    def trace_explorer_view() -> str:
        return _html("trace-explorer.html")
