"""Real-HTTP coverage for the security response headers added in the
Final Security Hardening Pass (app/main.py's add_security_headers
middleware) -- pins that every response actually carries them, so a
future refactor of main.py can't silently drop the middleware. Run
from `backend/`:

    python -m tests.test_security_headers
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_response_carries_all_security_headers():
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_a_404_response_still_carries_security_headers():
    # The middleware wraps call_next() unconditionally -- must apply
    # even to error responses, not just the happy path.
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
