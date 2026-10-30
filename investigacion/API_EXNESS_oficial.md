# API de trading de Exness — documentación oficial extraída

**Fecha de extracción:** 2026-10-28
**Método:** descarga directa con `curl` del sitio Docusaurus server-rendered `https://www.exness-api.com/`
y del contrato OpenAPI que ese sitio publica. Nada de este archivo está parafraseado desde memoria:
todo sale de las páginas y del YAML listados abajo.
**Versión del contrato:** `openapi: 3.1.1` · `info.title: Exness Trader API` · `info.version: 1.0.2`

> ⚠️ **Regla aplicada en todo el documento:** donde la documentación no dice algo, está escrito
> **"no documentado"**. No se inventó ningún nombre de campo, ruta ni número.

---

## 1. Fuentes

Todas las páginas respondieron **HTTP 200 con contenido real** (31 páginas; ninguna exigió login,
ninguna devolvió 403, ninguna devolvió la página 404 de ~60.008 bytes).

| Fuente | URL |
|---|---|
| **Contrato OpenAPI completo** (la fuente más precisa) | `https://www.exness-api.com/openapi/trading.public.yaml` — 164.323 bytes, 4.503 líneas. Copia local: `trading.public.yaml`, junto a este archivo |
| API Key & Host Setup | `https://www.exness-api.com/authentication/api-key-and-host-setup` |
| Authentication / Request signing | `https://www.exness-api.com/authentication/request-signing` |
| Send Your First Request | `https://www.exness-api.com/trading/get-started/send-first-request` |
| Place Your First Trade | `https://www.exness-api.com/trading/get-started/place-first-trade` |
| Access Point / Host Discovery | `https://www.exness-api.com/trading/get-started/access-point-host-discovery` |
| Subscribe To WebSocket Events | `https://www.exness-api.com/trading/get-started/subscribe-to-websocket-events` |
| Recommended Integration Flow | `https://www.exness-api.com/trading/get-started/recommended-integration-flow` |
| API Configuration and Limits | `https://www.exness-api.com/trading/guides/api-configuration-and-limits` |
| Formulas & Calculations | `https://www.exness-api.com/trading/guides/formulas-calculations` |
| Runtime Semantics | `https://www.exness-api.com/trading/guides/runtime-semantics` |
| Troubleshooting | `https://www.exness-api.com/trading/guides/troubleshooting` |
| Code Examples | `https://www.exness-api.com/trading/guides/code-examples` |
| Exness Trader API (reference raíz) | `https://www.exness-api.com/reference/trading/exness-trader-api` |
| Get account details | `https://www.exness-api.com/reference/trading/get-account-details` |
| Get available instrument list | `https://www.exness-api.com/reference/trading/get-available-instrument-list` |
| Get instrument condition | `https://www.exness-api.com/reference/trading/get-instrument-condition` |
| Get candle history | `https://www.exness-api.com/reference/trading/get-candle-history` |
| Get limits | `https://www.exness-api.com/reference/trading/get-limits` |
| Get trading state snapshot | `https://www.exness-api.com/reference/trading/get-trading-state-snapshot` |
| Open position | `https://www.exness-api.com/reference/trading/open-position` |
| Place pending order | `https://www.exness-api.com/reference/trading/place-pending-order` |
| Modify order | `https://www.exness-api.com/reference/trading/modify-order` |
| Cancel pending order | `https://www.exness-api.com/reference/trading/cancel-pending-order` |
| Close position | `https://www.exness-api.com/reference/trading/close-position` |
| Get operation status | `https://www.exness-api.com/reference/trading/get-operation-status` |
| Get orders history | `https://www.exness-api.com/reference/trading/get-orders-history` |
| Get deals history | `https://www.exness-api.com/reference/trading/get-deals-history` |
| Get WS ticks | `https://www.exness-api.com/reference/trading/get-ws-ticks` |
| Get WS events | `https://www.exness-api.com/reference/trading/get-ws-events` |
| *(extra, apareció en la navegación)* Overview | `https://www.exness-api.com/trading/get-started` |
| *(extra)* Core Concepts | `https://www.exness-api.com/trading/core-concepts` |

HTML crudos y texto extraído: `/tmp/exndocs/` y `/tmp/exndocs/txt/` (temporales, se borran al reiniciar).

⚠️ **Lo que las páginas `reference/trading/*` NO entregan por HTTP plano:** las tablas de
parámetros y los esquemas de respuesta se renderizan en el navegador (Swagger-like). El texto
server-rendered solo trae la descripción y los códigos de error. **Los nombres literales de campos,
tipos y obligatoriedad de este documento salen del `trading.public.yaml`**, que es el mismo contrato
que esas páginas consumen.

---

## 2. AUTENTICACIÓN

### 2.1 Cómo se obtiene la API key

Textual de *API Key & Host Setup*:

> **Key Management flow**
> 1. Log in to Personal Area or the client portal.
> 2. Open Key Management.
> 3. Create a new API key.
> 4. Select the key type when supported by the product UI.
> 5. Fill in the key name, expiry date, trading account, and allowed IPs if these fields are enabled.
> 6. Store the API key identifier and private signing key securely. Follow the selected key creation flow below.
> 7. Copy the host from the DNS widget. For Trader API, use this Gateway host to resolve the account Access Point before making REST requests or WebSocket connections.

> **Do not create API keys through the Exness API.**
> Use Key Management for API key creation, host visibility, revocation, and rotation.

**Valores a guardar** (los nombres de variable son *ilustrativos*, dice la propia doc):

| Valor | De dónde sale | Uso |
|---|---|---|
| `EXN_API_KEY` | Key Management | Identifica la API key en las solicitudes firmadas |
| `EXN_PRIVATE_KEY` | Clave privada de firma del flujo de creación elegido | Se usa **localmente** para crear las firmas. Los ejemplos pueden usar una ruta a un archivo PEM en vez de un valor en línea |
| `EXN_ACCOUNT_ID` | Cuenta de trading seleccionada | Se usa en los endpoints con alcance de cuenta |
| `EXN_API_BASE_URL` | Host de API específico del producto | Para Trader API, **el Access Point devuelto por discovery** |
| `EXN_DISCOVERY_BASE_URL` | DNS widget en Key Management | URL base del **Gateway** del Trader API, para descubrir el Access Point |

Ejemplo literal de la doc (valores de relleno):

```bash
export EXN_API_KEY="exnsk_your_public_api_key"
export EXN_PRIVATE_KEY="your_private_secret_key"
export EXN_ACCOUNT_ID="123456"
export EXN_DISCOVERY_BASE_URL="https://gateway.example"
export EXN_API_BASE_URL="https://access-point.example"
```

**Dos flujos de creación del par de llaves** (ambos disponibles para todas las API keys,
independiente del producto o los scopes):
- **Exness genera el par:** se sigue el flujo en Key Management y se guarda la clave privada cuando la entrega.
- **Tú generas el par:** generas un par **Ed25519** y registras la clave pública con la opción
  *"I'll use my own public key"*.

**Generar el par propio** (requiere OpenSSL 1.1.1 o superior con soporte Ed25519; en macOS
`/usr/bin/openssl` puede ser LibreSSL y no servir):

```bash
(
  umask 077
  if [ -e private.pem ] || [ -L private.pem ]; then
    printf '%s\n' 'private.pem already exists. Use a new directory.' >&2
    exit 1
  fi
  "$OPENSSL_BIN" genpkey -algorithm ED25519 -out private.pem || exit 1
  chmod 600 private.pem
)
```

`private.pem` queda en **PKCS#8 PEM sin cifrar**. No se sube a Key Management.

**Codificar la clave pública para registrarla:**

```bash
(
  set -o pipefail
  "$OPENSSL_BIN" pkey -in private.pem -pubout -outform DER | "$OPENSSL_BIN" base64 -A
)
```

Reglas literales del formato de registro:
- Se registra la **SubjectPublicKeyInfo (SPKI, también llamada PKIX) DER** completa, codificada como
  **Base64 estándar con padding**, en **una sola línea**, sin espacios ni saltos.
- *"Use the complete DER public key. Do not use `tail -c 32` to extract the raw key bytes: Base64 of
  the raw 32-byte key is not the registration format."*
- No se pega un bloque `BEGIN PUBLIC KEY`.
- ⚠️ Diferencia de codificación que la doc marca explícitamente: *"Request headers `EXN-DATA` and
  `EXN-SIGN` use base64url without padding; the public key registration value uses standard padded
  Base64."*
- *"The API key identifier sent in `EXN-API-KEY` is different from the public key you register."*

**Reglas de seguridad** (textual): guardar la clave secreta de forma segura · no commitearla a Git,
no pegarla en chats, no hardcodearla en producción, no incluirla en capturas · si se pierde, crear una
API key nueva · si se filtra, revocar y crear otra · usar *allowed IPs* cuando la UI lo permita.

### 2.2 Cómo se descubre el host / Access Point

Hay **dos hosts distintos** y la doc insiste en no confundirlos:

| Valor | Uso |
|---|---|
| **Gateway host** del DNS widget | Es a donde se manda la solicitud de **discovery** |
| **`access_point`** devuelto por discovery | Es a donde van **las solicitudes REST con alcance de cuenta y las conexiones WebSocket** |

