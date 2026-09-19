# ADR-0001 — Eliminar el seam de persistencia de resultados

- **Estado:** Aceptado
- **Fecha:** 2026-09-18
- **Decisores:** Rafael (review de arquitectura 2026-09-18)

## Contexto

Las tablas `RiskResult` y `StressResult` (`app/models/results.py`) se creaban
en el arranque (`init_db`) pero **ningún módulo las escribía ni las leía**: un
*seam* de persistencia con cero *adapters*. Regla de arquitectura: "un
adapter = seam hipotético; dos = real". Sin consumidor, el seam no era real y
obligaba a cada lector del código a preguntarse qué camino de persistencia usaba.

## Decisión

Eliminar las tablas `RiskResult` y `StressResult` y su registro en
`init_db`. No reintroducir el seam de persistencia de resultados hasta que
exista un consumidor real que produzca/consulte esos datos a partir de
`PortfolioProfile` (`app/risk/portfolio_profile.py`), el objeto de resultados
del núcleo del perfil de riesgo.

## Consecuencias

- Se elimina `app/models/results.py` y una import en `app/database.py`.
- El riesgo de portafolio sigue devolviéndose en memoria desde una sola
  llamada al perfil; no hay contrato de disco que mantener.
- Un futuro consumidor (persistencia de reportes, histórico de VaR) empieza
  desde `PortfolioProfile`, no desde el esquema anterior.
- Las revisiones de arquitectura no deberían re-proponer este seam sin un
  adapter concreto que lo justifique.