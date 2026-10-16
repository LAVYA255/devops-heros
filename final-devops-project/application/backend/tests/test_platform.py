"""Health, readiness and metrics: the endpoints Kubernetes and Prometheus rely on."""


def test_health_is_up(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "UP", "version": "test"}


def test_ready_when_database_reachable(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "READY"


def test_root_points_at_docs(client):
    body = client.get("/").json()
    assert body["service"] == "kharcha-api"
    assert body["docs"] == "/docs"


def test_metrics_is_prometheus_format(client):
    client.get("/health")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "kharcha_http_requests_total" in resp.text
    assert "kharcha_http_request_duration_seconds_bucket" in resp.text


def test_metrics_use_route_template_not_raw_path(client, make_expense):
    created = make_expense()
    client.get(f"/api/expenses/{created['id']}")
    text = client.get("/metrics").text
    # The template, not the literal ID, must be the label value.
    assert 'route="/api/expenses/{expense_id}"' in text
    assert f'route="/api/expenses/{created["id"]}"' not in text


def test_business_metric_counts_created_expenses(client, make_expense):
    make_expense(category="transport", amount="120.00")
    text = client.get("/metrics").text
    assert 'kharcha_expenses_created_total{category="transport"}' in text