> *"The DNS widget provides the Gateway host for discovery. It is not the account Access Point."*
> *"Do not copy a hostname from an example or guess the Gateway URL from an account Access Point."*

**Endpoint de discovery (vive en el Gateway, NO está en el OpenAPI):**

```
GET /v1/trading/access-point?account_id=123456
```

- `account_id` es **query parameter obligatorio**: *"a trading account ID represented as an unsigned
  64-bit integer string"*.
- Se firma como `GET`. El `path` dentro de `EXN-DATA` incluye **la ruta completa con el query, exactamente
  como se envía** — `/v1/trading/access-point?account_id=123456`, **no una URL completa**.
- Para GET firmados, `EXN-IDEMPOTENCY-KEY` es **obligatorio y con valor vacío**; el `idempotency_key`
  firmado también va como string vacío.

Respuesta HTTP 200 (ilustrativa; la URL es un placeholder):

```json
{
  "access_point": "https://access-point.example",
  "account_id": "123456"
}
```

> *"`access_point` is a URL. The echoed `account_id` is a string, not a JSON number."*

Si falla el discovery: `400` → revisar el `account_id` y el formato · `401` → API key, cabeceras y
firma · `403` → acceso a la cuenta solicitada · `429` → reintentar tras el tiempo que indique
`Retry-After` o `retry_after` · `500` → leer la `description` de la respuesta · `503` → servicio
temporalmente no disponible, reintentar más tarde.

**Hosts estáticos que aparecen en la doc y que NO son fallback:**

| Host | Estado | Qué dice la doc |
|---|---|---|
| `https://api.exness.com` | Main | *"Review/prototype example only… This static value is not an alternative to discovery."* |
| `https://api.exness-api.com` | Alternative | Idem |

Host de ejemplo que aparece en los curl de la doc: `https://ap-4decef67.exness.com` (ilustrativo).
En el OpenAPI, `servers` es `[{"url": "/"}]` — es decir, **el contrato no trae host; lo pone el discovery**.

### 2.3 Algoritmo EXACTO de firma de solicitudes

Resumen en una línea: **se arma un JSON de 7 campos, se codifica en base64url sin padding → ese string
va en `EXN-DATA`; los bytes del JSON decodificado se firman con Ed25519 y la firma en base64url sin
padding va en `EXN-SIGN`.**

> *"The client signs request metadata with an Ed25519 private key. The server validates the API key,
> timestamp, signed payload fields, path and query, body hash, signature, and access scope."*

#### Cabeceras firmadas (nombres literales)

| Cabecera | ¿Obligatoria? | Propósito (textual) |
|---|---|---|
| `EXN-API-KEY` | Sí | Public API key identifier. Must match `api_key` inside `EXN-DATA`. |
| `EXN-IDEMPOTENCY-KEY` | Sí | Empty for signed GET requests; non-empty for mutating requests. |
| `EXN-TIMESTAMP` | Sí | Unix timestamp in milliseconds. Must match `timestamp` inside `EXN-DATA`. |
| `EXN-SIGN-VERSION` | Sí | Signature protocol version. Current value: `1`. |
| `EXN-DATA` | Sí | Base64url-encoded signed payload without `=` padding. |
| `EXN-SIGN` | Sí | Ed25519 signature of the decoded `EXN-DATA` payload bytes, base64url-encoded without `=` padding. |

En el OpenAPI están modeladas como **security schemes** `apiKey` en header, no como parámetros de
operación: `ExnApiKeyAuth`, `ExnTimestampAuth`, `ExnDataAuth`, `ExnSignatureAuth`,
`ExnSignVersionAuth`, `ExnIdempotencyKeyAuth`. Las seis van juntas en un solo requisito de seguridad
(todas requeridas a la vez).

#### Payload decodificado de `EXN-DATA` (nombres literales de campo)

| Campo | Descripción (textual) |
|---|---|
| `api_key` | Same value as `EXN-API-KEY`. |
| `idempotency_key` | Same value as `EXN-IDEMPOTENCY-KEY`; empty string for signed GET requests. |
| `timestamp` | Same value as `EXN-TIMESTAMP`, in Unix milliseconds. |
| `sign_version` | Same value as `EXN-SIGN-VERSION`. |
| `method` | Uppercase HTTP method, for example `GET` or `POST`. |
| `path` | Request path with query string exactly as sent by the client. |
| `body_hash` | SHA-256 hash of the exact request body, base64url-encoded without padding. |

#### Reglas de firma (textual, lista completa)

- `EXN-SIGN` signs the **decoded `EXN-DATA` payload bytes**, not the base64url string.
- `EXN-DATA` and `EXN-SIGN` must use **base64url without `=` padding**.
- For requests without a body, `body_hash` is the SHA-256 hash of the empty byte sequence:
  **`47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU`**
- Query strings must be signed **exactly as transmitted**. Do not reorder, normalize, or re-encode
  query parameters after signing.
- **Duplicate query parameters are rejected.**
- For signed GET requests, `EXN-IDEMPOTENCY-KEY` must be present with an **empty value**.
- For mutating requests, `EXN-IDEMPOTENCY-KEY` must be **non-empty**.
- **Generate a fresh timestamp and signature for every request.**
- `EXN-SIGN-VERSION` must be `1`; *"The only supported value is `1`."*
- *"The timestamp must be close to the server time."* · *"Requests outside the accepted server time
  window are rejected."* — **el tamaño de esa ventana no está documentado**.

#### Ejemplo literal GET (de *Authentication*)

```bash
curl -X GET "https://ap-4decef67.exness.com/v1/configuration/accounts/123456/account" \
  -H "EXN-API-KEY: exnsk_your_public_api_key" \
  -H "EXN-IDEMPOTENCY-KEY:" \
  -H "EXN-TIMESTAMP: 1773656070123" \
  -H "EXN-SIGN-VERSION: 1" \
  -H "EXN-DATA: <base64url_encoded_payload>" \
  -H "EXN-SIGN: <base64url_encoded_signature>"
```

```json
{
  "api_key": "exnsk_your_public_api_key",
  "idempotency_key": "",
  "timestamp": 1773656070123,
  "sign_version": 1,
  "method": "GET",
  "path": "/v1/configuration/accounts/123456/account",
  "body_hash": "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"
}
```

⚠️ En *Access Point / Host Discovery* y en *Send Your First Request* la cabecera vacía se escribe con
**punto y coma**: `-H "EXN-IDEMPOTENCY-KEY;"`. La doc lo explica: *"The semicolon in curl's
`EXN-IDEMPOTENCY-KEY;` option sends the required header with an empty value."* En la página
*Authentication* aparece como `-H "EXN-IDEMPOTENCY-KEY:"` — **las dos formas aparecen en la doc
oficial y no aclara cuál es la correcta** (ver LAGUNAS).

#### Ejemplo literal POST (del reference raíz / OpenAPI)

```http
POST /v1/trading/accounts/123456789/orders HTTP/1.1
EXN-API-KEY: exnsk-live-example
EXN-IDEMPOTENCY-KEY: order-20260316-0001
EXN-TIMESTAMP: 1773656070123
EXN-SIGN-VERSION: 1
EXN-DATA: <base64url_encoded_payload>
EXN-SIGN: <base64url_encoded_signature>
Content-Type: application/json
```

```json
{
  "api_key": "exnsk-live-example",
  "idempotency_key": "order-20260316-0001",
  "timestamp": 1773656070123,
  "sign_version": 1,
  "method": "POST",
  "path": "/v1/trading/accounts/123456789/orders",
  "body_hash": "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"
}
```

⚠️ Ese ejemplo POST del OpenAPI muestra el `body_hash` del cuerpo **vacío** aunque el método lleva
cuerpo JSON obligatorio. Es una inconsistencia del ejemplo, no una regla.

#### Idempotencia (`EXN-IDEMPOTENCY-KEY`) — reglas literales

- Largo: **5 a 128 caracteres**. Caracteres permitidos: `A-Z`, `a-z`, `0-9`, `.`, `_`, `-`, `~`.
  Patrón del OpenAPI: `^[A-Za-z0-9._~-]{5,128}$`.
- Para GET firmados el valor debe ser **exactamente** `""` (en el schema: `{"type":"string","const":""}`).
- Si se reusa la misma key para **la misma cuenta, el mismo tipo de operación y el mismo payload**,
  la solicitud duplicada **se acepta con el `operation_id` original y no se ejecuta de nuevo**.
- Si se reusa para la misma cuenta y tipo de operación con **payload distinto**, se rechaza como
  conflicto de key duplicada.
- Los registros de idempotencia *"are retained for a limited time"* — **cuánto, no documentado**.
- La key se devuelve como `client_request_id` en el ACK, en el `transaction_event` correspondiente y
  en la respuesta de estado de operación.

#### Errores de autenticación

| Code | `error_message` | Acción del cliente |
|---|---|---|
| `1000` | `AUTH_INVALID_API_KEY` | Revisar `EXN-API-KEY`, expiración de la key y `api_key` dentro de `EXN-DATA`. |
| `1001` | `AUTH_INVALID_SIGNATURE` | Revisar `EXN-DATA`, `EXN-SIGN`, la clave privada, la serialización del payload, el body hash, el timestamp y la codificación base64url. |
| `1002` | `AUTH_PERMISSION_DENIED` | Revisar acceso a la cuenta, restricciones de IP de origen y permisos de la API key. |
| `1003` | `AUTH_RATE_LIMIT` | *(solo en Troubleshooting)* HTTP 429, demasiadas solicitudes de autenticación. Esperar `retry_after` cuando venga; si no, backoff. |

