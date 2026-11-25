"""Modelo de línea base energética (LBE) por regresión lineal múltiple.

Referencias de método (ver MODELO.md):
- ISO 50001:2018 §6.5 (EnPI) y §6.6 (línea base energética).
- ISO 50006:2023, indicadores y línea base normalizada por variables relevantes.
- ASHRAE Guideline 14-2014, criterios estadísticos para datos mensuales.
- Montgomery, Introduction to Statistical Quality Control, CUSUM tabular.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.stattools import durbin_watson

# Criterios de aceptación del modelo (supuestos M-04..M-07 en MODELO.md)
R2_MIN = 0.75
CVRMSE_MAX = 0.15      # ASHRAE G14, datos mensuales
NMBE_MAX = 0.05        # ASHRAE G14, datos mensuales
P_MAX = 0.05
N_MIN = 12


@dataclass
class ResultadoLB:
    y: str
    variables: list[str]
    coeficientes: pd.Series
    p_valores: pd.Series
    r2: float
    r2_ajustado: float
    cv_rmse: float
    nmbe: float
    n: int
    sigma: float                       # desviación estándar residual del ajuste
    modelo: object = field(repr=False)  # statsmodels RegressionResults

    def ecuacion(self) -> str:
        c = self.coeficientes
        partes = [f"{c['const']:,.0f}"]
        for v in self.variables:
            partes.append(f"{c[v]:+,.2f}·{v}")
        return f"{self.y} = " + " ".join(partes)


def ajustar_linea_base(df: pd.DataFrame, y: str, variables: list[str]) -> ResultadoLB:
    """Ajusta E = b0 + Σ bi·xi por mínimos cuadrados ordinarios."""
    if not variables:
        raise ValueError("Se necesita al menos una variable relevante.")
    datos = df[[y, *variables]].dropna()
    n, p = len(datos), len(variables)
    if n <= p + 1:
        raise ValueError(f"Datos insuficientes: n={n} para {p} variables.")
    X = sm.add_constant(datos[variables], has_constant="add")
    res = sm.OLS(datos[y], X).fit()
    resid = res.resid
    media = datos[y].mean()
    cv_rmse = float(np.sqrt((resid ** 2).sum() / (n - p - 1)) / media)
    nmbe = float(resid.sum() / ((n - p - 1) * media))
    return ResultadoLB(
        y=y, variables=list(variables), coeficientes=res.params, p_valores=res.pvalues,
        r2=float(res.rsquared), r2_ajustado=float(res.rsquared_adj),
        cv_rmse=cv_rmse, nmbe=nmbe, n=n, sigma=float(np.sqrt(res.scale)), modelo=res,
    )


def validar_modelo(res: ResultadoLB) -> pd.DataFrame:
    """Compara el ajuste contra los criterios de aceptación."""
    p_peor = float(res.p_valores.drop("const").max())
    dw = float(durbin_watson(res.modelo.resid))
    filas = [
        ("R² ≥ 0,75", res.r2, res.r2 >= R2_MIN),
        ("CV(RMSE) ≤ 15 %", res.cv_rmse, res.cv_rmse <= CVRMSE_MAX),
        ("|NMBE| ≤ 5 %", res.nmbe, abs(res.nmbe) <= NMBE_MAX),
        ("p de cada variable < 0,05", p_peor, p_peor < P_MAX),
        ("n ≥ 12 meses", res.n, res.n >= N_MIN),
        ("Durbin-Watson entre 1,5 y 2,5 (autocorrelación)", dw, 1.5 <= dw <= 2.5),
    ]
    return pd.DataFrame(filas, columns=["criterio", "valor", "cumple"])


def seleccionar_modelo(df: pd.DataFrame, y: str, candidatas: list[str]) -> pd.DataFrame:
    """Evalúa todas las combinaciones de variables candidatas.

    Un modelo es admisible si todas sus variables tienen p < 0,05 y coeficiente
    positivo (más producción o más grados día no pueden bajar el consumo).
    Se ordena por R² ajustado; el primero admisible es el recomendado.
    """
    filas = []
    for k in range(1, len(candidatas) + 1):
        for combo in combinations(candidatas, k):
            r = ajustar_linea_base(df, y, list(combo))
            coefs = r.coeficientes.drop("const")
            pv = r.p_valores.drop("const")
            filas.append({
                "variables": " + ".join(combo),
                "r2": r.r2, "r2_ajustado": r.r2_ajustado, "cv_rmse": r.cv_rmse,
                "p_max": float(pv.max()),
                "coef_positivos": bool((coefs > 0).all()),
                "admisible": bool((pv < P_MAX).all() and (coefs > 0).all()),
            })
    tabla = pd.DataFrame(filas).sort_values(["admisible", "r2_ajustado"], ascending=[False, False])
    return tabla.reset_index(drop=True)


def predecir(res: ResultadoLB, df: pd.DataFrame, alfa: float = 0.05) -> pd.DataFrame:
    """Consumo esperado según la línea base, con intervalo de predicción (1-alfa)."""
    X = sm.add_constant(df[res.variables], has_constant="add")
    pred = res.modelo.get_prediction(X).summary_frame(alpha=alfa)
    return pd.DataFrame({
        "esperado": pred["mean"].to_numpy(),
        "ip_inf": pred["obs_ci_lower"].to_numpy(),
        "ip_sup": pred["obs_ci_upper"].to_numpy(),
    }, index=df.index)


def cusum(real: pd.Series, esperado: pd.Series) -> pd.Series:
    """CUSUM de diferencias Σ(real − esperado). Pendiente negativa = ahorro."""
    return (real - esperado).cumsum()


def cusum_tabular(residuos: pd.Series, sigma: float, k: float = 0.5, h: float = 4.0,
                  recentrar: bool = True) -> pd.DataFrame:
    """CUSUM tabular de Page (Montgomery §9.1). k y h en múltiplos de sigma.

    C+ detecta aumentos sostenidos de consumo (pérdida de desempeño);
    C− detecta disminuciones sostenidas (mejora de desempeño).
    Con ``recentrar=True``, tras cada alarma se estima el nuevo nivel del residuo
    (μ ± K ± C/N, Montgomery ec. 9.4/9.5), se toma como nueva referencia y se
    reinician los acumuladores. Así una mejora ya confirmada no oculta una
    pérdida posterior (supuesto M-09).
    """
    K, H = k * sigma, h * sigma
    mu = 0.0
    cp = cm = 0.0
    np_, nm = 0, 0
    filas = []
    for e in residuos.to_numpy():
        cp = max(0.0, cp + (e - mu) - K)
        cm = max(0.0, cm - (e - mu) - K)
        np_ = np_ + 1 if cp > 0 else 0
        nm = nm + 1 if cm > 0 else 0
        sube, baja = cp > H, cm > H
        filas.append((cp, cm, mu, sube, baja))
        if recentrar and (sube or baja):
            mu = mu + K + cp / np_ if sube else mu - K - cm / nm
            cp = cm = 0.0
            np_ = nm = 0
    out = pd.DataFrame(filas, columns=["c_mas", "c_menos", "referencia", "alarma_aumento", "alarma_mejora"],
                       index=residuos.index)
    out.attrs["H"] = H
    return out


def analizar(df: pd.DataFrame, y: str, variables: list[str], inicio_base: str, fin_base: str,
             col_periodo: str = "mes", col_produccion: str | None = "produccion_t",
             k: float = 0.5, h: float = 4.0, recentrar: bool = True) -> tuple[ResultadoLB, pd.DataFrame]:
    """Flujo completo: ajusta la LBE en el periodo base y evalúa todo el horizonte."""
    df = df.sort_values(col_periodo).reset_index(drop=True)
    en_base = (df[col_periodo] >= inicio_base) & (df[col_periodo] <= fin_base)
    res = ajustar_linea_base(df[en_base], y, variables)

    out = df.copy()
    out["periodo"] = np.where(en_base, "base", np.where(df[col_periodo] > fin_base, "reporte", "previo"))
    out = out.join(predecir(res, out))
    out["diferencia"] = out[y] - out["esperado"]
    out["ahorro"] = -out["diferencia"]
    out["enpi_indice"] = out[y] / out["esperado"]          # EnPI normalizado (real/esperado)
    if col_produccion and col_produccion in out:
        out["enpi_kwh_t"] = out[y] / out[col_produccion]   # EnPI de cociente simple
    out["fuera_ip"] = (out[y] > out["ip_sup"]) | (out[y] < out["ip_inf"])

    rep = out["periodo"] == "reporte"
    out["cusum"] = np.nan
    out.loc[rep, "cusum"] = cusum(out.loc[rep, y], out.loc[rep, "esperado"])
    tab = cusum_tabular(out.loc[rep, "diferencia"], res.sigma, k=k, h=h, recentrar=recentrar)
    out = out.join(tab)
    out.attrs["H"] = tab.attrs["H"]
    return res, out
