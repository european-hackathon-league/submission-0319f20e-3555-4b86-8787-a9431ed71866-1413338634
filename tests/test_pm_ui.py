"""The browser cockpit must ship in the same API runtime used by Compose."""


def test_cockpit_and_assets_are_served_by_api(client):
    page = client.get("/pm/")
    assert page.status_code == 200
    assert 'id="workflow-form"' in page.text
    assert 'id="complete-workflow"' in page.text
    for asset, media_type in (("app.js", "javascript"), ("styles.css", "text/css")):
        response = client.get(f"/pm/{asset}")
        assert response.status_code == 200
        assert media_type in response.headers["content-type"]
    assert client.get("/pm/no-such-asset.js").status_code == 404
    # Mount must not absorb existing business API routes.
    assert client.get("/health").json() == {"status": "ok"}