⚠️ `1003 AUTH_RATE_LIMIT` aparece en la tabla de Troubleshooting pero **no está en el enum
`PublicApiErrorCode` del OpenAPI**. Contradicción de la propia doc.

Errores comunes de firma que la doc lista: *"Your API keys or timestamps do not match your data"* ·
*"You changed the request path or query details after you already signed it"* · *"Your data encoding
includes unnecessary padding"*.

---

## 3. LÍMITES

### 3.1 Los números exactos NO están publicados

Esto es el hallazgo central de esta sección y hay que decirlo sin adornos:

> *"Do not hardcode limits. API conditions may vary by account, API key, endpoint group, and current
> API configuration. **Always use the values returned by this endpoint.**"*

El contrato OpenAPI define la **forma** de los límites pero **no trae ni un valor numérico de ejemplo**
(verificado por grep: ningún `example` en `GlobalRestRateLimit`, `ApiRateLimit`,
`OperationRequestLimits`, `WebSocketGlobalAccountLimits` ni `WebSocketTokenBucketLimit`).
**Los rate limits reales solo se conocen llamando al endpoint con una credencial válida.**

```
GET /v1/configuration/accounts/{account_id}/limits
```

- *"REST limits apply to the complete AP cluster. WebSocket limits are enforced **per server node**."*
- *"The endpoint returns configured limits. It does not return the client's current remaining quota.
  The client must calculate available request capacity locally."*
- Se pide **al arrancar la aplicación**, después de resolver el Access Point, y se refresca
  periódicamente o tras errores de rate limit.

### 3.2 Estructura de la respuesta de límites (nombres literales)

```
LimitsResponse
└── limits (obligatorio) : ApiLimits
    ├── rest (obligatorio) : RestLimits
    │   ├── global_account_rate (obligatorio) : GlobalRestRateLimit
    │   │   ├── limit          : integer, minimum 1   (obligatorio)
    │   │   └── window_seconds : integer, minimum 1   (obligatorio)
    │   └── methods[] (obligatorio) : RestMethodLimits
    │       ├── api_operation_id (obligatorio) : string
    │       ├── http_method      (obligatorio) : enum GET|POST|PUT|PATCH|DELETE
    │       ├── path            (obligatorio) : string
    │       ├── rate_limit      (obligatorio) : { limit:int≥1, window_seconds:int≥1 }
    │       └── limits (opcional) : OperationRequestLimits
    │           ├── max_candles_per_request             : integer ≥ 1
    │           ├── max_candles_per_request_description : string
    │           ├── history_range_days                  : integer ≥ 1
    │           └── history_age_days                    : integer ≥ 1
    └── websocket (obligatorio) : WebSocketLimits
        ├── global_account_limits (obligatorio) : WebSocketGlobalAccountLimits
        │   ├── max_active_connections     : integer ≥ 1   (obligatorio)
        │   ├── max_inbound_message_bytes  : integer ≥ 1   (obligatorio)
        │   ├── connection_rate            : WebSocketTokenBucketLimit (obligatorio)
        │   ├── inbound_message_rate       : WebSocketTokenBucketLimit (obligatorio)
        │   └── strikes                    : WebSocketStrikeLimits     (obligatorio)
        │       ├── refill_amount : integer ≥ 1
        │       ├── threshold     : integer ≥ 1
        │       └── period_ms     : integer ≥ 1
        └── endpoints[] (obligatorio) : WebSocketEndpointLimits
            ├── api_operation_id, http_method, path            (obligatorios)
            ├── connection_rate, inbound_message_rate          (obligatorios)
            └── subscription_operation_rate (obligatorio) : objeto cuyas claves son el tipo de
                suscripción y cuyos valores son WebSocketTokenBucketLimit

WebSocketTokenBucketLimit = { limit: int≥1, window_seconds: number(double), burst: int≥1 }
```

Cálculo de capacidad REST, textual: buscar el método en `limits.rest.methods[]` (match por
`api_operation_id`, `http_method` o `path`) → leer `rate_limit.limit` y `rate_limit.window_seconds` →
contar localmente las solicitudes ya enviadas en la ventana actual → enviar solo si el uso local está
bajo el límite.

### 3.3 Protección de WebSocket (textual del OpenAPI, tag *Server Events*)

- **Active connections:** como máximo `max_active_connections` conexiones WebSocket concurrentes por
  cuenta. Las que exceden se **rechazan en el handshake con HTTP 429**.
- **Connection rate:** las conexiones nuevas deben pasar **los dos** buckets `connection_rate` (el
  global y el del endpoint); si exceden cualquiera, rechazo en el handshake con HTTP 429.
- **Inbound messages:** cada mensaje del cliente (subscribe, unsubscribe, ping, custom) se valida, no
  puede exceder `max_inbound_message_bytes` y está sujeto a `inbound_message_rate` global y por
  endpoint. Los frames sobredimensionados se rechazan **y cuentan como strikes**; los mensajes
  throttleados **se descartan**.
- **Subscription operations:** los subscribe están limitados por endpoint con
  `subscription_operation_rate`; **una solicitud sobre N instrumentos cuenta como N operaciones de
  suscripción**. Los unsubscribe no están sujetos a `subscription_operation_rate` pero sí a
  `inbound_message_rate`. **"The total number of subscriptions is not limited."**
- **Strikes:** se registra un strike cuando el cliente se suscribe a un instrumento inexistente o se
  desuscribe de uno al que no estaba suscrito. Al exceder `strikes.threshold` dentro de la ventana de
  decaimiento, la conexión se cierra con **policy-violation (RFC 6455 código 1008)**.
- **Slow consumers:** cada conexión tiene una cola de salida acotada; si el cliente no alcanza y la
  cola se desborda, **se termina la conexión** en vez de bufferear indefinidamente.

### 3.4 Throttling de ticks

> *"In order to ensure system stability and performance, tick updates may be throttled. The delivery
> frequency may be reduced up to **one update per 500ms**."* (reference *Get WS ticks*)

### 3.5 Intervalo de `account_state`

- *"Updates are sent every **2 seconds**."*
- *"The interval is **shared globally** for all subscribers."*
- *"The timing window does not depend on subscription start time."*
- *"Floating account state updates are **not** delivered on every market tick."*

### 3.6 Timeouts

**No documentado** ningún timeout del servidor (ni HTTP ni WebSocket idle). Lo único que aparece son
timeouts **del cliente en los ejemplos**, que no son contrato:
`handshakeTimeout: 10000` (ms) al abrir el WebSocket, `timeoutMs = 30000` por defecto en el helper
`waitForJsonMessage`, y `sleep(1000)` entre polls de estado de operación. La ventana de tolerancia del
`EXN-TIMESTAMP` tampoco está documentada.

### 3.7 Paginación

- Los endpoints históricos usan **paginación por cursor**.
- `cursor` es un **token de continuación opaco**; *"Clients must not parse or modify `cursor`."*
- *"When `cursor` is used, it cannot be combined with filters except `limit`, unless explicitly stated
  otherwise."*
- Las colecciones históricas vienen en **orden cronológico ascendente**, de más viejo a más nuevo.
- `limit`: entero, **mínimo 1, máximo 200, default 100**.
- Campos de respuesta de paginación: `next_cursor` (string), `has_more` (boolean), `range` (objeto con
  `from` y `to`, ambos `date-time`).
- Ventanas de historia: `from` es obligatorio cuando no se entrega `cursor`; `from` debe ser anterior
  a la hora actual del servidor; la ventana pedida debe caber dentro de `history_age_days` y su largo
  no puede exceder `history_range_days`, **valores que se obtienen del endpoint de límites** (no están
  publicados).

### 3.8 Retención de datos

| Qué | Cuánto | Fuente |
|---|---|---|
| Operaciones (`operation_id`) | **24 horas** | Runtime Semantics y reference *Get operation status* |
| Posiciones cerradas y órdenes en estado final | **1 mes** — *"(subject to clarification)"* | reference de los métodos de trading |
| Registros de idempotencia | *"a limited time"* — **no documentado** | OpenAPI |

### 3.9 Historia de velas disponible por timeframe

| Timeframe | Historia disponible |
|---|---|
| `S1` | 1 día |
| `S5` | 5 días |
| `S15` | 15 días |
| `M1`, `M3` | 1 año |
| `M5`, `M10` | 2 años |
| `M15`, `M30` | 3 años |
| `H1`+ | historia completa disponible |

⚠️ Discrepancia entre páginas sobre el tope de velas por solicitud: *Runtime Semantics* dice
*"`count` is bidirectional and must be from **-1000 to 1000, excluding 0**"* y *"If `to` is used, the
requested range must not exceed **from + 1000 candles**"*. El reference de *Get candle history* y el
OpenAPI dicen *"its absolute value must not exceed the **configured** candle limit… retrieve the
current limit from `GET /v1/configuration/accounts/{account_id}/limits`"* (`max_candles_per_request`),
sin número. El schema de `count` solo exige `≠ 0` (`oneOf` de `integer maximum:-1` o `integer minimum:1`).

