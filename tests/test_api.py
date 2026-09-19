"""Tests de integración de la API REST (end-to-end)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_full_flow(client: TestClient, sample_data_dir: Path):
    # 1. ETL: subir el CSV de muestra.
    csv_path = sample_data_dir / "sample_prices.csv"
    with open(csv_path, "rb") as f:
        resp = client.post(
            "/etl/upload",
            files={"file": ("sample_prices.csv", f, "text/csv")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["instruments_loaded"] == 6
    assert body["price_rows_loaded"] > 0

    # 2. Listar instrumentos.
    instruments = client.get("/etl/instruments").json()
    assert len(instruments) == 6
    symbols = {i["symbol"] for i in instruments}
    assert {"AAPL", "MSFT", "EURUSD"} <= symbols

    # 2b. VaR de un instrumento individual (los tres métodos), con retornos reales.
    aapl = next(i for i in instruments if i["symbol"] == "AAPL")
    for method in ("historical", "parametric", "monte_carlo"):
        r = client.post(
            f"/risk/instruments/{aapl['id']}/var",
            json={"method": method, "confidence_level": 0.95},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # AAPL ≈ 185 USD, vol anual ~28%: VaR 1d al 95% es una fracción del precio.
        assert 0 < data["var_value"] < 50
        assert data["expected_shortfall"] >= data["var_value"]

    # 3. Crear portafolio y añadir posiciones.
    resp = client.post("/portfolios", json={"name": "Test Port"})
    assert resp.status_code == 201
    portfolio_id = resp.json()["id"]

    for inst in instruments:
        if inst["symbol"] in {"AAPL", "MSFT", "XAU"}:
            r = client.post(
                f"/portfolios/{portfolio_id}/positions",
                json={"instrument_id": inst["id"], "quantity": 100.0},
            )
            assert r.status_code == 201, r.text

    # 4. VaR del portafolio (los tres métodos).
    for method in ("historical", "parametric", "monte_carlo"):
        r = client.post(
            f"/risk/portfolios/{portfolio_id}/var",
            json={"method": method, "confidence_level": 0.95},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["var_value"] > 0
        assert data["expected_shortfall"] >= data["var_value"]

    # 5. Stress tests por defecto.
    r = client.post(f"/risk/portfolios/{portfolio_id}/stress", json={"scenarios": None})
    assert r.status_code == 200, r.text
    scenarios = r.json()
    assert len(scenarios) == 4
    names = {s["scenario_name"] for s in scenarios}
    assert names == {"equity_crash", "equity_rally", "fx_devaluation", "vol_spike"}

    # 5b. Stress tests con escenarios personalizados.
    custom = {
        "equity_crash": {"AAPL": -0.30, "MSFT": -0.30, "XAU": -0.15},
        "gold_rally": {"XAU": 0.20},
    }
    r = client.post(f"/risk/portfolios/{portfolio_id}/stress", json={"scenarios": custom})
    assert r.status_code == 200, r.text
    by_name = {s["scenario_name"]: s["impact"] for s in r.json()}
    assert set(by_name) == {"equity_crash", "gold_rally"}
    # Todas las posiciones son long: el crash golpea y el rally de oro no compensa.
    assert by_name["equity_crash"] < 0 < by_name["gold_rally"]
    assert by_name["equity_crash"] + by_name["gold_rally"] < 0

    # 6. Sensibilidades.
    r = client.get(f"/risk/portfolios/{portfolio_id}/sensitivities")
    assert r.status_code == 200
    sens = r.json()
    assert len(sens) == 3
    assert all(s["annualized_volatility"] is not None for s in sens)

    # 7. Reporte consolidado.
    r = client.post(
        f"/risk/portfolios/{portfolio_id}/report",
        json={"method": "parametric", "confidence_level": 0.95},
    )
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["market_value"] > 0
    assert set(report["var_by_method"]) == {"historical", "parametric", "monte_carlo"}
    assert report["market_value"] > report["var_by_method"]["parametric"]