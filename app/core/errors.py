"""Plain-language responses for setup problems, instead of a bare "Internal Server Error"."""
from __future__ import annotations

import html
from typing import Any, Dict

from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.requests import Request

_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Setup needed</title>
<style>body{{font-family:system-ui,sans-serif;background:#f1f5f9;color:#1e293b;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{background:#fff;border-radius:12px;box-shadow:0 4px 20px #0001;max-width:560px;margin:16px;padding:32px}}
h1{{font-size:1.25rem;margin:0 0 8px}}p{{line-height:1.5}}code{{background:#f1f5f9;padding:2px 6px;border-radius:4px}}
.fix{{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px;margin-top:16px}}small{{color:#64748b}}</style></head>
<body><div class="card"><h1>{title}</h1><p>{message}</p><div class="fix"><strong>What to do:</strong><br>{fix}</div>
<p><small>This page appears because of how the application is set up, not because of anything you did. The server's own log has the technical details.</small></p></div></body></html>"""

TITLES = {
    "database_unreachable": "Cannot reach the database",
    "schema_not_set_up": "The database needs setting up",
    "schema_outdated": "The database needs upgrading",
    "schema_newer": "The application needs updating",
}


def wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return request.url.path.startswith("/api/") or ("application/json" in accept and "text/html" not in accept)


def setup_problem_response(request: Request, status: Dict[str, Any]) -> Response:
    """503 with a message a person can act on (no stack trace, nothing sensitive)."""
    if wants_json(request):
        return JSONResponse(status_code=503, content={"detail": f"{status['message']} {status['fix']}".strip(), "problem": status["problem"],
                                                      "fix": status["fix"]})
    body = _PAGE.format(title=html.escape(TITLES.get(status["problem"], "Setup needed")), message=html.escape(status["message"]),
                        fix=html.escape(status["fix"]).replace("alembic upgrade head", "<code>alembic upgrade head</code>"))
    return HTMLResponse(body, status_code=503)
