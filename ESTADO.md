# ESTADO — Laboratorio de trading Exness

**Última actualización: 2026-10-29 (segunda sesión del día).** Todo vive en el VPS, en disco local
(`~/trading-lab`). Nada en el Mac, nada en Google Drive: el montaje es FUSE por
rclone y el I/O del VPS ya tiene 21% de stall medido.

## Lo que está corriendo ahora mismo

| Cada | Qué | Verificado |
|---|---|---|
| **5 min** | operador de papel sobre 40 instrumentos, 24/7 | pasadas automáticas confirmadas en el log |
| 08:20 | centinela: vigila al juez + resumen diario | alarma probada inyectando 2 fallas |

Mira el estado al minuto con:

    ~/bin/lab python ~/trading-lab/scripts/estado_papel.py
    ~/bin/lab python ~/trading-lab/scripts/aprender.py

## Lo medido sobre datos reales (45,9 años, 13 instrumentos)

| | |
|---|---|
| Retorno anual del mejor conjunto clásico | **+0,33%** |
| Ganancia por día con US$2.000 | **US$0,019** |
| Drawdown máximo | 12,7% |
| Aciertos | 36,3% |
| Depósito a plazo chileno, mismo período | 5 veces más |
| S&P 500 comprado y olvidado | 68 veces más |

**Subir el apalancamiento no cambia nada:** de 2x a 100x el resultado es
idéntico porque el sistema nunca usa más de 1,80x. Lo que ata el tamaño es el
0,5% de riesgo por operación.

**Subir el riesgo sí escala**, proporcionalmente: 0,5% → +0,33% anual;
1% → +0,67%. Para el objetivo de US$200/día haría falta ~60 veces más riesgo,
y con 36% de aciertos **8 pérdidas seguidas ocurren el 2,7% de las veces**.

⚠️ **La trampa de la tabla de riesgo:** al subirlo, las primeras operaciones
consumen el cupo de apalancamiento y el resto queda vetado. La fila que se ve
mejor (20% de riesgo, +2,47% anual) tiene **5 operaciones en 46 años**. Es azar.
El script ahora lo marca.

## Dónde quedó

**El laboratorio está operando solo.** Un cron diario a las 08:20 vigila al juez,
espera la credencial de Exness y, cuando aparezca, corre la etapa 1 por su cuenta
y avisa por Telegram.

**No opera, ni en real ni en simulado.** Falta la credencial, y falta que alguna
estrategia sobreviva la validación. Hoy ninguna lo ha hecho sobre datos reales,
porque todavía no ha visto un solo dato real.

## Lo único que bloquea

Tres datos de **Key Management** en el Personal Area de Exness:

1. API key identifier
2. Número de la cuenta de trading
3. Host del "DNS widget" (sin slash final)

Van a `~/.config/exness/env` (hay plantilla en `env.plantilla`). El par de llaves
Ed25519 **ya existe en el VPS**; la pública a registrar sale con:

    cat ~/.config/exness/trader_ed25519.pub.pem

Configuración del formulario: nombre `trading-lab`, producto **Trader API**,
expiración 12 meses, **permisos mínimos de lectura** (si hay opción sin trading,
esa), Allowed IPs **`<IP-DEL-VPS>`**, y la opción *"I'll use my own public key"*.

**La pregunta que más importa:** ¿aparece alguna cuenta **DEMO** en el selector
"Trading account"? El contrato OpenAPI no distingue demo de real (`TradeMode` solo
tiene `enabled`/`trading_disabled`), así que si la demo aparece ahí, se desbloquea
operar en simulado por API.

## Qué funciona, verificado

| Pieza | Estado | Evidencia |
|---|---|---|
| Motor de riesgo | FUNCIONAL | puro, sin red, deniega por defecto, 16 reglas |
| Kill switch | FUNCIONAL | persiste en disco, atómico, fail-safe si está corrupto |
| Backtester | FUNCIONAL | look-ahead inalcanzable por construcción |
| Juez estadístico | FUNCIONAL | 3 barreras: muestra, t-stat Šidák, Sharpe desinflado |
| Torneo | FUNCIONAL | benchmarks obligatorios, "ninguna califica" es resultado válido |
| 6 estrategias clásicas + 2 benchmarks | FUNCIONAL | sin optimizar, de libro |
| Registro de experimentos | FUNCIONAL | JSONL con huella de datos y SHA de código |
| Firma Ed25519 | FUNCIONAL | firma y su pública verifica |
| Cliente de lectura | FUNCIONAL | sin métodos de escritura, IPv4 forzada |
| Centinela diario | FUNCIONAL | alarma verificada inyectando 2 fallas reales |
| **Datos de mercado reales** | **PENDIENTE** | depende de la credencial |
| **Paper trading** | **PENDIENTE** | depende de si la demo sirve por API |
| **Ejecución real** | **NO HABILITADA** | requiere autorización explícita y separada |

**99 pruebas pasando.** Cifras del juez, recalculadas desde disco:

| Prueba | Sharpe positivo máx. | t máx. | Veredicto |
|---|---|---|---|
| Paseos aleatorios (3 semillas) | **0,408** | 1,17 | ninguna califica |
| Momentum AR(1) φ=0,35 (3 semillas) | **2,096** | 6,01 | califican 2 |

## Decisión de alcance vigente

**El juez, no el jugador.** Construir validación estadística, no generación de
estrategias por LLM. Razón: con Sharpe 0,5 hacen falta ~13,2 años de serie limpia
*por estrategia* (reproducido con `anos_minimos(0.5)`), XAUUSD tiene ~23 años, y
los tres instrumentos están correlacionados por el dólar. **El cuello de botella
son los datos, no las ideas.**

## Cómo retomar

    cd ~/trading-lab
    ~/bin/lab python -m pytest tests/ -q          # 99 pruebas
    ~/bin/lab python scripts/prueba_del_juez.py   # no debe certificar nada
    ~/bin/lab python scripts/prueba_de_potencia.py # sí debe detectar momentum
    tail -5 experimentos/audit_centinela.jsonl    # qué vio el centinela

`~/bin/lab` corre dentro del techo de recursos (1,5 GB de RAM, swap 0, 1,5 núcleos)
para no apretar a Hermes.
