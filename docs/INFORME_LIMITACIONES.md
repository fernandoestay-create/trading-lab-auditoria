# Informe de limitaciones — laboratorio de trading

**Fecha: 2026-10-28.** Todas las cifras de este documento se midieron ese día.
Un número medido muere cuando cambia la arquitectura: si cambias capital, lote
mínimo, límite de riesgo o instrumento, **recalcúlalos, no los heredes**.

---

## 1. Lo que este laboratorio NO puede decirte

**No puede decirte que una estrategia va a ser rentable.** Puede decirte que una
estrategia *no sobrevive* el escrutinio, lo cual es la mayoría de las veces el
resultado útil.

**No puede crear observaciones que no existen.** Con un Sharpe de 0,5 hacen falta
**13,2 años** de serie limpia para distinguirlo de cero al 95% — cifra que este
laboratorio reproduce de forma independiente con `anos_minimos(0.5)`. XAUUSD
tiene del orden de 23 años de historia. EURUSD, XAUUSD y BTCUSD están
correlacionados por el factor dólar: no son tres experimentos independientes.

**La corrección por búsqueda múltiple es necesaria, no suficiente.** Hay
evidencia publicada de que un oráculo deliberadamente tramposo con Sharpe 35
pasa intacto el filtro de Sharpe desinflado. Por eso el laboratorio exige
**tres** barreras a la vez (muestra mínima, t-stat corregido por Šidák, y
Sharpe desinflado positivo), y aun así el veredicto máximo que emite es
*"sobrevive EN MUESTRA"*, nunca *"es rentable"*.

---

## 2. Errores reales que se encontraron construyendo esto

Se dejan escritos porque son el tipo de error que se repite, y porque si no
están aquí, mañana no hay forma de saber que existieron.

### 2.1 El spread se cobraba solo en la entrada  (corregido)
Como el stop y el objetivo se fijan **relativos al precio de entrada**, al
ensanchar el spread todo se desplazaba en bloque y el costo se cancelaba: la
prueba de estrés con spread ×5 daba **exactamente el mismo P&L** que con spread
×1. Una posición larga entra al *ask* y sale al *bid*: el spread se paga en los
dos lados. Lo detectó la prueba `test_estres_de_spread_empeora_el_resultado`.

### 2.2 El Sharpe se anualizaba con √252  (corregido — el error más grave)
Se calculaban retornos **por operación** y se anualizaban como si hubiera una
operación diaria. Con 55 operaciones en 3.000 barras diarias hay ~4,6 al año, no
252: eso infló el Sharpe unas **7 veces**. Consecuencia medida: el torneo
**certificó tres estrategias sobre paseos aleatorios puros**, una con Sharpe
2,50. Tras corregir, ese 2,50 pasó a **0,41** y ninguna califica.
Ahora se anualiza con la frecuencia real: `operaciones / años de datos`.

### 2.3 El veredicto y la calificación se contradecían  (corregido)
El veredicto decía *"INSUFICIENTE: solo 55 operaciones"* y `califican()` las
dejaba pasar igual. Dos partes del mismo juez en desacuerdo es un bug, no un
matiz. Ahora ambas leen la misma constante `MIN_OPERACIONES = 100`.

### 2.4 El benchmark pasivo no operaba, y nadie se enteraba  (corregido)
`comprar-y-mantener` aparecía con **0 operaciones** en todas las corridas. No
era falta de oportunidades: con un stop de 50×ATR el tamaño que cabe en el 0,5%
de riesgo daba 0,0017 lotes, **bajo el mínimo del contrato**, así que la orden
nunca se construía — y eso no se contaba en ninguna parte. Un benchmark que no
opera no es vara de nada. Ahora existe `senales_sin_orden` con su motivo, y el
resumen lo denuncia.

### 2.5 Estado compartido entre corridas del torneo  (corregido)
Se reutilizaban las mismas instancias de estrategia entre series. Las que tienen
estado (el generador de `Aleatoria`, la bandera de `ComprarYMantener`)
arrastraban ese estado: la pasiva disparaba en la primera serie y nunca más.