### 3.10 Reglas de reintento ante rate limit

> Cuando la API devuelve HTTP 429 o `REQUEST_RATE_LIMIT`: no reintentar inmediatamente en bucle ·
> refrescar límites si la configuración local puede estar vencida · recalcular capacidad local ·
> esperar a que haya capacidad · reintentar solo si la operación sigue siendo necesaria y es seguro
> hacerlo. *"`REQUEST_RATE_LIMIT` is non-retryable automatically."*
> *"Do not assume that another account, API key, endpoint, or endpoint group has the same limits."*

---

## 4. TABLA DE ENDPOINTS

**Host base:** el `access_point` devuelto por el discovery. El OpenAPI declara `servers: [{url: "/"}]`,
es decir **no fija host**.
**Parámetro de ruta común a todos:** `account_id` — *"Trading account number (associated with API key)"*,
tipo `UInt64String` = string con patrón `^[0-9]{1,20}$`, largo 1 a 20, sin signo ni separadores.
**Todos** requieren las 6 cabeceras `EXN-*` de la sección 2.3.

### 4.1 Discovery (Gateway, fuera del OpenAPI)

| Método | Ruta literal | Parámetros obligatorios | Campos de respuesta |
|---|---|---|---|
| `GET` | `/v1/trading/access-point` | `account_id` (query, string de entero sin signo de 64 bits) | `access_point` (URL, string), `account_id` (string) |

### 4.2 Configuration

| Método | Ruta literal | `operationId` | Parámetros obligatorios | Respuesta |
|---|---|---|---|---|
| `GET` | `/v1/configuration/accounts/{account_id}/account` | `getAccountDetails` | `account_id` (path) | `200` → `AccountDetailsResponse` |
| `GET` | `/v1/configuration/accounts/{account_id}/instruments` | `getAvailableInstrumentList` | `account_id` (path) | `200` → `InstrumentNameListResponse` |
| `GET` | `/v1/configuration/accounts/{account_id}/instruments/{instrument}/conditions` | `getInstrumentCondition` | `account_id` (path), `instrument` (path, `InstrumentName`) | `200` → `InstrumentConditionResponse` |
| `GET` | `/v1/configuration/accounts/{account_id}/limits` | `getLimits` | `account_id` (path) | `200` → `LimitsResponse` (ver 3.2) |

**`AccountDetailsResponse`** — obligatorios `account_id`, `create_date`:
`account_id` (`UInt64String`) · `account_name` (string, ej. `Standard`) · `create_date` (date-time, ej.
`2024-03-14T11:46:30+00:00`) · `settings` (`AccountSettings`).

**`AccountSettings`** — obligatorios `currency`, `leverage`, `trade_mode`, `account_status`,
`execution_mode`: `currency` (string) · `leverage` (string) · `margin_call_level` (`DecimalString`) ·
`stopout_level` (`DecimalString`) · `trade_mode` (`enabled` | `trading_disabled`) · `account_status`
(`active` | `close_only`) · `execution_mode` (`undefined` | `instant` | `market`).

⚠️ En *Send Your First Request* el ejemplo de respuesta es **plano y con otros nombres**:
`{"account_id": 123456, "currency": "USD", "leverage": "1:2000", "margin_call_level": "60",
"stop_out_level": "0"}` — `account_id` como número, sin el envoltorio `settings`, y
`stop_out_level` en vez de `stopout_level`. El OpenAPI dice `settings.stopout_level` y
`account_id` como string. **Contradicción entre la guía y el contrato**; la propia página advierte
*"Always use the generated API Reference documentation as your final guide for the exact response fields."*

**`InstrumentNameListResponse`**: `instruments` (array de `InstrumentName`). `InstrumentName` =
string, patrón `^[A-Za-z0-9._-]+$`, largo **1 a 11**, ej. `EURUSD`.

**`InstrumentConditionResponse`** — obligatorio `instrument`. Campos: `instrument` · `description`
(ej. `Euro vs US Dollar`) · `international_name` (`EUR/USD`) · `category` (`Forex`) · `base_currency` ·
`quote_currency` · `margin_currency` · `point_digits` (integer int32, ej. `5`) · `calc_mode`
(`undefined`|`forex`|`forex_no_leverage`|`cfd`|`cfd_leverage`) · `exec_mode`
(`undefined`|`instant`|`market`) · `margin_percent` · `contract_size` · `volume_min` · `volume_max` ·
`volume_step` · `swap_long` · `swap_short` (todos `DecimalString`) · `swap_multipliers[]`
(`{day: string ej. "WED", multiplier: int32 ej. 3}`) · `trade_mode` · `order_types[]`
(`stop`|`limit`|`stoplimit`|`market`) · `filling_modes[]` (`fok`|`ioc`|`boc`) · `trade_sessions[]`
(`{trade_mode, week_start_time: ej. "Mon, 10:00:00", week_end_time: ej. "Mon, 11:59:59"}`) ·
`commission_settings` (`{commission_type: undefined|per_lot_per_side|per_lot_per_trade|per_million_usd,
commission_value: {amount: DecimalString, currency: string}}`).

> Es la fuente de las validaciones por instrumento: `volume_min`, `volume_max`, `volume_step` para el
> volumen; `point_digits` para la precisión de precio y el incremento mínimo implícito `10^-point_digits`.

### 4.3 Historical Market Data

| Método | Ruta literal | `operationId` | Respuesta |
|---|---|---|---|
| `GET` | `/v1/market-data/accounts/{account_id}/candles` | `getCandleHistory` | `200` → `CandleHistoryResponse` |

| Parámetro | In | Obligatorio | Tipo / valores |
|---|---|---|---|
| `account_id` | path | **sí** | `UInt64String` |
| `instrument` | query | **sí** | `InstrumentName` |
| `timeframe` | query | **sí** | string enum: `S1`, `S5`, `S15`, `M1`, `M3`, `M5`, `M10`, `M15`, `M30`, `H1`, `H2`, `H4`, `D1`, `W1`, `MN` |
| `from` | query | **sí** | string `date-time` — inclusivo |
| `to` | query | no | string `date-time` — **exclusivo**; no combinable con `count` |
| `count` | query | no | integer `≠ 0` (bidireccional); no combinable con `to` |
| `price_type` | query | no | string enum `bid` \| `ask` \| `both`, **default `bid`** |

`CandleHistoryResponse`: `candles[]`, donde cada elemento es `Candle` **o** `CandleBidAsk`:
- `Candle` (un solo lado): `time` (date-time), `open`, `high`, `low`, `close`, `volume` — todos
  `number`/`double`.
- `CandleBidAsk` (cuando `price_type=both`): `time`, `bid` (`CandleSide`), `ask` (`CandleSide`),
  `volume`. `CandleSide` = `{open, high, low, close}` como `number`/`double`.

> Los precios de market data (tick bid/ask y OHLC de velas) son **JSON numbers** (`type: number,
> format: double`), **no** strings decimales — a diferencia de los valores monetarios y de trading.

### 4.4 Trading (los mutantes devuelven `202` + ACK, no el resultado final)

| Método | Ruta literal | `operationId` | Cuerpo / parámetros | Respuesta |
|---|---|---|---|---|
| `POST` | `/v1/trading/accounts/{account_id}/positions` | `openPosition` | body JSON **obligatorio** `OpenPositionRequest` | `202` → `AckResponse` |
| `POST` | `/v1/trading/accounts/{account_id}/orders` | `placePendingOrder` | body JSON **obligatorio** `NewPendingOrderRequest` | `202` → `AckResponse` |
| `PATCH` | `/v1/trading/accounts/{account_id}/orders/{order_id}` | `modifyOrder` | `order_id` (path, `UInt64String`) + body `ModifyOrderRequest` | `202` → `AckResponse` |
| `DELETE` | `/v1/trading/accounts/{account_id}/orders/{order_id}` | `cancelPendingOrder` | `order_id` (path, `UInt64String`) | `202` → `AckResponse` |
| `DELETE` | `/v1/trading/accounts/{account_id}/positions/{position_id}` | `closePosition` | `position_id` (path, `UInt64String`) + queries opcionales | `202` → `AckResponse` |
| `GET` | `/v1/trading/accounts/{account_id}/snapshot` | `getTradingStateSnapshot` | `account_id` | `200` → `TradingStateSnapshot` |
| `GET` | `/v1/trading/accounts/{account_id}/operations/{operation_id}` | `getOperationStatus` | `operation_id` (path, `UInt64String`) | `200` → `OperationStatusResponse`; `404` → `ErrorResponse` |
| `GET` | `/v1/history/accounts/{account_id}/orders` | `getOrdersHistory` | ver abajo | `200` → `OrdersHistoryResponse` |
| `GET` | `/v1/history/accounts/{account_id}/deals` | `getDealsHistory` | ver abajo | `200` → `DealsHistoryResponse` |

**`OpenPositionRequest`** — obligatorios **`instrument`, `side`, `volume`**:

