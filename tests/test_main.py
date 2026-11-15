from fastapi.testclient import TestClient
from app.main import app

# Wrap the FastAPI app in Starlette's TestClient to simulate HTTP calls in memory.
# Eliminates network port binding and external server overhead during CI runs.
client = TestClient(app)


def test_liveness_endpoint():
    # Confirm /healthz returns HTTP 200 even when no PostgreSQL instance is running.
    # Also verify the middleware injects X-Correlation-ID into response headers.
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert "X-Correlation-ID" in response.headers


def test_readiness_fails_when_db_unavailable():
    # Confirm /ready detects the missing database and returns 503 Service Unavailable.
    # Proves Kubernetes will not route traffic to an uninitialized or disconnected pod.
    response = client.get("/ready")
    assert response.status_code == 503