### 2.6 `memory.high` estranguló el VPS en vez de proteger a Hermes  (corregido)
El primer techo de recursos usaba `MemoryHigh=1G`. Con el swap de la máquina ya
al 80%, eso produjo thrashing indefinido: el load subió de **5,3 a 6,9** y
empeoró el I/O de toda la máquina — lo contrario de proteger a Hermes. El
contador del kernel registró **35.150 estrangulamientos**. Ahora solo
`MemoryMax=1536M` y `MemorySwapMax=0`: un muro que mata limpio. Verificado por
efecto: `memory.events` → `oom_kill` pasó de 1 a 2.

---

## 3. Limitaciones conocidas y NO corregidas

### 3.1 El tope de riesgo subestima la pérdida real
El 0,5% se calcula sobre la distancia al stop. Pero al cerrar se paga medio
spread más, así que la pérdida real **excede** el nominal. Medido: riesgo
nominal 50,00 USD → pérdida real 50,10 USD. Es pequeño por operación y
sistemático en el agregado. Fijado en la prueba
`test_si_la_barra_toca_stop_y_objetivo_gana_el_stop`.

### 3.2 Restricción estructural: el stop más ancho operable
Con lote mínimo 0,01 y riesgo 0,5% sobre US$10.000, el stop más ancho que se
puede operar son **5.000 ticks** (~500 pips en EURUSD). Cualquier estrategia que
necesite más **no es expresable** con estos parámetros. Esto limita el catálogo
de estrategias antes de cualquier consideración de rentabilidad.

### 3.3 Los costos NO están medidos
`COSTOS_SIN_MEDIR` se llama así a propósito. Las cifras que usan los scripts de
prueba son del orden correcto para EURUSD pero **no se midieron en la cuenta
real**. Un modelo de costos heredado de un blog es peor que ninguno, porque
produce un backtest que parece creíble. **Esto es lo primero que hay que
arreglar, y es gratis:** 30 días registrando spread y swap reales.

### 3.4 No hay datos de mercado reales todavía
Todo lo validado hasta ahora corre sobre series sintéticas, a propósito: sirven
para probar el juez, no para medir estrategias. Hasta que no entren datos
reales, **ningún resultado de este laboratorio dice nada sobre los mercados**.

### 3.5 Sin datos intrabarra, el desempate es un supuesto
Si una barra toca stop y objetivo, se asume que tocó el stop. Es el supuesto
conservador y es el correcto por defecto, pero **es un supuesto**: con datos de
ticks se sabría cuál ocurrió primero.

### 3.6 Walk-forward y Monte Carlo: pendientes
El laboratorio hace in-sample con corrección por búsqueda múltiple. Faltan
walk-forward, Monte Carlo sobre el orden de las operaciones, y el período
sellado. **Mientras falten, el veredicto máximo posible sigue siendo
"sobrevive en muestra".**

---

## 4. Sobre la API de Exness

- **La firma es Ed25519, no HMAC.** La llave privada nunca viaja. Buena noticia
  para la seguridad.
- **Los rate limits no tienen ningún número público.** El contrato OpenAPI
  define la forma (`methods[].rate_limit{limit, window_seconds}`) pero cero
  valores. Solo se conocen llamando a `GET /v1/configuration/accounts/{id}/limits`
  con credencial real. **No se puede estimar la viabilidad de una estrategia de
  alta frecuencia antes de tener credencial.**
- **No hay implementación de referencia de la firma.** La doc dice que
  `buildSignedHeaders` es *"ilustrativo y no provisto"*, y no fija la
  serialización exacta del JSON ni la tolerancia del timestamp.
- **Cuentas demo: silencio total.** Cero menciones de `demo` en 31 páginas y en
  el contrato OpenAPI. **No está documentado que se pueda hacer paper trading
  con cotizaciones reales vía API sin una cuenta real.** Esto golpea directo a
  la Fase J del plan original.
- **No hay cobro documentado** por acceder a la API: cero menciones de fee,
  subscription o access charge. Lo que se paga es el costo de operar.

---

## 5. Lo que NO se construyó, y por qué