| Campo | Tipo | Obligatorio | Notas literales |
|---|---|---|---|
| `instrument` | `InstrumentName` | **sí** | |
| `side` | string enum `buy` \| `sell` | **sí** | |
| `volume` | `InstrumentVolumeString` (decimal en string, positivo) | **sí** | debe cumplir `volume_min`, `volume_max`, `volume_step` |
| `price` | `InstrumentPriceString` | no | *"Required when instrument `exec_mode` is `instant`. Not applicable for `market` execution and will be ignored."* |
| `deviation` | `DecimalString` | no | desviación máxima de precio **expresada en points**; solo aplica con `exec_mode = instant` y `price` entregado |
| `stop_loss_price` | `InstrumentPriceString` | no | |
| `take_profit_price` | `InstrumentPriceString` | no | |
| `comment` | string | no | |

**`NewPendingOrderRequest`** = `oneOf` de tres formas. *"Market orders are not accepted by this method."*

- **`NewLimitOrderRequest`** — obligatorios `instrument`, `side`, `type`, `volume`, `price`:
  `type` = `"limit"` · más `stop_loss_price`, `take_profit_price`, `comment` opcionales.
- **`NewStopOrderRequest`** — obligatorios `instrument`, `side`, `type`, `volume`, `price`:
  `type` = `"stop"` · mismos opcionales.
- **`NewSltpOrderRequest`** — obligatorios `position_id` (`UInt64String`) y `type` = `"sltp"`, **más
  al menos uno** de `stop_loss_price` / `take_profit_price` (`anyOf`). Opcional `comment`.

**`ModifyOrderRequest`** — *"At least one of the following fields must be provided: `price`,
`stop_loss_price`, `take_profit_price`."* Campos omitidos no se cambian. **`null` en
`stop_loss_price` o `take_profit_price` elimina el SL/TP.** Opcional `comment`.

**`closePosition`** — queries opcionales:
`volume` (`ClosePositionVolumeString`, patrón `^[+]?[0-9]+(?:\.[0-9]+)?$`; si se omite se cierra todo
el volumen remanente; `0`/`0.0`/`0.00` solo se aceptan si va `close_by_position_id`) ·
`price` (`InstrumentPriceString`) · `deviation` (`DecimalString`, en points, ej. `2.5`; **ignorado en
ejecución `market`**) · `close_by_position_id` (`UInt64String`, solo donde close-by está soportado).

**`AckResponse`** — obligatorio `status`:
`operation_id` (`UInt64String`, opcional) · `client_request_id` (string, opcional) ·
`status` (string enum, **único valor** `accepted`).

**`OperationStatusResponse`** — obligatorios `operation_id`, `status`, `created_at`, `updated_at`:
`operation_id` (`UInt64String`) · `status` (`pending` | `confirmed` | `rejected` | `failed`) ·
`client_request_id` (string) · `error_code` (`PublicApiErrorCode`, integer) · `error_message` (string,
ej. `TRADING_RULE_INVALID_PRICE_LEVELS`) · `created_at` (date-time) · `updated_at` (date-time).

**`TradingStateSnapshot`** — obligatorio `account_state`:
`orders[]` (`Order`) · `positions[]` (`Position`) · `account_state` (`AccountState`).

**`Order`** — obligatorios `order_id`, `order_type`, `state`, `create_time`:
`order_id` (`UInt64String`) · `position_id` (`UInt64String`) · `order_type` (`market`|`stop`|`limit`|`sltp`) ·
`state` (`pending_new`|`placed`|`filled`|`cancelled`|`rejected`) · `direction` (`buy`|`sell`) ·
`instrument` · `price` · `stop_loss_price` · `take_profit_price` (`DecimalString`) · `create_time` ·
`update_time` (date-time) · `volume` (`DecimalString`) · `reason` (`OrderReason`: `undefined`|`sl`|`tp`|
`so`|`margin_check_failed`|`dealer`|`close_by`|`stock_split`|`trading_server`).
*"For `order_type=sltp`, some trading fields such as `direction`, `instrument`, `price`, and `volume`
may be omitted if they are inherited from the related position."*

**`Position`** — obligatorios `position_id`, `direction`, `instrument`, `volume`, `state`, `create_time`:
`position_id` · `direction` (`buy`|`sell`) · `instrument` · `initial_volume` · `volume` ·
`open_price` · `state` (`open`|`closed`) · `margin_rate` · `create_time` · `commission` · `swap` ·
`rollover_time` (date-time).

**`AccountState`** — **los tres obligatorios**: `balance`, `equity`, `used_margin` (`DecimalString`, en
moneda de la cuenta). En los `transaction_event` el tipo es `TransactionAccountState` = `AccountState`
**más `leverage` (string) obligatorio**.

**`Deal`** — obligatorios `deal_id`, `type`, `create_time`:
`deal_id` · `order_id` · `position_id` (`UInt64String`) · `type` (`open`|`close`|`balance`|
`null_compensation`|`swap_fee`|`admin_fee`|`dividend`|`exness_dollar`) · `direction` (`buy`|`sell`) ·
`instrument` · `volume` · `price` (`DecimalString`) · `profit` (`ProfitAmount` = `{amount:
DecimalString, currency: string}`) · `create_time` · `commission` (`DecimalString`).

**Historias** — `OrdersHistoryResponse` / `DealsHistoryResponse`, obligatorio `items`:
`items[]` (`OrderHistoryItem` = `{event_time, order}` / `DealHistoryItem` = `{event_time, deal}`,
ambos campos obligatorios) · `next_cursor` (string) · `has_more` (boolean) · `range` (`{from, to}`).

Parámetros de las historias:

| Parámetro | In | Obligatorio | Tipo / valores |
|---|---|---|---|
| `account_id` | path | **sí** | `UInt64String` |
| `from` | query | condicional — *"required when `cursor` is not provided"* | string `date-time` |
| `to` | query | no | string `date-time`; debe ser posterior a `from` |
| `cursor` | query | no | string opaco; no combinable con filtros salvo `limit` |
| `limit` | query | no | integer, **1 a 200, default 100** |
| `instrument` | query | no | `InstrumentName` (filtro) |
| `order_state` | query | no | *(solo orders)* enum `filled` \| `cancelled` \| `rejected` |
| `deal_type` | query | no | *(solo deals)* enum `open` \| `close` \| `balance` \| `null_compensation` \| `admin_fee` \| `swap_fee` \| `dividend` \| `exness_dollar` |

