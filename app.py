"""App Streamlit: línea base energética ISO 50001 / 50006 con CUSUM.

Ejecutar:  streamlit run app.py
"""
import io
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from lb50001 import analizar, seleccionar_modelo, validar_modelo  # noqa: E402

DATOS_DEMO = Path(__file__).parent / "data" / "planta_sintetica.csv"

st.set_page_config(page_title="Línea base ISO 50001", layout="wide")
st.title("Línea base energética y CUSUM (ISO 50001 / ISO 50006)")
st.caption("Proyecto personal de portafolio. Datos de demostración: clima REAL de Santiago "
           "(Open-Meteo, CC BY 4.0); producción y consumo SINTÉTICOS de una planta ficticia.")

# ---------------- Datos ----------------
with st.sidebar:
    st.header("1. Datos")
    archivo = st.file_uploader("CSV propio (opcional)", type="csv",
                               help="Columnas: mes (AAAA-MM), consumo y variables relevantes.")
    df = pd.read_csv(archivo) if archivo else pd.read_csv(DATOS_DEMO)
    if not archivo:
        st.info("Usando datos de demostración (sintéticos).")
    df["mes"] = df["mes"].astype(str)
    numericas = [c for c in df.select_dtypes("number").columns if c != "dias"]
    y = st.selectbox("Consumo energético", numericas,
                     index=numericas.index("consumo_kwh") if "consumo_kwh" in numericas else 0)
    candidatas = st.multiselect("Variables relevantes candidatas", [c for c in numericas if c != y],
                                default=[c for c in ["produccion_t", "gdr_base18", "gdc_base15"] if c in numericas])
    col_prod = st.selectbox("Variable de producción (EnPI kWh/unidad)", ["(ninguna)", *candidatas],
                            index=1 if "produccion_t" in candidatas else 0)

    st.header("2. Periodo base")
    meses = sorted(df["mes"].unique())
    ini, fin = st.select_slider("Periodo de línea base", options=meses,
                                value=(meses[0], meses[min(23, len(meses) - 2)]))

    st.header("3. CUSUM tabular")
    k = st.number_input("k (holgura, × σ)", 0.1, 2.0, 0.5, 0.1)
    h = st.number_input("h (umbral, × σ)", 1.0, 10.0, 4.0, 0.5)
    recentrar = st.checkbox("Recentrar tras cada alarma", True)

if not candidatas:
    st.warning("Elige al menos una variable relevante.")
    st.stop()

base = df[(df["mes"] >= ini) & (df["mes"] <= fin)]
seleccion = seleccionar_modelo(base, y, candidatas)

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Modelo de línea base", "EnPI", "CUSUM", "Desviaciones", "Datos y exportación"])

with tab1:
    st.subheader("Selección de variables (periodo base)")
    st.dataframe(seleccion.style.format({"r2": "{:.3f}", "r2_ajustado": "{:.3f}",
                                         "cv_rmse": "{:.1%}", "p_max": "{:.4f}"}), use_container_width=True)
    admisibles = seleccion[seleccion["admisible"]]
    opciones = list(seleccion["variables"])
    recomendado = admisibles["variables"].iloc[0] if len(admisibles) else opciones[0]
    elegido = st.selectbox("Modelo a usar", opciones, index=opciones.index(recomendado),
                           help="Por defecto: el admisible con mayor R² ajustado.")
    variables = elegido.split(" + ")

res, out = analizar(df, y, variables, ini, fin,
                    col_produccion=None if col_prod == "(ninguna)" else col_prod,
                    k=k, h=h, recentrar=recentrar)
rep = out[out["periodo"] == "reporte"]

