"""Tests de integración de la API REST (end-to-end)."""
from __future__ import annotations

from pathlib import Path

import pytest
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


def _seed_portfolio(client: TestClient) -> int:
    """Sube la muestra completa y crea un portafolio con los 6 instrumentos."""
    csv_path = Path(__file__).resolve().parent.parent / "data" / "sample" / "sample_prices.csv"
    with open(csv_path, "rb") as f:
        client.post("/etl/upload", files={"file": ("sample_prices.csv", f, "text/csv")})
    instruments = client.get("/etl/instruments").json()
    resp = client.post("/portfolios", json={"name": "Engine Port"})
    assert resp.status_code == 201
    portfolio_id = resp.json()["id"]
    for inst in instruments:
        r = client.post(
            f"/portfolios/{portfolio_id}/positions",
            json={"instrument_id": inst["id"], "quantity": 100.0},
        )
        assert r.status_code == 201, r.text
    assert len(instruments) == 6
    return portfolio_id


def test_var_engine_segments(client: TestClient):
    """El motor central responde VaR/ES por segmento con cifras trazables."""
    portfolio_id = _seed_portfolio(client)

    all_resp = client.post(
        f"/risk/portfolios/{portfolio_id}/var/engine",
        json={"confidence_level": 0.95, "horizon_days": 1},
    )
    assert all_resp.status_code == 200, all_resp.text
    data = all_resp.json()

    # Lecturas centrales.
    assert data["segment"] == "all"
    assert data["var_value"] > 0
    assert data["expected_shortfall"] >= data["var_value"]
    assert data["portfolio_value"] > 0

    # Proveniencia (de dónde salió cada número).
    assert data["worst_historical_loss"] >= data["expected_shortfall"]
    assert data["n_observations"] > 100
    assert data["n_positions"] == 6
    assert data["n_factors"] == 6
    assert data["calculation_time_ms"] >= 0

    # Segmentos: cada subconjunto es una fracción estricta del total.
    for segment, expected_positions in (
        ("fx", 1),
        ("equity", 3),
        ("commodity", 1),
        ("rate", 1),
    ):
        r = client.post(
            f"/risk/portfolios/{portfolio_id}/var/engine",
            json={"segment": segment, "confidence_level": 0.95},
        )
        assert r.status_code == 200, r.text
        seg = r.json()
        assert seg["n_positions"] == expected_positions
        assert 0 < seg["portfolio_value"] < data["portfolio_value"]
        assert seg["var_value"] > 0
        assert seg["expected_shortfall"] >= seg["var_value"]

    # Confianza y horizonte desplazan la cifra.
    r_high = client.post(
        f"/risk/portfolios/{portfolio_id}/var/engine",
        json={"confidence_level": 0.99, "horizon_days": 10},
    )
    assert r_high.status_code == 200
    assert r_high.json()["var_value"] > data["var_value"]


def test_var_engine_unknown_segment(client: TestClient):
    portfolio_id = _seed_portfolio(client)
    r = client.post(
        f"/risk/portfolios/{portfolio_id}/var/engine",
        json={"segment": "metals"},
    )
    assert r.status_code == 422


def test_var_factors_decomposition(client: TestClient):
    """La contribución al VaR por factor suma 1 y las clases rollup coinciden."""
    portfolio_id = _seed_portfolio(client)

    r = client.get(
        f"/risk/portfolios/{portfolio_id}/var/factors?confidence_level=0.95&horizon_days=1"
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["portfolio_value"] > 0
    assert data["total_var"] > 0
    assert len(data["factors"]) == 6

    shares = sum(f["share"] for f in data["factors"])
    assert shares == pytest.approx(1.0, abs=1e-5)

    contribs = sum(f["contribution"] for f in data["factors"])
    assert contribs == pytest.approx(data["total_var"], rel=1e-4)

    cls_rollup = {}
    for f in data["factors"]:
        cls_rollup[f["asset_class"]] = cls_rollup.get(f["asset_class"], 0.0) + f["share"]
    assert {c["asset_class"] for c in data["classes"]} == set(cls_rollup)
    for c in data["classes"]:
        assert c["share"] == pytest.approx(cls_rollup[c["asset_class"]], abs=5e-6)

    for f in data["factors"]:
        assert f["delta"] == pytest.approx(f["exposure"])
        assert f["gamma"] == 0.0
        assert f["vega"] == 0.0
        assert f["annualized_volatility"] > 0


def test_stress_report(client: TestClient):
    """Baseline vs. estresado: P&L = Σ exposición×shock y VaR sube con la pérdida."""
    portfolio_id = _seed_portfolio(client)

    # 1. Escenario de pérdida: -20% a todo el universo (equity, fx, commodity, rate).
    instruments = client.get("/etl/instruments").json()
    shocks = {i["symbol"]: -0.20 for i in instruments}
    r = client.post(
        f"/risk/portfolios/{portfolio_id}/stress/report",
        json={"scenario_name": "crash", "shocks": shocks},
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["n_positions"] == 6
    assert data["stressed_value"] == pytest.approx(data["baseline_value"] * 0.80, rel=1e-3)
    assert data["pnl"] == pytest.approx(-data["baseline_value"] * 0.20, rel=1e-3)
    assert data["var_baseline"] > 0
    assert data["var_stressed"] >= data["var_baseline"]

    # 2. Escenario de ganancia: el VaR no sube por el shock positivo.
    r2 = client.post(
        f"/risk/portfolios/{portfolio_id}/stress/report",
        json={"scenario_name": "rally", "shocks": {i["symbol"]: 0.20 for i in instruments}},
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["pnl"] > 0
    assert d2["stressed_value"] > d2["baseline_value"]

    # 3. Shock por símbolo: solo afecta a ese instrumento (P&L = exposición).
    sens = client.get(f"/risk/portfolios/{portfolio_id}/sensitivities").json()
    aapl = next(s for s in sens if s["instrument"] == "AAPL")
    r3 = client.post(
        f"/risk/portfolios/{portfolio_id}/stress/report",
        json={"scenario_name": "single", "shocks": {"AAPL": 1.00}},
    )
    assert r3.status_code == 200, r3.text
    d3 = r3.json()
    assert d3["pnl"] == pytest.approx(aapl["exposure"], rel=1e-3)