> *"Open orders and open positions are not returned by history endpoints. Read them from snapshot or
> Server Events."* Las posiciones de las órdenes `filled` **no** las devuelve este método y *"can be
> calculated based on deals with `type = 'open', 'close'"*.

### 4.5 Códigos de error públicos (`PublicApiErrorCode`, enum completo del OpenAPI)

`code` es **integer int32**. `error_message` es el nombre literal.

| Código | Nombre | HTTP (según Troubleshooting) |
|---|---|---|
| `1` | `SYSTEM_RATE_LIMIT` | 429 |
| `2` | `SYSTEM_TEMPORARY_UNAVAILABLE` | 503 |
| `3` | `SYSTEM_INTERNAL_ERROR` | 500 |
| `1000` | `AUTH_INVALID_API_KEY` | 401 |
| `1001` | `AUTH_INVALID_SIGNATURE` | 401 |
| `1002` | `AUTH_PERMISSION_DENIED` | 403 |
| `2000` | `ACCOUNT_NOT_FOUND` | 404 |
| `2001` | `ACCOUNT_DISABLED` | 403 |
| `2002` | `ACCOUNT_CLOSE_ONLY` | 403 |
| `3000` | `REQUEST_INVALID` | 400 |
| `3001` | `REQUEST_INVALID_PARAMETERS` | 400 |
| `3002` | `REQUEST_INVALID_PRICE` | 400 |
| `3003` | `REQUEST_INVALID_TIMEFRAME` | 400 |
| `3004` | `REQUEST_INVALID_TIME_RANGE` | 400 |
| `3005` | `REQUEST_INVALID_COUNT` | 400 |
| `3006` | `REQUEST_INVALID_LIMIT` | 400 |
| `3007` | `REQUEST_INVALID_CURSOR` | 400 |
| `3008` | `REQUEST_INVALID_PRICE_TYPE` | 400 |
| `3009` | `REQUEST_INVALID_FILTER_COMBINATION` | 400 |
| `3010` | `REQUEST_UNSUPPORTED_MEDIA_TYPE` | 400 |
| `3011` | `REQUEST_METHOD_NOT_ALLOWED` | 405 |
| `3012` | `REQUEST_ORDER_NOT_FOUND` | 404 |
| `3013` | `REQUEST_POSITION_NOT_FOUND` | 404 |
| `3014` | `REQUEST_OPERATION_NOT_FOUND` | 404 |
| `3015` | `REQUEST_RATE_LIMIT` | 429 |
| `4000` | `MARKET_INSTRUMENT_NOT_FOUND` | 404 |
| `4001` | `MARKET_TRADE_DISABLED` | 403 |
| `4002` | `MARKET_CLOSE_ONLY` | 403 |
| `4003` | `MARKET_SESSION_CLOSED` | 409 |
| `4004` | `MARKET_NO_QUOTES` | 503 |
| `5000` | `TRADING_RULE_INVALID_VOLUME` | 422 |
| `5001` | `TRADING_RULE_VOLUME_TOO_SMALL` | 422 |
| `5002` | `TRADING_RULE_VOLUME_TOO_LARGE` | 422 |
| `5003` | `TRADING_RULE_INVALID_VOLUME_STEP` | 422 |
| `5004` | `TRADING_RULE_INVALID_REMAINING_VOLUME` | 422 |
| `5005` | `TRADING_RULE_INVALID_PRICE_LEVELS` | 422 |
| `5006` | `TRADING_RULE_INSUFFICIENT_MARGIN` | 422 |
| `5007` | `TRADING_RULE_MARGIN_LEVEL_TOO_LOW` | 422 |
| `5008` | `TRADING_RULE_OPERATION_RESTRICTED` | 422 |
| `5009` | `TRADING_RULE_TOO_MANY_PENDING_ORDERS` | 422 |
| `5010` | `TRADING_RULE_TOO_MANY_OPEN_POSITIONS` | 422 |
| `6000` | `EXECUTION_REQUOTE` | 409 |
| `6001` | `EXECUTION_REJECTED` | 409 |

*(más `1003 AUTH_RATE_LIMIT` / 429, que sale solo en Troubleshooting y no en el enum — ver §2.3)*

Formas de la respuesta de error:
`ErrorResponse` = `{code: integer, error_message: string}` (ambos obligatorios) ·
`WsErrorResponse` = `{id: string, code: integer, error_message: string}` (los tres obligatorios).

Ejemplos literales:
```json
{ "code": 3001, "error_message": "REQUEST_INVALID_PARAMETERS" }
```
```json
{ "id": "request-1", "code": 3000, "error_message": "REQUEST_INVALID" }
```

> *"Public errors are non-retryable by default."* · *"`code` is the primary signal for client
> automation."* · *"clients… must not rely on internal diagnostic text."*

### 4.6 Semántica asíncrona (necesaria para usar los endpoints de trading)

- Los métodos mutantes devuelven **`202` con un ACK**. *"ACK means the request was accepted for
  processing"*, no que el resultado final exista.
- El resultado final llega por **`transaction_event`** en Server Events, y se puede leer de
  `GET /v1/trading/accounts/{account_id}/operations/{operation_id}`.
- Correlación: por `operation_id` o por `client_request_id` (el eco de la idempotency key).
- Estados de operación: `pending` (seguir esperando o poll con backoff) · `confirmed` (finalizada) ·
  `rejected` (revisar el error y cambiar la solicitud) · `failed` (revisar y reintentar solo si es seguro).
- Estados de `transaction_event`: `success` · `rejected` · `failed`. En `rejected`/`failed` *"the
  payload may be empty and `error_code` may be provided"*.
- Restricciones de runtime: con `trade_mode = trading_disabled` algunos métodos y streams no están
  disponibles (incluidos `/snapshot`, las historias y **los dos streams WebSocket**); con
  `account_status = close_only` no se permite abrir posiciones ni colocar órdenes pendientes —
  cerrar y cancelar sí (y *place pending order* se permite **solo para órdenes SLTP**).
- Fechas: todas en **UTC**, ISO 8601 con offset explícito, ej. `2026-03-16T12:54:30+00:00`.
- Decimales: valores monetarios, de precio, de margen y de volumen van como **strings decimales** con
  patrón `^[+-]?[0-9]+(?:\.[0-9]+)?$`. *"Use decimal-safe arithmetic… Do not rely on binary
  floating-point for critical calculations."*

---

## 5. WEBSOCKET

### 5.1 URL y endpoints

El host es **el mismo Access Point** devuelto por discovery, con el esquema cambiado a `ws`/`wss`. Del
helper de ejemplo (que la doc marca como **no verificado**):

```ts
export function toWsBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
}
```

> ⚠️ Advertencia literal de la doc: *"The URL construction in this helper **still requires
> verification** of supported schemes, ports, trailing slashes and base-path prefixes. Do not treat it
> as a validated production URL builder. The connection URL and signed path must agree."*

| Caso de uso | Ruta WebSocket | Payload de suscripción |
|---|---|---|
| Ticks en vivo | `/v1/server-events/accounts/{account_id}/ws/ticks` | `id` + `subscribe.event = ticks` + `subscribe.instruments` |
| Transacciones | `/v1/server-events/accounts/{account_id}/ws/events` | `id` + `subscribe.event = transactions` |
| Estado de cuenta | `/v1/server-events/accounts/{account_id}/ws/events` | `id` + `subscribe.event = account_state` |
| Actualizaciones de instrumento | `/v1/server-events/accounts/{account_id}/ws/events` | `id` + `subscribe.event = instruments` + `subscribe.instruments` opcional |
| HMR | `/v1/server-events/accounts/{account_id}/ws/events` | `id` + `subscribe.event = hmr` + `subscribe.instruments` |

> *"Use this stream only for live ticks. Do not subscribe to `transactions`, `account_state`,
> `instruments`, or `hmr` through this stream."* y al revés: *"Do not subscribe to `ticks` through
> this stream."*
> *"HMR no longer uses a separate WebSocket endpoint."*

⚠️ En el OpenAPI estas dos rutas aparecen como **`POST`** (`getWSTicks`, `getWSEvents`), pero es un
modelado: *"This OpenAPI operation models the WebSocket subscription command message. The actual
WebSocket connection handshake is signed as a GET request."*

### 5.2 Handshake

- **Se firma el handshake como una solicitud `GET`**, no el mensaje de suscripción como POST.
- *"The signed `path` inside `EXN-DATA` must exactly match the WebSocket connection path."*
- Se usan las mismas 6 cabeceras `EXN-*`, con `idempotencyKey: ''` (GET firmado).
- En el ejemplo de la doc, el cliente abre la conexión con el **subprotocolo `'exness-ws-protocol'`**,
  `handshakeTimeout: 10000` y `perMessageDeflate: false`:

```ts
const headers = await buildSignedHeaders({
  apiKey: auth.apiKey, privateKey: auth.privateKey,
  method: 'GET', pathWithQuery: path, body: '', idempotencyKey: '',
});
const ws = new WebSocket(`${toWsBaseUrl(baseUrl)}${path}`, 'exness-ws-protocol', {
  headers, handshakeTimeout: 10000, perMessageDeflate: false,
});
```

- Conexiones que exceden `max_active_connections` o los buckets de `connection_rate` se **rechazan en
  el handshake con HTTP 429**.
- `buildSignedHeaders` es un helper **ilustrativo y no provisto por la página**: *"The imported
  `./lib/` helpers are illustrative dependencies and are not provided by this page."*

### 5.3 Formato de suscripción

Esquema `WSTicksSubscribeRequestData` — obligatorios `id` y `subscribe`; dentro de `subscribe`,
obligatorios `event` (único valor `ticks`) e `instruments`:

```json
{
  "id": "ticks-xauusd-1",
  "subscribe": {
    "event": "ticks",
    "instruments": ["XAUUSD"]
  }
}
```

`WSEventsCommandRequestData` = `oneOf` de **subscribe** (`{id, subscribe}`) y **unsubscribe**
(`{id, unsubscribe}`), ambos con los dos campos obligatorios. El objeto de suscripción es un `oneOf`:

| `event` | Campos obligatorios | Notas |
|---|---|---|
| `transactions` | `event` | sin `instruments` |
| `account_state` | `event` | sin `instruments` |
| `instruments` | `event`, `instruments[]` | admite `["all"]` para todos los del account |
| `hmr` | `event`, `instruments[]` | **no existe wildcard `all` para `hmr`** |

```json
{ "id": "subscribe-transactions-1", "subscribe": { "event": "transactions" } }
{ "id": "instrument-updates",       "subscribe": { "event": "instruments", "instruments": ["all"] } }
{ "id": "hmr-subscribe",            "subscribe": { "event": "hmr", "instruments": ["XAUUSD"] } }
```

Para desuscribir: mismo objeto bajo la clave `unsubscribe`. Los instrumentos no suscritos se ignoran.
*"Use exactly `["all"]` to unsubscribe from all instrument updates."*

**Reglas de rechazo:** cada instrumento pedido debe estar disponible para la cuenta; *"if at least one
requested instrument is not available for the account, the **entire** subscription request is
rejected; existing subscriptions are not affected"*.

### 5.4 Mensajes de ticks

`WSTick` (ningún campo marcado obligatorio en el schema):
`instrument` (`InstrumentName`) · `bid` (`number`/`double`) · `ask` (`number`/`double`) ·
`timestamp` (string `date-time`).

- *"Upon successful subscription, the server sends the last tick for each subscribed instrument."*
- Throttling: hasta **una actualización cada 500 ms**.
- No disponible si `trade_mode` es `trading_disabled`.

El ejemplo de la doc lee exactamente `message.instrument`, `message.bid`, `message.ask`,
`message.timestamp` del mensaje raíz (**sin envoltorio `payload`**).

### 5.5 Mensajes de eventos

`WSTradingEvent` = `oneOf` de seis sobres. **Dos familias de forma distinta**, y la doc lo marca:

| `event_type` | Forma | Campos |
|---|---|---|
| `trading_state_snapshot` | con `payload` | obligatorios `event_type`, `payload` → `TradingStateSnapshot` (`orders[]`, `positions[]`, `account_state`) |
| `transaction_event` | con `payload` | obligatorios `event_type`, `payload`. Nivel de sobre: `operation_id` (`UInt64String`), `client_request_id` (string), `status` (`success`\|`failed`\|`rejected`), `error_code` (integer), `error_message` (string), `event_time` (date-time). `payload` → `TransactionPayload` |
| `account_state_event` | con `payload` | obligatorios `event_type`, `event_time`, `payload` → `{account_state}` (obligatorio) con `balance`, `equity`, `used_margin` |
| `instrument_event` | con `payload` | obligatorios `event_type`, `event_time`, `action`, `payload`. `action` = `new`\|`upd`\|`del`. `payload` = **`InstrumentConditionResponse` completo**, no solo los campos cambiados |
| `hmr_snapshot` | **sin `payload`** | obligatorios `event_type`, `periods[]` (`HmrPeriod`), al nivel raíz del evento |
| `hmr_update` | **sin `payload`** | obligatorios `event_type`, `upserted_periods[]` (`HmrPeriod`), `removed_period_ids[]` (`UInt64String`), al nivel raíz. *"HMR events do not include `event_time` in the current version."* |

`TransactionPayload` (ningún campo obligatorio): `orders[]` · `positions[]` · `deals[]` ·
`account_state` (`TransactionAccountState`).
*"The payload contains **only** entities created or changed as a result of this concrete
transaction."* · *"Transaction is a meta-entity. It does not have its own transaction identifier."*

Composición por escenario (textual):

| Escenario | Payload posible |
|---|---|
| Colocación de orden pendiente | `order` y `account_state` |
| Orden pendiente con SL/TP | la pendiente principal, la orden SLTP y `account_state` |
| Apertura de posición | `order`, `deal`, `position` y `account_state` |
| Cierre parcial | `order`, `deal`, la posición actualizada y `account_state` |
| Operación de balance | un deal de tipo balance y `account_state` |

`HmrPeriod` — **todos obligatorios**: `period_id` (`UInt64String`) · `event_type`
(`regular` = evento puntual \| `periodic` = se repite cada semana) · `instruments[]` · `leverage`
(string) · `start_time` (string) · `end_time` (string).

Ejemplos literales de mensajes:
```json
{ "event_type": "transaction_event", "operation_id": "789", "status": "success",
  "client_request_id": "order-2026-06-22-0001" }
