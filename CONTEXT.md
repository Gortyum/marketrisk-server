# Glosario de dominio — Market Risk API

Este archivo nombra los conceptos de dominio y dónde viven como *seams*.
Las decisiones de arquitectura que no queremos re-litigar en cada revisión
se registran en `docs/adr/`.

## Conceptos

- **Instrumento** — factor de riesgo atómico con serie de precios
  (equity, fx, commodity, rate). `app/models/market_data.py`.
- **Precio histórico** — close diario por instrumento y fecha; entrada
  bruta de todo el análisis.
- **Retorno** — log-return diario de un precio. La **pérdida** es su
  negado y se trabaja siempre en valores positivos.
- **Posición** — tenencia de un instrumento dentro de un portafolio
  (cantidad × peso). `app/models/portfolio.py`.
- **Exposición** — valor de mercado de una posición: cantidad × último precio.
- **Portafolio** — conjunto de posiciones; la unidad de análisis de riesgo.
- **Perfil de riesgo** — el seam del análisis: el módulo que materializa
  TODO el riesgo de un portafolio en un solo pase (valor de mercado, VaR y
  ES por método, sensibilidades y stress). Núcleo puro en
  `app/risk/portfolio_profile.py`; `RiskService`
  (`app/services/risk_service.py`) es el adapter que lee la base y lo llama.
- **VaR / Expected Shortfall (ES)** — pérdida en USD (positiva) a un nivel
  de confianza y horizonte dados. ES = pérdida media más allá del VaR.
- **Escenario de stress** — shocks porcentuales por instrumento
  (p. ej. `equity_crash` -20%). `app/risk/stress.py`.
- **Sensibilidad** — exposición (USD) de una posición y su volatilidad
  anualizada.
- **Ingesta de mercado (ETL)** — extract → transform → load de series de
  precios, idempotente (upsert por instrumento y por fecha).
  `app/etl/`.

## Convenciones

- Los VaR/ES se devuelven como pérdida en USD, positivos.
- El VaR/ES por instrumento y portafolio sale de `compute_var()` en
  `app/risk/var.py`: **un único dispatch de método y una única política de
  escalado por horizonte**.
- El perfil de riesgo de portafolio usa log-retornos alineados por fecha y
  ponderación por valor de mercado; Monte Carlo simula con correlación
  (Cholesky).