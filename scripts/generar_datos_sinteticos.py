"""Genera los datos SINTÉTICOS de producción y consumo eléctrico de una planta ficticia.

El clima (grados día) es REAL (Open-Meteo, Santiago). La producción, el consumo y los
eventos son INVENTADOS para la demostración; no corresponden a ninguna planta real.

Uso:  python scripts/generar_datos_sinteticos.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SEMILLA = 50001

# "Verdad" del generador (supuesto S-01 en MODELO.md). El modelo NO conoce estos valores.
CARGA_BASE_KWH = 85_000.0      # kWh/mes independientes de producción y clima
KWH_POR_T = 110.0               # kWh por tonelada producida
KWH_POR_GDR = 420.0             # kWh por grado día de refrigeración (base 18 °C)
KWH_POR_GDC = 160.0             # kWh por grado día de calefacción (base 15 °C)
RUIDO_KWH = 4_000.0             # desviación estándar del ruido

# Eventos sembrados en el periodo de reporte (supuesto S-02)
MEJORA_DESDE = "2023-07"        # variadores de frecuencia en chillers: -5 % del consumo
MEJORA_FRACCION = 0.05
FUGA_MESES = ["2024-05", "2024-06", "2024-07"]   # fuga de aire comprimido
FUGA_KWH = 14_000.0


def generar() -> pd.DataFrame:
    rng = np.random.default_rng(SEMILLA)
    clima = pd.read_csv(RAIZ / "data" / "clima_santiago_mensual.csv")
    n = len(clima)
    mes_num = pd.to_datetime(clima["mes"]).dt.month.to_numpy()
    anio = pd.to_datetime(clima["mes"]).dt.year.to_numpy()

    estacional = 90 * np.sin(2 * np.pi * (mes_num - 3) / 12)
    crecimiento = np.where(anio >= 2024, 1.08, 1.0)
    produccion = (1000 + estacional + rng.normal(0, 70, n)) * crecimiento
    produccion = np.round(produccion, 1)

    esperado = (CARGA_BASE_KWH + KWH_POR_T * produccion
                + KWH_POR_GDR * clima["gdr_base18"] + KWH_POR_GDC * clima["gdc_base15"])
    consumo = esperado + rng.normal(0, RUIDO_KWH, n)
    mejora = clima["mes"] >= MEJORA_DESDE
    consumo = np.where(mejora, consumo * (1 - MEJORA_FRACCION), consumo)
    consumo = np.where(clima["mes"].isin(FUGA_MESES), consumo + FUGA_KWH, consumo)

    df = clima[["mes", "dias", "gdc_base15", "gdr_base18"]].copy()
    df["produccion_t"] = produccion
    df["consumo_kwh"] = np.round(consumo, 0)
    df["evento_sembrado"] = ""
    df.loc[mejora, "evento_sembrado"] = "VDF chillers (-5%)"
    df.loc[df["mes"].isin(FUGA_MESES), "evento_sembrado"] = "VDF chillers (-5%) + fuga aire comprimido"
    df["origen"] = "clima real Open-Meteo; produccion/consumo SINTETICOS"
    return df


if __name__ == "__main__":
    salida = RAIZ / "data" / "planta_sintetica.csv"
    generar().to_csv(salida, index=False)
    print(f"Escrito {salida}")
