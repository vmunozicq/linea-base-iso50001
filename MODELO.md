# MODELO.md — Línea base energética (ISO 50001 / ISO 50006)

> **Estado: borrador para revisión de Vicente.** Claude Code escribió el código y este borrador.
> Los supuestos, ecuaciones y criterios son de Vicente: cada ítem marcado **[REVISAR]** debe
> confirmarse, corregirse o justificarse antes de publicar el repositorio.

## 1. Objetivo

Construir la línea base energética (LBE) de una planta, calcular indicadores de desempeño
energético (EnPI), cuantificar ahorros normalizados y detectar cambios de desempeño con CUSUM,
siguiendo el enfoque de ISO 50001:2018 (§6.5 EnPI, §6.6 LBE) e ISO 50006 (LBE normalizada por
variables relevantes).

## 2. Datos

| Dato | Origen | Tipo |
|---|---|---|
| Temperatura media diaria, Santiago (−33,45; −70,66), 2021–2024 | Open-Meteo Historical Weather API (reanálisis ERA5) | **Real**, CC BY 4.0 |
| Grados día mensuales (GDC base 15 °C, GDR base 18 °C) | Calculados desde lo anterior | Derivado |
| Producción mensual (t) | `scripts/generar_datos_sinteticos.py`, semilla 50001 | **Sintético** |
| Consumo eléctrico mensual (kWh) | Ídem | **Sintético** |
| Eventos (mejora y fuga) | Sembrados en el generador | **Sintético** |

Supuestos de datos:

- **S-01 [REVISAR]** Planta ficticia con `E = 85 000 + 110·P + 420·GDR + 160·GDC + ε`, ε ~ N(0; 4 000 kWh).
  Son órdenes de magnitud plausibles para una planta de alimentos/química liviana con refrigeración,
  no datos de una planta real. ¿Los ajustamos a algo que conozcas (por ejemplo, kWh/t típico de un rubro)?
- **S-02 [REVISAR]** Eventos sembrados en el periodo de reporte: variadores de frecuencia en chillers
  desde 2023-07 (−5 % del consumo) y fuga de aire comprimido 2024-05 a 2024-07 (+14 000 kWh/mes).
- **S-03** Producción con estacionalidad (±90 t) y +8 % en 2024, para mostrar por qué el EnPI de
  cociente simple (kWh/t) engaña.
- **S-04 [REVISAR]** Bases de grados día: 15 °C para calefacción y 18 °C para refrigeración. Son
  convenciones; ISO 50006 sugiere estimar el punto de equilibrio de la propia instalación
  (regresión por tramos o *change-point*). Falta citar la convención chilena que prefieras.
- **S-05** Open-Meteo es reanálisis en grilla, no una estación DMC. Para un caso real conviene la
  estación de Quinta Normal o Pudahuel (Dirección Meteorológica de Chile).
- **S-06 [REVISAR]** Los meses no se normalizan por número de días; la carga base se modela como
  kWh/mes constante. Alternativa: agregar `dias` como variable.

## 3. Modelo

### 3.1 Línea base (regresión lineal múltiple por MCO)

E_esperado = b0 + b1·P + b2·GDR + b3·GDC

- **M-01** Periodo base: 2021-01 a 2022-12 (24 meses). Periodo de reporte: 2023-01 a 2024-12.
- **M-02** Selección de variables: se ajustan todas las combinaciones de candidatas; es *admisible*
  si cada variable tiene p < 0,05 y coeficiente positivo (más producción o más grados día no pueden
  bajar el consumo). Se recomienda la admisible con mayor R² ajustado.
- **M-03** Intervalo de predicción 95 % para cada mes (incluye incertidumbre del ajuste y del ruido).

### 3.2 Criterios de aceptación **[REVISAR]**

ISO 50006 exige que el modelo sea estadísticamente válido pero no fija umbrales numéricos. Se
tomaron de ASHRAE Guideline 14-2014 (datos mensuales) y práctica habitual:

| Id | Criterio | Umbral | Fuente |
|---|---|---|---|
| M-04 | R² | ≥ 0,75 | Práctica habitual (guías de LBE / IPMVP) |
| M-05 | CV(RMSE) | ≤ 15 % | ASHRAE G14, mensual |
| M-06 | NMBE | ±5 % | ASHRAE G14, mensual (en MCO con constante es ≈0 por construcción) |
| M-07 | p de cada variable | < 0,05 | Estadística clásica |
| M-08 | Durbin-Watson | 1,5–2,5 | Regla práctica de autocorrelación |

