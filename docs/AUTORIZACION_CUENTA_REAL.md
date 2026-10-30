# Autorización para la cuenta real — límite vigente

**Instrucción de Fernando, 2026-10-30, textual:**

> Ya está guardada la key REAL de Exness en `~/trading-lab/.env`
> (`EXNESS_API_KEY_REAL`), con su llave privada en
> `~/.config/trading-lab/exness_real_private.pem`. **NO la uses todavía.**
> Todo el trabajo y las pruebas siguen solo contra la DEMO. Para usar la real
> necesito que yo te lo autorice **por escrito en este chat**. Cuando llegue ese
> momento, la primera llamada con la real debe ser **solo lectura** (info de
> cuenta y saldo) y la **reportas antes de cualquier orden**.

Esto está escrito acá y no solo en el chat a propósito: una instrucción que
vive únicamente en una conversación se pierde con la conversación.

## Estado del cerrojo, verificado el 2026-10-30

| Camino | Resultado |
|---|---|
| Entorno por defecto | **DEMO** |
| `cargar("REAL")` sin autorización | **PermissionError** |
| `TRADING_LAB_ENTORNO=REAL` a secas | **PermissionError** |
| Scripts que mencionan las variables | **ninguno** |
| Líneas del crontab que las mencionan | **0** |

Para llegar a REAL hacen falta **las dos a la vez**:

    TRADING_LAB_ENTORNO=REAL   y   TRADING_LAB_AUTORIZO_REAL=si

Ninguna está puesta en el ambiente, en un script ni en un cron.

## Las llaves son distintas, a propósito

| | Pública (prefijo) | Privada |
|---|---|---|
| DEMO | `<LLAVE-PUBLICA-ED25519>…` | `~/.config/exness/trader_ed25519.pem` (600) |
| REAL | `<LLAVE-PUBLICA-ED25519>…` | `~/.config/trading-lab/exness_real_private.pem` (600) |

Así se puede revocar una sin tocar la otra, y una equivocación en demo no
puede alcanzar la cuenta real.

## ⚠️ Falta un dato para cuando se autorice

`.env` tiene `EXNESS_API_KEY_REAL` pero **no** `EXNESS_ACCOUNT_ID_REAL`. Sin
eso, incluso con la autorización puesta, la carga falla. Cuando corresponda
hay que agregar (el número lo dio Fernando: <CUENTA-REAL>):

    EXNESS_ACCOUNT_ID_REAL=<CUENTA-REAL>
    EXNESS_PRIVATE_KEY_REAL_PATH=<HOME>/.config/trading-lab/exness_real_private.pem

No lo agregué yo: es su archivo de credenciales y la instrucción es no tocar
nada de la real hasta que lo autorice.

## La secuencia obligatoria cuando llegue la autorización

1. Autorización **escrita en el chat** por Fernando.
2. Primera llamada: **solo lectura** — info de cuenta y saldo.
3. **Reportar el resultado** antes de cualquier orden.
4. Recién entonces, y con una autorización aparte, considerar una orden.
