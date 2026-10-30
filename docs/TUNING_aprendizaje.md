# Aprendizaje operativo del laboratorio

**Doc de fine-tuning.** Cada corrida que arroja un número se escribe acá, con
el número, lo que se esperaba y lo que salió — **incluido lo que no funcionó**.
Un número que vive solo en el chat es una anécdota (L-129).

Última actualización: **2026-10-30**.

---

## 1. Lo que se midió sobre la cuenta real de Exness

| Qué | Medido | Yo suponía |
|---|---|---|
| Spread BTCUSD | **2,69 promedio · 8,58 máximo** | 25 (4-9x pesimista) |
| Spread ETHUSD | 0,0449% del precio | — (es el más caro en relativo) |
| Spread XAUUSD | 0,0062% | — |
| Comisión | **cero**, confirmada en el deal | 3,50/lote/lado |
| Swap BTCUSD largo | **−1.778,7** (unidad ambigua) | 0 |
| Swap corto | **0** en los tres instrumentos | — |
| Costo ida y vuelta real | **US$0,84 y fue TODO movimiento de precio** | spread + comisión |
| Rate limit global | **10/s** | no publicado |
| Rate limit velas | **2/s declarado, 1/s en la práctica** | no publicado |
| Velas por llamada | hasta **1.000** | 200 (me equivoqué) |
| Instrumentos | **334** (212 divisas, 111 acciones, 14 cripto, 12 metales, 9 índices) | ~40 |
| Apalancamiento disponible | **2000:1** | — |
| Saldo de la demo | **US$500** | simulaba con 1.000 |

**La ambigüedad del swap quedó resuelta por diseño, no por medición:** la regla
de intradía de Fernando (nunca mantener de un día para otro) significa que el
swap no se cobra nunca. La restricción eliminó la incertidumbre.

### Latencia, medida contra la API

| Endpoint | Mediana | Peor |
|---|---|---|
| `snapshot` (saldo y posiciones) | **1.137 ms** | 1.230 ms |
| `candles` | 591 ms | 1.030 ms |
| `access-point` | 338 ms | — |
| `account` | 189 ms | 305 ms |
| `conditions` | 159 ms | 170 ms |

**Antigüedad del dato al decidir: 44 s de mediana, 49 s el peor.** Para un ciclo
de 5 minutos es aceptable; para scalping no serviría.

---

## 2. Hipótesis que se probaron y FALLARON

Esto es lo más valioso del documento.

### "El oro y el petróleo tienen tendencias más claras" — FALSO

Ratio de eficiencia de Kaufman (movimiento neto / movimiento total, ventana 20),
sobre 4.000 barras diarias. **Un paseo aleatorio puro da 0,2305.**

| Activo | Eficiencia | vs. ruido |
|---|---|---|
| BTCUSD | 0,2653 | +15,1% |
| AAPL | 0,2624 | +13,8% |
| ETHUSD | 0,2565 | +11,3% |
| **Oro** | 0,2397 | **+4,0% — indistinguible de ruido** |
| **Petróleo WTI** | 0,2358 | **+2,3% — indistinguible de ruido** |
| Gas natural | 0,2112 | **−8,4% — más ruidoso que el azar** |

**Por qué la intuición engaña:** en un gráfico las tendencias pasadas se ven
obvias. En el momento no se ven. El que tiene la tendencia menos sucia es
BTCUSD. *Pendiente: medir intradía, que es donde se opera.*

### Intradía: la hipótesis del oro y el petróleo cae MÁS FUERTE

Medido con datos de Exness en barras de 5 minutos (900 barras ≈ 3 días).
Línea de ruido con la misma cantidad de barras: **0,2312**.

| Activo | Intradía vs ruido | Diario vs ruido |
|---|---|---|
| **BTCUSD** | **+10,0%** | +15,1% |
| Oro 24/7 | +1,1% | +4,0% |
| Oro | +0,3% | — |
| ETHUSD | −1,8% | +11,3% |
| EURUSD | −2,4% | −3,4% |
| Cobre | −5,5% | — |
| **USOIL** | **−11,2%** | +2,3% |
| **UKOIL** | **−13,9%** | — |