```
```json
{ "event_type": "transaction_event", "operation_id": "789", "status": "rejected",
  "error_code": 5006, "error_message": "TRADING_RULE_INSUFFICIENT_MARGIN",
  "event_time": "2026-12-14T11:46:30+00:00", "payload": {} }
```

### 5.6 Reconexión y recuperación

> *"WebSocket streams are realtime streams and **do not provide durable replay, resume tokens, or
> gap-fill by event id**."*
> *"After reconnect, the client must create a new WebSocket connection and resubscribe."*

Secuencia textual: reconectar con backoff → firmar el handshake nuevo con la ruta exacta → reiniciar
las suscripciones → pedir o esperar un snapshot fresco donde el stream lo soporte → reconciliar el
estado local antes de seguir con el procesamiento incremental.
Recuperación de resultado de operación: si se recibió el ACK pero no se vio el `transaction_event`,
usar `GET /v1/trading/accounts/{account_id}/operations/{operation_id}` **mientras el estado siga
retenido** (24 h).
Cierre por abuso: policy-violation **RFC 6455 código 1008** al exceder `strikes.threshold`, o por
desborde de la cola de salida (slow consumer).

---

## 6. CUENTAS DEMO

**La documentación no lo menciona.**

Verificado por búsqueda textual de `demo`, `real account`, `live account`, `practice` en las 31
páginas extraídas y en el `trading.public.yaml` completo: **cero coincidencias** sobre
compatibilidad con cuentas demo. La doc habla siempre de *"your trading account"* / *"the trading
account that the key can access"* sin distinguir tipo. Lo más cerca que llega es `exnsk-live-example`
como valor de ejemplo de API key — pero es un placeholder, no una afirmación sobre tipos de cuenta.

Lo que sí distingue la doc es **tipos de cuenta por niveles de margen** (§7), lo que indica que el
tipo de cuenta importa; pero demo vs. real no aparece.

---

## 7. RESTRICCIONES

### 7.1 Requisitos previos (de *Overview*, textual)

- **Exness account:** *"You need an Exness platform-based account."*
- **Full KYC:** *"You need to provide proof of identity and proof of address (where applicable)
  **before API access can be enabled**."*
- **Account ID, API Key y Secret Key:** *"After eligibility is met, create credentials in Key
  Management"*. La palabra *eligibility* aparece sin definirse.

### 7.2 Regiones y jurisdicciones

**No documentado.** Búsqueda textual de `region`, `jurisdiction`, `restricted countr`, `country` en
las 31 páginas y en el YAML: no hay ninguna restricción geográfica declarada.

### 7.3 Tipos de API key y alcance

- Hay al menos dos tipos: *"Use an **Exness API key**, not an **Info API key**"* para trading
  (*Place Your First Trade*), y en el flujo recomendado: *"Need read-only integration? → Use **Info API
  key** and avoid mutating endpoints."* **Qué otros tipos existen y cómo se eligen: no documentado.**
- La API key se restringe por: **cuenta de trading** (o grupo de cuentas), **fecha de expiración**,
  **IPs permitidas** (*"if these fields are enabled"*) y **operation scope**.
- *"The API key must be allowed to access the requested account, source IP, and operation scope."*
- El error `1002 AUTH_PERMISSION_DENIED` cubre los tres: cuenta, IP de origen y scope.

### 7.4 Estados de cuenta que bloquean operaciones

`trade_mode` y `account_status` son **independientes**; *"Any combination of these fields is valid"*
(ejemplos de la doc: `trade_mode=trading_disabled` con `account_status=active`, y `trade_mode=enabled`
con `account_status=close_only`).

| Campo / valor | Efecto |
|---|---|
| `trade_mode = enabled` | la cuenta está disponible para operar |
| `trade_mode = trading_disabled` | *"trading operations and trading-related realtime streams are disabled; configuration remains available"* |
| `account_status = active` | abrir, modificar y cerrar está permitido |
| `account_status = close_only` | **solo** cerrar posiciones y cancelar órdenes. `2002 ACCOUNT_CLOSE_ONLY` / HTTP 403 |
| `2001 ACCOUNT_DISABLED` | HTTP 403 — *"Do not send new trading requests"* |
| Instrumento `MARKET_TRADE_DISABLED` / `MARKET_CLOSE_ONLY` | restricción al nivel del instrumento, no de la cuenta |
| `MARKET_SESSION_CLOSED` | HTTP 409 — hay que esperar la sesión del instrumento (`trade_sessions` con `week_start_time`/`week_end_time`) |

### 7.5 Uso automatizado

**Explícitamente permitido y previsto.** *"What you can build"* incluye literalmente: *"**Trading
bot** — Open, modify, and close exposure through signed REST operations"*, integración de market data,
monitoreo de cuenta, *"Automated SLTP management"* y dashboard propio. No hay ninguna cláusula en la
doc técnica que limite la frecuencia de operación más allá de los rate limits.

Pero sí hay un descargo explícito sobre los ejemplos: *"The following examples are simplified
onboarding examples… **They are NOT production-ready trading bots.** Production systems should
additionally implement: reconnect handling, rate limit tracking, persistence, retry policies, risk
management, monitoring, security hardening."*

### 7.6 Margen, apalancamiento y HMR (restricciones económicas duras)

Fórmulas literales de *Formulas & Calculations*:

```
equity        = balance + floating_pnl
free_margin   = equity - used_margin
margin_level  = (equity / used_margin) * 100     # indefinido si used_margin = 0

buy_position_pnl  = volume * (LastBidPrice - OpenPrice) * contractSize * ProfitRate
sell_position_pnl = volume * (OpenPrice - LastAskPrice) * contractSize * ProfitRate

# calc_mode "Forex" o "ForexNoLeverage" (calc_mode = 1 o 2):
used_margin = volume * contractSize * marginRate * marginPercentage
# calc_mode "CFD" o "CFDLeverage" (calc_mode = 3 o 4):
used_margin = volume * contractSize * openPrice * marginRate * marginPercentage

# marginPercentage:
#   Forex / CFDLeverage      -> 1 / account.leverage  (0 si el apalancamiento es ilimitado)
#   ForexNoLeverage / CFD    -> instrument.margin_percent

