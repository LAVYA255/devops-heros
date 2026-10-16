"""The monthly summary, which is where the budget from the ConfigMap is used."""
from decimal import Decimal


def test_summary_totals_by_category(client, make_expense):
    make_expense(category="rent", amount="6000.00", spent_on="2026-10-01")
    make_expense(category="food", amount="250.50", spent_on="2026-10-03")
    make_expense(category="food", amount="149.50", spent_on="2026-10-04")

    body = client.get("/api/expenses/summary", params={"month": "2026-10"}).json()

    assert Decimal(body["total"]) == Decimal("6400.00")
    assert body["count"] == 3
    by_cat = {row["category"]: row for row in body["by_category"]}
    assert Decimal(by_cat["food"]["total"]) == Decimal("400.00")
    assert by_cat["food"]["count"] == 2
    # Biggest spend first.
    assert body["by_category"][0]["category"] == "rent"


def test_summary_uses_budget_from_config(client, make_expense):
    # conftest sets MONTHLY_BUDGET=10000
    make_expense(category="rent", amount="2500.00", spent_on="2026-10-01")
    body = client.get("/api/expenses/summary", params={"month": "2026-10"}).json()
    assert Decimal(body["budget"]) == Decimal("10000")
    assert body["budget_used_pct"] == 25.0
    assert Decimal(body["remaining"]) == Decimal("7500")


def test_summary_ignores_other_months(client, make_expense):
    make_expense(amount="999.00", spent_on="2026-09-30")
    body = client.get("/api/expenses/summary", params={"month": "2026-10"}).json()
    assert body["count"] == 0
    assert Decimal(body["total"]) == Decimal("0")
    assert body["by_category"] == []


def test_summary_december_rolls_into_next_year(client, make_expense):
    make_expense(amount="100.00", spent_on="2026-12-31")
    make_expense(amount="100.00", spent_on="2027-01-01")
    body = client.get("/api/expenses/summary", params={"month": "2026-12"}).json()
    assert body["count"] == 1


def test_summary_route_is_not_treated_as_an_id(client):
    # /summary is declared before /{expense_id}; if the order were wrong FastAPI
    # would try to parse "summary" as an int and return 422.
    assert client.get("/api/expenses/summary").status_code == 200
