import json

import pytest


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000",
                                    "http://localhost:5173", "http://127.0.0.1:5173"])
def test_local_frontend_can_preflight_and_read_workspace(client, origin):
    response = client.options("/requirements/requirement", headers={
        "Origin": origin, "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "Content-Type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers
    response = client.get("/workspace", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_unconfigured_frontend_cannot_preflight(client):
    response = client.options("/workspace", headers={
        "Origin": "https://unconfigured.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("path", ["/imports/web-fetch", "/analyses", "/requirements/generate"])
@pytest.mark.parametrize("payload", [{"\ud800": "extra"}, {"actor": "bad\ud800"}, {"actor": float("nan")}])
def test_invalid_input_is_safe_across_routers(client, path, payload):
    response = client.post(path, content=json.dumps(payload), headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]
