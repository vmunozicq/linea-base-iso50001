import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

import generar_datos_sinteticos as gen  # noqa: E402
from lb50001 import (analizar, ajustar_linea_base, cusum, cusum_tabular,  # noqa: E402
                     seleccionar_modelo, validar_modelo)

VARS = ["produccion_t", "gdr_base18", "gdc_base15"]


@pytest.fixture(scope="module")
def datos():
    return pd.read_csv(RAIZ / "data" / "planta_sintetica.csv")


def test_csv_reproducible(datos):
    """El CSV publicado es exactamente el que produce el generador con su semilla."""
    nuevo = gen.generar().reset_index(drop=True)
    pd.testing.assert_frame_equal(nuevo.fillna(""), datos.fillna(""), check_dtype=False)


def test_regresion_recupera_coeficientes_exactos():
    rng = np.random.default_rng(0)
    x1, x2 = rng.uniform(0, 100, 50), rng.uniform(0, 50, 50)
    df = pd.DataFrame({"x1": x1, "x2": x2, "y": 1000 + 3 * x1 + 7 * x2})
    r = ajustar_linea_base(df, "y", ["x1", "x2"])
    assert r.coeficientes["const"] == pytest.approx(1000)
    assert r.coeficientes["x1"] == pytest.approx(3)
    assert r.coeficientes["x2"] == pytest.approx(7)
    assert r.r2 == pytest.approx(1)


def _esperado_verdadero(df):
    return (gen.CARGA_BASE_KWH + gen.KWH_POR_T * df.produccion_t
            + gen.KWH_POR_GDR * df.gdr_base18 + gen.KWH_POR_GDC * df.gdc_base15)


def test_linea_base_predice_el_consumo_verdadero(datos):
    """La LBE reproduce el consumo 'verdadero' (sin eventos ni ruido): error mensual < 4 %
    y sesgo medio < 1 % en todo el horizonte (hallazgo H-1 en MODELO.md)."""
    base = datos[datos.mes <= "2022-12"]
    _, out = analizar(datos, "consumo_kwh", VARS, "2021-01", "2022-12")
    verdad = _esperado_verdadero(out)
    err = (out.esperado - verdad) / verdad
    assert err.abs().max() < 0.04
    assert abs(err.mean()) < 0.01
    assert len(base) == 24


def test_cobertura_ic95_monte_carlo(datos):
    """Sobre 300 réplicas del ruido, el IC95 de cada coeficiente cubre el valor verdadero ~95 %.

    Con la semilla publicada, el IC95 de la constante y de kWh/t no cubre el valor
    verdadero (le tocó la 'mala' réplica): ver hallazgo H-1 en MODELO.md.
    """
    base = datos[datos.mes <= "2022-12"].copy()
    verdad = _esperado_verdadero(base)
    valores = {"const": gen.CARGA_BASE_KWH, "produccion_t": gen.KWH_POR_T,
               "gdr_base18": gen.KWH_POR_GDR, "gdc_base15": gen.KWH_POR_GDC}
    rng = np.random.default_rng(123)
    cubre = {v: 0 for v in valores}
    R = 300
    for _ in range(R):
        base["consumo_kwh"] = verdad + rng.normal(0, gen.RUIDO_KWH, len(base))
        ic = ajustar_linea_base(base, "consumo_kwh", VARS).modelo.conf_int()
        for v, val in valores.items():
            cubre[v] += ic.loc[v, 0] <= val <= ic.loc[v, 1]
    for v in valores:
        assert 0.90 <= cubre[v] / R <= 0.99, (v, cubre[v] / R)


def test_modelo_cumple_criterios(datos):
    r = ajustar_linea_base(datos[datos.mes <= "2022-12"], "consumo_kwh", VARS)
    assert validar_modelo(r)["cumple"].all()


def test_seleccion_recomienda_tres_variables(datos):
    tabla = seleccionar_modelo(datos[datos.mes <= "2022-12"], "consumo_kwh", VARS)
    assert tabla.iloc[0]["variables"] == "produccion_t + gdr_base18 + gdc_base15"
    assert tabla.iloc[0]["admisible"]


def test_ahorro_estimado_cercano_al_real(datos):
    _, out = analizar(datos, "consumo_kwh", VARS, "2021-01", "2022-12")
    rep = out[out.periodo == "reporte"]
    clima = rep
    sin_eventos = (gen.CARGA_BASE_KWH + gen.KWH_POR_T * rep.produccion_t
                   + gen.KWH_POR_GDR * clima.gdr_base18 + gen.KWH_POR_GDC * clima.gdc_base15)
    # ahorro "verdadero" neto de la mejora y la fuga (sin el ruido)
    mejora = np.where(rep.mes >= gen.MEJORA_DESDE, gen.MEJORA_FRACCION * sin_eventos, 0)
    fuga = np.where(rep.mes.isin(gen.FUGA_MESES), gen.FUGA_KWH, 0)
    verdadero = (mejora - fuga).sum()
    assert rep.ahorro.sum() == pytest.approx(verdadero, rel=0.25)


def test_cusum_es_suma_acumulada():
    real = pd.Series([10.0, 12, 8, 9])
    esp = pd.Series([10.0, 10, 10, 10])
    assert list(cusum(real, esp)) == [0, 2, 0, -1]


def test_cusum_tabular_sin_alarma_en_ruido():
    rng = np.random.default_rng(1)
    t = cusum_tabular(pd.Series(rng.normal(0, 1, 60)), sigma=1.0)
    assert not t.alarma_aumento.any() and not t.alarma_mejora.any()


def test_cusum_tabular_detecta_escalon():
    e = pd.Series([0.0] * 10 + [2.0] * 10)
    t = cusum_tabular(e, sigma=1.0, k=0.5, h=4.0)
    assert not t.alarma_aumento.iloc[:10].any()
    # con escalón de 2σ y k=0,5: C+ crece 1,5 por mes y supera 4 al tercer mes
    assert t.alarma_aumento.idxmax() == 12


def test_detecta_eventos_sembrados(datos):
    _, out = analizar(datos, "consumo_kwh", VARS, "2021-01", "2022-12")
    rep = out[out.periodo == "reporte"].set_index("mes")
    primera_mejora = rep.index[rep.alarma_mejora][0]
    assert "2023-07" <= primera_mejora <= "2023-10"   # VDF desde 2023-07
    assert rep.loc["2024-05":"2024-07", "alarma_aumento"].any()  # fuga 2024-05..07
    assert not rep.loc[:"2024-04", "alarma_aumento"].any()      # sin falsos aumentos antes


def test_errores_de_entrada():
    df = pd.DataFrame({"y": [1.0, 2.0], "x": [1.0, 2.0]})
    with pytest.raises(ValueError):
        ajustar_linea_base(df, "y", [])
    with pytest.raises(ValueError):
        ajustar_linea_base(df, "y", ["x"])


def test_plantilla_tiene_columnas_de_la_demo(datos):
    plantilla = pd.read_csv(RAIZ / "data" / "plantilla_entrada.csv")
    assert set(plantilla.columns) <= set(datos.columns)
    assert {"mes", "consumo_kwh"} <= set(plantilla.columns)