margin call: margin_level <= margin_call_level
stop out:    margin_level <= stopout_level
```

⚠️ Esa página numera los `calc_mode` **1..4**, pero el enum del OpenAPI es
`undefined | forex | forex_no_leverage | cfd | cfd_leverage` (strings). Contradicción de notación.

**Niveles por tipo de cuenta** (la doc dice *"At Exness, margin call and stop levels are based on
trading account types"*):

| Cuenta | Margin Call | Stop Out |
|---|---|---|
| Standard Cent | 60% | 0% |
| Standard | 60% | 0% |
| Pro | 30% | 0% |
| Raw Spread | 30% | 0% |
| Zero | 30% | 0% |

**Apalancamiento:** mínimo `1:2` · *"Leverage cannot be disabled"* · *"The leverage requested by the
client when opening an account is not a mandatory requirement for execution"* · puede reducirse
durante HMR · se sigue por los eventos HMR del stream de Server Events.

**HMR (Higher Margin Requirements):** *"For the majority of instruments, orders opened up to **15
minutes before and 90 seconds after** a high-impact news release are subject to higher margin
requirements."* También aplica antes y después de las pausas programadas de mercado (fines de semana,
feriados, pausas diarias).

| Grupo | Instrumentos | Apalancamiento durante HMR |
|---|---|---|
| Forex | All | 1:200 |
| Energies | USOIL | 1:20 |
| Energies | UKOIL | 1:20 |
| Energies | XNGUSD | 1:5 |
| Metals | XAU | 1:200 – 1:1000 |
| Metals | XAG | 1:50 – 1:200 |
| Metals | XALUSD, XCUUSD, XNIUSD, XPBUSD, XZNUSD | 1:50 |
| Cryptocurrencies | All | 1:200 |

| Pausa | Antes | Después |
|---|---|---|
| Fin de semana — todos salvo BTC y ETH* | ~3 horas | 1 hora |
| USOIL (diaria) | 30 minutos | 5 minutos |
| UKOIL (diaria) | ~30 minutos | 5 minutos |
| Oro `XAU*` (diaria) | 30 minutos | ~10 minutos |
| Plata `XAG*` (diaria) | 30 minutos | ~10 minutos |
| BTCXAG, BTCXAU (diaria) | ~30 minutos | 5 minutos |

Enlaces externos que da la doc:
`https://get.exness.help/hc/en-us/articles/20618327917596-Higher-Margin-Requirements-HMR` y
`https://get.exness.help/hc/en-us/articles/360014529380-Leverage` (**no descargados en esta extracción**).

**Otras restricciones de negocio:** *"Margin requirements for fully hedged orders equal 0%"* ·
*"No margin is taken for pending orders"* · topes de cantidad reflejados en
`TRADING_RULE_TOO_MANY_PENDING_ORDERS` y `TRADING_RULE_TOO_MANY_OPEN_POSITIONS` — **los números de
esos topes no están documentados**.

### 7.7 Reglas de conversión de divisa (textual)

```
if currency_from == currency_to: conversion_rate = 1.0
else: conversión directa (par XXXYYY) → si no, inversa (par YYYXXX)
      → si no, dos pasos vía USD: currency_from -> USD -> currency_to
```

`ConversionDirection` (distinto de la dirección de la posición):
`Sell`: base→quote = `bid`, quote→base = `1/ask`. `Buy`: base→quote = `ask`, quote→base = `1/bid`.
**`ProfitRate`** (quote → moneda de cuenta): con `calc_mode` forex / forex_no_leverage depende de la
dirección de la posición (buy→Buy, sell→Sell); con cfd / cfd_leverage depende de la rentabilidad
(profit > 0 → Sell, profit < 0 → Buy).
**`MarginRate`** (margin currency → moneda de cuenta): se calcula al abrir la posición y queda
guardado en `Position.margin_rate`; la dirección de conversión es la misma que la de la posición.

---

## 8. LAGUNAS

Lo que la documentación **no** aclara y hay que probar contra el servidor real.

### Bloqueantes para escribir el cliente

1. **Los rate limits no tienen ni un número público.** El contrato define la forma pero no trae un solo
   valor de ejemplo. Hasta hacer un `GET /v1/configuration/accounts/{id}/limits` con credencial real
   **no se sabe si la API soporta 5 o 500 solicitudes por minuto**, ni cuántas conexiones WebSocket
   concurrentes, ni `max_candles_per_request`, ni `history_age_days` / `history_range_days`. Esto
   decide si una estrategia es viable y no se puede estimar desde la doc.
2. **No hay ninguna implementación de referencia de la firma.** La prosa describe el algoritmo
   completo, pero `buildSignedHeaders` / `./lib/signing.js` son *"illustrative dependencies and are not
   provided by this page"*. Hay que escribirla a ciegas y validarla contra el servidor. Tres puntos
   que la doc no fija y que rompen la firma si se eligen mal: **la serialización exacta del JSON de
   `EXN-DATA`** (orden de claves, espacios, ¿`timestamp` y `sign_version` como números o como
   strings?), si el `path` firmado puede tener o no barra final, y qué cuenta como "el cuerpo exacto"
   para el `body_hash` (¿el byte stream enviado, antes o después de cualquier serialización del cliente?).
3. **La construcción de la URL del WebSocket está declarada no verificada por Exness misma:**
   *"requires verification of supported schemes, ports, trailing slashes and base-path prefixes"*.
   Además el subprotocolo `'exness-ws-protocol'` aparece **solo** en el código de ejemplo, nunca en la
   prosa normativa: no se sabe si es obligatorio.

### Importantes

4. **La ventana de tolerancia del `EXN-TIMESTAMP` no está documentada.** Solo *"must be close to the
   server time"*. Sin ese número no se puede decidir si hace falta sincronizar reloj con NTP ni cuánto
   clock skew tolera un VPS.
5. **Cómo se obtiene el Gateway host no es automatizable según la doc:** sale de un *"DNS widget"* en
   Key Management, es decir de la UI. No hay endpoint ni dominio estable publicado, y los dos hosts
   que aparecen (`api.exness.com`, `api.exness-api.com`) están marcados como *"review/prototype
   example only… not an alternative to discovery"*. Un cron que reconstruya el cliente desde cero
   necesita ese host hardcodeado o leído de un secreto.
6. **Cuentas demo: silencio total** (§6). Hay que probar si una cuenta demo aparece en Key Management
   y si el discovery le devuelve Access Point. Esto decide si se puede hacer paper trading antes de
   arriesgar plata, y es la primera pregunta de cualquier prueba.
7. **Qué significa "eligibility"** más allá de KYC completo: ¿hace falta depósito mínimo, antigüedad,
   un tipo de cuenta específico, solicitud aprobada? No está escrito.
8. **Qué tipos de API key existen y cómo se piden.** La doc nombra *"Exness API key"* e *"Info API
   key"* pero nunca lista los tipos ni los scopes disponibles.
9. **Timeouts del servidor: no documentados.** Ni HTTP, ni idle del WebSocket, ni si hay ping/pong
   obligatorio. La doc menciona que se valida cada mensaje entrante *"(subscribe, unsubscribe, ping,
   custom)"*, lo que implica que existe un `ping`, pero **no documenta su formato ni su cadencia**.
10. **Topes de órdenes y posiciones sin número:** `TRADING_RULE_TOO_MANY_PENDING_ORDERS` y
    `TRADING_RULE_TOO_MANY_OPEN_POSITIONS` existen como errores, pero el límite no aparece en ninguna
    parte ni en el endpoint de límites.
11. **Retención de idempotencia: *"a limited time"*.** Si el reintento de un cron cae fuera de esa
    ventana, la misma key se trata como solicitud nueva y **la orden se ejecuta dos veces**. Es un
    riesgo de dinero real sin número asociado.

### Contradicciones internas de la doc (hay que resolverlas probando)

12. **`EXN-IDEMPOTENCY-KEY` vacío: `-H "EXN-IDEMPOTENCY-KEY:"` vs `-H "EXN-IDEMPOTENCY-KEY;"`.** Las
    dos formas aparecen en páginas oficiales distintas y en curl **no son lo mismo** (la primera puede
    omitir la cabecera). Para GET firmados la cabecera es obligatoria con valor vacío, así que la
    diferencia decide si la solicitud pasa o devuelve `1001`.
13. **`stopout_level` (OpenAPI) vs `stop_out_level` (guía *Send Your First Request*)**, y la misma guía
    muestra la respuesta de cuenta **plana** con `account_id` numérico, mientras el contrato la define
    anidada bajo `settings` con `account_id` string.
14. **Tope de velas: `1000` fijo (Runtime Semantics) vs `max_candles_per_request` configurable
    (reference + OpenAPI).** El schema de `count` solo valida `≠ 0`.
15. **`1003 AUTH_RATE_LIMIT` existe en Troubleshooting pero no en el enum `PublicApiErrorCode`.** Un
    cliente que haga `match` exhaustivo sobre el enum va a romperse al recibirlo.
16. **`calc_mode` numerado 1–4 en Formulas vs enum de strings en el OpenAPI.** Las fórmulas de margen
    dependen de ese campo, así que hay que confirmar qué devuelve el servidor de verdad.
17. **Retención de posiciones cerradas: "1 month (subject to clarification)"** — la propia doc admite
    que el número no está cerrado.

### Menores

18. **El ejemplo POST del OpenAPI muestra el `body_hash` del cuerpo vacío** en un método con cuerpo
    obligatorio. Es un error del ejemplo, pero puede inducir a implementar mal la firma.
19. **`WSTick` no tiene ningún campo obligatorio en el schema** (ni `instrument`), y el propio ejemplo
    de la doc defiende contra eso (`if (!message.instrument || message.bid === undefined …) return;`).
    No se sabe qué mensajes llegan por ese stream además de los ticks.
20. **`Candle` tampoco tiene campos obligatorios**, así que no se sabe si puede venir una vela sin
    `close`.
21. **`close_by_position_id` aplica "only for account models and instruments where close-by is
    supported"** — qué modelos y qué instrumentos, no documentado.
22. **No hay endpoint para listar las posiciones u órdenes abiertas por separado**: solo el snapshot
    completo o el stream. Con muchas posiciones no se sabe si el snapshot pagina (su schema no tiene
    cursor).
23. **Las páginas de referencia no sirven por HTTP plano** para sacar esquemas; quien repita esta
    extracción debe ir directo al `trading.public.yaml`.
