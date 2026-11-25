# Fuentes

## Datos
- **Open-Meteo Historical Weather API** (reanálisis ERA5 de Copernicus/ECMWF). Temperatura media diaria
  2021-01-01 a 2024-12-31, lat −33,45, lon −70,66, zona America/Santiago. Licencia CC BY 4.0.
  https://open-meteo.com/en/docs/historical-weather-api — descargado el 2026-11-25.
  Archivo derivado: `data/clima_santiago_mensual.csv` (grados día mensuales).
- **Datos sintéticos**: `data/planta_sintetica.csv`, generado por `scripts/generar_datos_sinteticos.py`
  (semilla 50001). No corresponden a ninguna planta real.

## Normas y método (no se reproduce texto de normas)
- ISO 50001:2018, Sistemas de gestión de la energía. Requisitos con orientación para su uso.
- ISO 50006:2023, Medición del desempeño energético usando líneas base energéticas (LBE) e indicadores de desempeño energético (IDEn).
- ASHRAE Guideline 14-2014, Measurement of Energy, Demand, and Water Savings.
- Montgomery, D. C., *Introduction to Statistical Quality Control*, Wiley (capítulo de CUSUM).
