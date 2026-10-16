"""CRUD behaviour of /api/expenses."""


def test_categories_listed(client):
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    assert "food" in resp.json()
    assert "rent" in resp.json()


def test_create_expense(client):
    resp = client.post(
        "/api/expenses",
        json={
            "title": "Metro card top-up",
            "amount": "500.00",
            "category": "transport",
            "spent_on": "2026-10-02",
            "note": "monthly",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] > 0
    assert body["title"] == "Metro card top-up"
    assert body["amount"] == "500.00"
    assert body["category"] == "transport"


def test_category_is_normalised(client, make_expense):
    created = make_expense(category="  FOOD ")
    assert created["category"] == "food"


def test_list_newest_first(client, make_expense):
    make_expense(title="older", spent_on="2026-10-01")
    make_expense(title="newer", spent_on="2026-10-20")
    titles = [e["title"] for e in client.get("/api/expenses").json()]
    assert titles == ["newer", "older"]


def test_filter_by_category(client, make_expense):
    make_expense(title="Groceries", category="food")
    make_expense(title="Electricity", category="utilities")
    resp = client.get("/api/expenses", params={"category": "utilities"})
    assert [e["title"] for e in resp.json()] == ["Electricity"]


def test_filter_by_month(client, make_expense):
    make_expense(title="september", spent_on="2026-09-30")
    make_expense(title="october", spent_on="2026-10-01")
    resp = client.get("/api/expenses", params={"month": "2026-10"})
    assert [e["title"] for e in resp.json()] == ["october"]


def test_bad_month_is_rejected(client):
    resp = client.get("/api/expenses", params={"month": "October"})
    assert resp.status_code == 422


def test_get_expense_by_id(client, make_expense):
    created = make_expense(title="Gym")
    resp = client.get(f"/api/expenses/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Gym"


def test_get_missing_expense_is_404(client):
    resp = client.get("/api/expenses/9999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_update_expense(client, make_expense):
    created = make_expense(title="Coffee", amount="80.00")
    resp = client.put(
        f"/api/expenses/{created['id']}",
        json={
            "title": "Coffee and sandwich",
            "amount": "230.00",
            "category": "food",
            "spent_on": "2026-10-05",
            "note": "with Rohan",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == "230.00"
    assert client.get(f"/api/expenses/{created['id']}").json()["note"] == "with Rohan"


def test_update_missing_expense_is_404(client):
    resp = client.put(
        "/api/expenses/9999",
        json={"title": "x", "amount": "1", "category": "food", "spent_on": "2026-10-01"},
    )
    assert resp.status_code == 404


def test_delete_expense(client, make_expense):
    created = make_expense()
    assert client.delete(f"/api/expenses/{created['id']}").status_code == 204
    assert client.get(f"/api/expenses/{created['id']}").status_code == 404


def test_delete_missing_expense_is_404(client):
    assert client.delete("/api/expenses/9999").status_code == 404


def test_negative_amount_rejected(client):
    resp = client.post(
        "/api/expenses",
        json={"title": "Refund?", "amount": "-50", "category": "food", "spent_on": "2026-10-01"},
    )
    assert resp.status_code == 422


def test_zero_amount_rejected(client):
    resp = client.post(
        "/api/expenses",
        json={"title": "Free", "amount": "0", "category": "food", "spent_on": "2026-10-01"},
    )
    assert resp.status_code == 422


def test_unknown_category_rejected(client):
    resp = client.post(
        "/api/expenses",
        json={"title": "Crypto", "amount": "100", "category": "gambling", "spent_on": "2026-10-01"},
    )
    assert resp.status_code == 422
    assert "category must be one of" in resp.text


def test_blank_title_rejected(client):
    resp = client.post(
        "/api/expenses",
        json={"title": "   ", "amount": "10", "category": "food", "spent_on": "2026-10-01"},
    )
    assert resp.status_code == 422