with tab1:
    st.markdown(f"**Ecuación:** `{res.ecuacion()}`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("R²", f"{res.r2:.3f}")
    c2.metric("R² ajustado", f"{res.r2_ajustado:.3f}")
    c3.metric("CV(RMSE)", f"{res.cv_rmse:.1%}")
    c4.metric("n meses base", res.n)
    val = validar_modelo(res)
    st.dataframe(val, use_container_width=True, hide_index=True)
    if not val["cumple"].all():
        st.error("El modelo no cumple todos los criterios: revisa variables o periodo base.")
    coefs = pd.DataFrame({"coeficiente": res.coeficientes, "p": res.p_valores,
                          "IC95 inf": res.modelo.conf_int()[0], "IC95 sup": res.modelo.conf_int()[1]})
    st.dataframe(coefs.style.format("{:,.4g}"), use_container_width=True)

    fig = go.Figure()
    fig.add_scatter(x=out["mes"], y=out["ip_sup"], line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=out["mes"], y=out["ip_inf"], fill="tonexty", line=dict(width=0),
                    fillcolor="rgba(100,149,237,0.2)", name="IP 95 %")
    fig.add_scatter(x=out["mes"], y=out["esperado"], name="Esperado (línea base)", line=dict(dash="dash"))
    fig.add_scatter(x=out["mes"], y=out[y], name="Real", mode="lines+markers")
    fig.add_vrect(x0=ini, x1=fin, fillcolor="gray", opacity=0.08, line_width=0,
                  annotation_text="periodo base", annotation_position="top left")
    fig.update_layout(yaxis_title=y, height=420, margin=dict(t=30))
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure(go.Scatter(x=out.loc[out.periodo == "base", "esperado"],
                                y=out.loc[out.periodo == "base", y], mode="markers", name="base"))
    lim = [out[y].min(), out[y].max()]
    fig2.add_scatter(x=lim, y=lim, mode="lines", name="1:1", line=dict(dash="dot"))
    fig2.update_layout(xaxis_title="Esperado", yaxis_title="Real", height=380, margin=dict(t=30))
    st.plotly_chart(fig2, use_container_width=True)

with tab2:
    st.subheader("Indicadores de desempeño energético (periodo de reporte)")
    if len(rep):
        ahorro = rep["ahorro"].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Ahorro acumulado", f"{ahorro:,.0f}", help="Σ(esperado − real)")
        c2.metric("Ahorro relativo", f"{ahorro / rep['esperado'].sum():.1%}")
        c3.metric("EnPI normalizado medio (real/esperado)", f"{rep['enpi_indice'].mean():.3f}")
    fig = go.Figure()
    fig.add_scatter(x=out["mes"], y=out["enpi_indice"], name="Real / esperado", mode="lines+markers")
    fig.add_hline(y=1, line_dash="dot")
    fig.update_layout(yaxis_title="EnPI normalizado", height=350, margin=dict(t=30))
    st.plotly_chart(fig, use_container_width=True)
    if "enpi_kwh_t" in out:
        st.markdown("**EnPI de cociente simple (kWh por unidad)**. No corrige por clima ni por carga base, "
                    "por eso puede mostrar mejoras o pérdidas que no existen.")
        fig = go.Figure(go.Scatter(x=out["mes"], y=out["enpi_kwh_t"], mode="lines+markers"))
        fig.update_layout(yaxis_title="kWh / unidad", height=300, margin=dict(t=30))
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("CUSUM de diferencias Σ(real − esperado)")
    st.caption("Pendiente negativa: el consumo está por debajo de la línea base (ahorro). "
               "Un cambio de pendiente marca el mes en que cambió el desempeño.")
    fig = go.Figure(go.Scatter(x=rep["mes"], y=rep["cusum"], mode="lines+markers"))
    fig.add_hline(y=0, line_dash="dot")
    fig.update_layout(yaxis_title="CUSUM", height=380, margin=dict(t=30))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("CUSUM tabular (Page)")
    H = out.attrs["H"]
    fig = go.Figure()
    fig.add_scatter(x=rep["mes"], y=rep["c_mas"], name="C+ (aumento)", mode="lines+markers")
    fig.add_scatter(x=rep["mes"], y=-rep["c_menos"], name="−C− (mejora)", mode="lines+markers")
    fig.add_hline(y=H, line_color="red", annotation_text="H")
    fig.add_hline(y=-H, line_color="green", annotation_text="−H")
    fig.update_layout(height=380, margin=dict(t=30))
    st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("Meses con desviación")
    cols = ["mes", y, "esperado", "diferencia", "fuera_ip", "alarma_aumento", "alarma_mejora"]
    if "evento_sembrado" in rep:
        cols.append("evento_sembrado")
    marcados = rep[rep["fuera_ip"] | rep["alarma_aumento"] | rep["alarma_mejora"]][cols]
    st.dataframe(marcados.style.format({y: "{:,.0f}", "esperado": "{:,.0f}", "diferencia": "{:+,.0f}"}),
                 use_container_width=True, hide_index=True)
    st.caption("fuera_ip: el mes cae fuera del intervalo de predicción 95 %. "
               "alarma_*: el CUSUM tabular superó H (cambio sostenido).")

with tab5:
    st.dataframe(out, use_container_width=True)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="resultados", index=False)
        seleccion.to_excel(xw, sheet_name="seleccion_modelo", index=False)
        validar_modelo(res).to_excel(xw, sheet_name="validacion", index=False)
        pd.DataFrame({"coeficiente": res.coeficientes, "p": res.p_valores}).to_excel(xw, sheet_name="coeficientes")
    st.download_button("Descargar Excel", buf.getvalue(), "linea_base_iso50001.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