| Fase | Estado | Por qué |
|---|---|---|
| B — RAG de libros | **PENDIENTE** | Los 5 libros listados son comerciales. No se bajan de fuentes no autorizadas. Falta la ruta de los que Fernando tenga comprados. |
| C — Investigador LLM | **PENDIENTE a propósito** | Decisión de alcance: el LLM entra como *crítico* de backtests, no como generador de estrategias. Hay evidencia publicada de que la generación por LLM no sobrevive evaluación honesta. |
| D — Motor de datos | **PARCIAL** | DuckDB y pyarrow instalados; falta la ingesta real y la validación de series. |
| G — Entrenamiento automático | **PENDIENTE** | Sin datos reales y sin costos medidos, automatizar la búsqueda solo multiplica el data snooping. |
| J — Paper trading | **BLOQUEADO** | Depende de si la API admite cuentas demo, que no está documentado. |
| K — Adaptador de ejecución | **PENDIENTE** | No se habilita ejecución real. Requiere autorización explícita y separada. |
| L — Telegram | **PENDIENTE** | Va por `~/bin/avisar-telegram.sh`, nunca por `hermes send`. |
| M — Dashboard | **PENDIENTE** | El VPS tiene I/O al 21% de stall. Un servicio más necesita justificarse. |

---

## 6. La siguiente mejora de mayor valor

**Medir los costos reales de la cuenta durante 30 días.** Cuesta cero pesos, no
necesita credenciales de trading, y es la que más incertidumbre elimina: si el
spread y el swap reales de XAUUSD se comen el margen de las estrategias
clásicas, el proyecto se cierra antes de gastar un peso más. Todo lo demás
—datos históricos, walk-forward, el investigador— depende de que esa respuesta
sea favorable.

---

## 7. Corregido después del cierre: las métricas no persistían (L-129)

**Hallado el 2026-10-28, después de escribir el resumen ejecutivo.** Al confirmar
que no existía trabajo previo de trading apareció **L-129** del workspace: el
Revisor EIA se vendía con *"76% de recall en backtesting"* y la auditoría encontró
que el script **imprimía por pantalla y no escribía sus insumos a disco**. El
número se transcribió a mano desde la consola y se replicó a siete documentos sin
que nadie lo volviera a medir. La lección: *una métrica que no persiste no es una
métrica, es una anécdota*.

**Este laboratorio cometía el mismo error.** `prueba_del_juez.py` y
`prueba_de_potencia.py` imprimían sus tablas y no guardaban nada. El Sharpe de
0,41, el t=5,48 y el *"ninguna califica"* que se reportaron en el resumen
ejecutivo existían **solo en la salida de consola** — camino directo a volverse
el mismo folclore que L-129 documenta.

**Corregido:** `labcore/experimentos/registro.py` persiste cada corrida en
JSONL append-only con las cuatro cosas que hacen auditable un número:

1. **Qué datos** — `sha256` de las barras exactas. Si la serie cambia, la huella
   cambia y el número viejo queda visiblemente atado a datos que ya no existen.
2. **Con qué parámetros** — instrumento, costos, límites de riesgo, capital, y
   `n_pruebas_declaradas`.
3. **Con qué código** — SHA de git **y si el árbol estaba sucio**. Un resultado
   producido con el árbol sucio no es reproducible, y eso se registra en vez de
   ocultarse (`reproducible: false`).
4. **Qué salió** — métricas completas de **cada** participante, incluidos los
   benchmarks y los que perdieron. No solo el ganador.

Se eligió JSONL sobre una base de datos a propósito: es auditable con `grep`,
versionable en git, y no se puede editar una corrida pasada sin que el diff lo
muestre. Verificado que DuckDB lo consulta directo con `read_json_auto`.

**Recalculado desde disco**, no desde la consola:

| Prueba | Sharpe máximo | t máximo | Veredicto |
|---|---|---|---|
| Paseos aleatorios (3 semillas, 9 estrategias) | **0,408** | 1,17 | NINGUNA CALIFICA |
| Momentum AR(1) φ=0,35 (3 semillas, 6 estrategias) | **2,096** | 6,01 | CALIFICAN 2 |

Una línea corrupta en el registro **se denuncia**, no se salta en silencio.