CV(RMSE) = √(Σe²/(n−p−1)) / Ē  NMBE = Σe / ((n−p−1)·Ē)

### 3.3 EnPI y ahorro

- EnPI de cociente: kWh/t (solo informativo).
- EnPI normalizado: E_real / E_esperado (1 = igual a la línea base; < 1 = mejor desempeño).
- Ahorro mensual = E_esperado − E_real; ahorro acumulado del periodo de reporte.

### 3.4 Detección de desviaciones

- **CUSUM de diferencias**: Σ(E_real − E_esperado) en el periodo de reporte. Un cambio de
  pendiente indica el mes en que cambió el desempeño.
- **Mes fuera del IP 95 %**: desviación puntual.
- **CUSUM tabular de Page** (Montgomery, *Introduction to Statistical Quality Control*, cap. 9):
  C⁺ᵢ = máx(0; C⁺ᵢ₋₁ + eᵢ − μ − K), C⁻ᵢ = máx(0; C⁻ᵢ₋₁ − (eᵢ − μ) − K), con K = k·σ y H = h·σ.
  - **M-09 [REVISAR]** k = 0,5 y h = 4 (ARL₀ ≈ 168 meses, detecta un cambio de 1σ en ~8,4 meses).
  - **M-10 [REVISAR]** σ = desviación residual del ajuste base. Fuera de muestra el error real es algo
    mayor (incertidumbre de los coeficientes), así que la tasa de falsas alarmas puede ser mayor a la nominal.
  - **M-11 [REVISAR]** Tras cada alarma se *recentra*: la nueva referencia μ es el nivel estimado
    (μ ± K ± C/N) y se reinician los acumuladores. Sin esto, una mejora ya confirmada oculta una
    pérdida posterior (la fuga de 2024 no se detectaba).

## 4. Validación (contra la "verdad" del generador)

Como los datos son sintéticos, sabemos qué debía encontrar el modelo. Todo esto está en `tests/`.

| Prueba | Resultado |
|---|---|
| Selección de variables | Recomienda P + GDR + GDC (las tres verdaderas). R² = 0,951; CV(RMSE) = 1,9 %; DW = 2,44 |
| Cobertura del IC95 de los coeficientes (300 réplicas Monte Carlo) | Entre 90 % y 99 % para los cuatro coeficientes |
| Error de la LBE vs consumo verdadero sin ruido | Máx. 3,1 % mensual; sesgo medio +0,55 % en reporte |
| Ahorro acumulado 2023–2024 | Estimado 173,2 MWh vs verdadero 160,7 MWh (+7,8 %) |
| Detección de la mejora (desde 2023-07) | Alarma C⁻ en 2023-09 (2 meses de retardo) |
| Detección de la fuga (2024-05 a 07) | Alarma C⁺ en 2024-05 (mismo mes) |
| Falsas alarmas de aumento antes de la fuga | Ninguna |

### Hallazgos para discutir

- **H-1** Con la semilla publicada, la constante estimada (61 500 kWh) y el kWh/t (135,9) quedan
  justo fuera de sus IC95 respecto de la verdad (85 000 y 110). La producción varía poco (≈±10 %),
  así que constante y pendiente se confunden entre sí. El modelo **predice bien** (error < 3,1 %)
  pero sus coeficientes **no deben leerse** como "carga base" ni "consumo específico" físicos.
  Es una lección útil para el video: buena predicción ≠ coeficientes interpretables.
- **H-2** El EnPI de cociente (kWh/t) baja 5,2 % en 2024 respecto del periodo base, pero parte de eso
  es dilución de la carga base por +8 % de producción. El EnPI normalizado da −3,2 % en todo el reporte.
- **H-3** Tras la primera alarma de mejora, la referencia recentrada (−7 500 kWh) subestima el nuevo
  nivel real (≈ −11 000), lo que genera una segunda alarma de mejora en 2024-02. Es un retardo
  conocido del recentrado; se podría usar la media de los meses posteriores a la alarma.
- **H-4** Falta la incertidumbre del ahorro (ASHRAE G14, ec. 4-6 / IPMVP). Trabajo futuro.

## 5. Lista de revisión para Vicente

- [ ] S-01, S-02: magnitudes de la planta y de los eventos.
- [ ] S-04: bases de grados día y su referencia.
- [ ] S-06: normalizar o no por días del mes.
- [ ] M-04 a M-08: criterios de aceptación y sus fuentes.
- [ ] M-09 a M-11: parámetros del CUSUM tabular y recentrado.
- [ ] H-1 a H-4: redacción de los hallazgos en tus palabras.
