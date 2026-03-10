"""Integration tests for the web interface."""

from starlette.testclient import TestClient

from slab_designer.web.app import app

client = TestClient(app)


def test_homepage_renders() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Slab design without the spreadsheet fog." in response.text
    assert "Wheel Load" in response.text
    assert "Shrinkage-Compensating" in response.text


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_wheel_api_returns_validation_status() -> None:
    response = client.post(
        "/api/wheel",
        json={
            "axle_load_lb": 22400,
            "contact_area_in2": 25,
            "wheel_spacing_in": 40,
            "k": 200,
            "fr": 570,
            "method": "pca",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["validation_status"] == "approximate"
    assert body["metrics"][0]["value"] == "PCA"


def test_pt_api_returns_equation_based_response() -> None:
    response = client.post(
        "/api/pt",
        json={
            "slab_length_ft": 500,
            "slab_thickness_in": 6,
            "Pe": 26000,
            "k": 150,
            "fp": 250,
            "mu": 0.5,
            "slip_sheet": "none",
            "industrial": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["validation_status"] == "equation-based"
    assert any(metric["label"] == "Tendon spacing" for metric in body["metrics"])


def test_shrinkage_api_returns_digitized_response() -> None:
    response = client.post(
        "/api/shrinkage",
        json={
            "slab_thickness_in": 6.0,
            "slab_length_ft": 100.0,
            "slab_width_ft": 12.0,
            "prism_expansion_pct": 0.05,
            "rho": 0.00241,
            "volume_surface_ratio": 6.0,
            "k": 100.0,
            "slip_sheet": "two_poly",
            "expansion_at_one_end": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["validation_status"] == "digitized"
    assert any(metric["label"] == "Full compensation" for metric in body["metrics"])


def test_frc_yield_line_requires_thickness() -> None:
    response = client.post(
        "/api/frc",
        json={
            "load_lb": 15000,
            "contact_area_in2": 24,
            "k": 100,
            "re3": 55,
            "method": "yield_line",
        },
    )

    assert response.status_code == 400
    assert "h_in" in response.json()["error"]