**El petróleo intradía es 11-14% MÁS aleatorio que una moneda.** No es que
no tenga tendencia: tiene *menos estructura que el azar*. El oro queda en la
línea del ruido en los dos marcos.

**Lo único por encima del ruido en AMBOS marcos y con DOS fuentes distintas
(yfinance diario y Exness M5) es BTCUSD.** Eso ya no es casualidad de una
ventana: es el hallazgo más sólido del laboratorio hasta ahora.

*Salvedad:* 900 barras M5 son 3 días. La medición diaria tenía 4.000 barras
(16 años). El número intradía apunta igual pero con muestra más débil. No se
quitan instrumentos del universo por esto: que decida el forward test, que es
la medición que no se puede cocinar.

### "Cuando sube el precio, bitcoin baja" — FALSO

Correlaciones de retornos diarios sobre 1.984 días. **Todas las de BTCUSD son
positivas, ninguna negativa.** La más cercana a cero es el petróleo (+0,03).

### "Los modelos de machine learning van a encontrar la ventaja" — FALSO

130 combinaciones (13 instrumentos × 10 estrategias), corrección por búsqueda
múltiple contando todas. Los tres modelos quedaron primeros en 11 de 13
instrumentos y **no calificaron en ninguno**: el mejor t-stat fue 1,99 contra un
umbral de 3,36. Y la **regresión logística** le ganó siempre al random forest y
al gradient boosting: con señal débil y muestra corta, los modelos complejos
memorizan ruido.

### "Subir el apalancamiento mejora el resultado" — FALSO

De 2x a 100x el resultado es **idéntico**: US$2.326. El sistema nunca usa más de
**1,80x** porque lo que ata el tamaño es el 0,5% de riesgo por operación.

### "Un margen de tolerancia en la ruptura evita el ruido" — AYUDA EN 1 DE 5

| Activo | sin margen | m=0,25 ATR |
|---|---|---|
| BTCUSD | **+543** | +505 |
| ETHUSD | **+481** | +462 |
| WTI | **+126** | +26 |
| SPY | **+77** | −41 |
| **Oro** | −9 | **+215** |

En diario cuesta más de lo que ahorra, salvo en el oro. **No se adopta:** elegir
el mejor ajuste por activo es data snooping. *Pendiente: medir intradía.*

### "La estrategia le gana a comprar y esperar" — FALSO, 0 de 5

| Activo | Pasiva | ruptura-20 |
|---|---|---|
| BTCUSD | **+$461.125** | +$924 |
| SOLUSD | **+$198.136** | +$479 |
| ETHUSD | **+$11.924** | +$785 |
| SPY | **+$10.341** | +$160 |
| Oro | **+$3.755** | +$400 |

Ajustado por drawdown la estrategia solo gana en ETHUSD (12,2 contra 6,3).
El "robusto al 100% en todo N" era **el mercado subiendo**, no la estrategia.

---

## 3. Lo que se aprendió de la estructura del mercado

### Los grupos de correlación escritos a mano mienten

Medidos sobre 1.984 días, umbral 0,70:

| Grupo | Miembros | Realidad |
|---|---|---|
| GRUPO_AAPL | AAPL, NVDA, QQQ, SPY | **una apuesta** |
| GRUPO_BTCUSD | BTCUSD, ETHUSD, SOLUSD | **una apuesta** |
| GRUPO_XAGUSD | Oro, Plata | **una apuesta** |
| Independientes | EURUSD · COPPER · **WTI** · NATGAS | 4 de 13 |

Pares más pegados: QQQ/SPY **+0,94**, BTCUSD/ETHUSD **+0,83**, Oro/Plata +0,78.

**Consecuencia:** operar BTCUSD y ETHUSD a la vez no diversifica — es una
posición del doble de tamaño. Los grupos ahora se **derivan de la medición**
(`labcore/correlaciones.py`), no de etiquetas.

**La ironía:** el petróleo es el único realmente descorrelacionado de todo, y
tiene tendencia de nivel-ruido. Ese es el intercambio real.

### El tamaño mínimo del contrato limita qué estrategias existen

Con lote mínimo 0,01 y riesgo 0,5% sobre US$10.000, el stop más ancho operable
son **5.000 ticks (~500 pips)**. Cualquier estrategia que necesite más **no es
expresable**. Con US$1.000, EURUSD directamente **no es operable**: 0
operaciones, las 10 estrategias sin poder dimensionar.

