import pytest

from app.server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_index_lists_operations(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "add" in resp.get_json()["operations"]


def test_calc_returns_result(client):
    resp = client.get("/calc?op=add&a=10&b=5")
    assert resp.status_code == 200
    assert resp.get_json()["result"] == 15


def test_calc_rejects_divide_by_zero(client):
    resp = client.get("/calc?op=divide&a=10&b=0")
    assert resp.status_code == 400
    assert "zero" in resp.get_json()["error"]


def test_calc_rejects_bad_numbers(client):
    resp = client.get("/calc?op=add&a=abc&b=5")
    assert resp.status_code == 400
