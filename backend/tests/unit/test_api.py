"""Liveness, readiness, validation, and structured error tests."""

from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from veritas.api.app import create_app
from veritas.api.settings import Settings


def _client(db_path: Path, *, raise_server_exceptions: bool = True) -> TestClient:
    app = create_app(Settings(db_path=db_path))
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_health_stays_live_when_storage_and_chain_are_unavailable() -> None:
    blocked = Path("/dev/null/veritas.db")
    with _client(blocked) as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "health-check-1"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "veritas"}
    assert response.headers["x-request-id"] == "health-check-1"
    assert "chain" not in response.text
    assert not blocked.exists()


def test_health_replaces_an_unsafe_correlation_id() -> None:
    with _client(Path("/dev/null/veritas.db")) as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "bad id"})
    assert response.status_code == 200
    correlation_id = response.headers["x-request-id"]
    assert correlation_id != "bad id"
    assert len(correlation_id) >= 32


def test_ready_is_degraded_when_sqlite_works_and_chain_is_absent(tmp_path: Path) -> None:
    with _client(tmp_path / "veritas.db") as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    checks = {item["name"]: item for item in body["checks"]}
    assert checks["sqlite"]["status"] == "ok"
    assert checks["chain"]["status"] == "warning"
    assert (tmp_path / "veritas.db").is_file()


def test_ready_is_not_ready_when_sqlite_cannot_open() -> None:
    with _client(Path("/dev/null/veritas.db")) as client:
        response = client.get("/api/v1/ready", headers={"X-Request-ID": "ready-fail-1"})
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    checks = {item["name"]: item for item in body["checks"]}
    assert checks["sqlite"]["status"] == "failed"
    assert "dev/null" not in response.text
    assert response.headers["x-request-id"] == "ready-fail-1"


def test_http_error_uses_the_structured_body() -> None:
    with _client(Path("/dev/null/veritas.db")) as client:
        response = client.post("/api/v1/health", headers={"X-Request-ID": "err-1"})
    assert response.status_code == 405
    assert response.json() == {
        "error": {
            "code": "METHOD_NOT_ALLOWED",
            "message": "Method Not Allowed",
            "correlation_id": "err-1",
        }
    }
    assert response.headers["x-request-id"] == "err-1"


def test_unhandled_error_hides_the_exception_text() -> None:
    app = create_app(Settings(db_path=Path("/dev/null/veritas.db")))

    @app.get("/api/v1/explode")
    def explode() -> dict[str, str]:
        raise RuntimeError("secret local path /tmp/private")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/explode", headers={"X-Request-ID": "err-500"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["correlation_id"] == "err-500"
    assert "secret local path" not in response.text


def test_validation_error_is_structured() -> None:
    app = create_app(Settings(db_path=Path("/dev/null/veritas.db")))

    class AmountBody(BaseModel):
        amount_minor: int = Field(gt=0)

    @app.post("/api/v1/validation-probe")
    def validation_probe(payload: Annotated[AmountBody, Body()]) -> AmountBody:
        return payload

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/validation-probe",
            json={"amount_minor": 0},
            headers={"X-Request-ID": "val-1"},
        )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["correlation_id"] == "val-1"
    assert error["details"][0]["loc"] == ["body", "amount_minor"]
    assert response.headers["x-request-id"] == "val-1"


def test_settings_reject_a_public_bind_host() -> None:
    try:
        Settings(host="0.0.0.0")
    except ValueError:
        return
    raise AssertionError("public bind host was accepted")


def test_app_factory_returns_fastapi() -> None:
    app = create_app(Settings(db_path=Path("/dev/null/veritas.db")))
    assert isinstance(app, FastAPI)


def test_current_ruleset_endpoint(tmp_path: Path) -> None:
    with _client(tmp_path / "veritas.db") as client:
        res1 = client.get("/api/v1/rulesets/current")
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["ruleset_version"] == "rules-v1"
        assert len(data1["manifest_sha256"]) == 64
        assert "rules" in data1["manifest"]

        res2 = client.get("/rulesets/current")
        assert res2.status_code == 200
        assert res2.json() == data1