---

## 4. La aritmética de los objetivos

| Objetivo | Sobre | Es | Veredicto |
|---|---|---|---|
| US$500/día | US$1.000 | 50%/día | imposible |
| US$300/día | US$1.000 | 30%/día | imposible |
| US$200/día | US$2.000 | 10%/día | imposible |
| US$150/día | US$1.000 | 15%/día | **mecánicamente posible, estadísticamente ruinoso** |

Para US$150/día hace falta **1 lote de BTC (76x)**. A ese tamaño cada stop cuesta
**US$994 — el 99% de la cuenta**. Con 52-56% de aciertos, dos pérdidas seguidas
ocurren el 23% de las veces: **casi un día de cada cuatro.**

Capital necesario para US$150/día a retornos que existen:

| Retorno diario | Referencia | Capital |
|---|---|---|
| 0,10% | muy bueno (~28%/año) | US$150.000 |
| 0,20% | excepcional (~65%/año) | US$75.000 |
| 0,40% | el mejor fondo de la historia | US$37.500 |

---

## 5. Lo medido sobre la mecánica del laboratorio

| Hallazgo | Detalle |
|---|---|
| Un paseo aleatorio da eficiencia **0,2305** | la línea que hace interpretable todo lo demás |
| MinTRL con Sharpe 0,5 | **13,2 años** de serie limpia, POR estrategia |
| Sharpe desinflado, 1,5 con 200 pruebas | baja a **1,10** |
| Cambiar la ventana de datos **cambia los sobrevivientes** | AAPL calificaba con 46 años y no con 16 |
| Operar hacia adelante **no se puede cocinar** | el tiempo va en una sola dirección |

---

## 6. Los bugs propios, que son parte del aprendizaje

| # | Bug | Cómo se detectó |
|---|---|---|
| 1 | El Sharpe anualizado con √252 inflaba 7x y **certificaba ruido** | prueba del juez contra paseos aleatorios |
| 2 | El spread se cobraba solo en la entrada | la prueba de estrés daba el mismo P&L |
| 3 | El spread fijo sobre 46 años: US$0,02 al AAPL de 1980 (20% del precio) | leverage daba idéntico en 7 escenarios |
| 4 | Conté 10 pruebas cuando eran 130 | revisar el registro |
| 5 | Los cortes de pérdida solo miraban lo cerrado | Fernando preguntó cómo iba |
| 6 | `memory.high` estranguló el VPS en vez de aislar | load subió de 5,3 a 6,9 |
| 7 | `timestamp` y `sign_version` como texto, no número | **releer la doc antes de escribir** |
| 8 | `timeframe` "1m" en vez de "M1"; el parámetro `limit` no existe | error 3003 del servidor |
| 9 | `io.weight` declarado pero el controlador no está delegado | leer el cgroup, no `systemctl show` |
| 10 | El cron fallaba en silencio y salía con 0 | el log no tenía pasadas automáticas |
| 11 | Variable `c` del bucle pisó la cartera | el informe explotó con KeyError |
| 12 | Margen de spread arbitrario: 0,1% daba 76,50 a BTC contra 2,69 medido | mirar el número resultante |

**El patrón:** siete de los doce se detectaron porque **un número no cuadraba**,
no porque alguien revisara el código. De ahí la regla: cada medición se escribe y
se compara con lo esperado.

---

## 7. Qué está pendiente de medir

1. **Intradía**: eficiencia de tendencia, correlaciones y el margen de tolerancia
   en barras de 5 y 15 minutos. Es donde se opera y donde la intuición de
   Fernando sobre el oro y el petróleo podría sostenerse.
2. **Ejecución real contra demo**: slippage, requotes y rechazos. La demo llena
   al precio cotizado; el contrato lista `EXECUTION_REQUOTE` y
   `EXECUTION_REJECTED` porque pasan en cuentas reales.
3. **La distribución del spread** en las horas malas. Con 24 muestras ya se vio
   que BTCUSD va de 2,69 a 8,58 — varía 3,2 veces.
4. **El forward test**: la única evidencia que no se puede cocinar.
