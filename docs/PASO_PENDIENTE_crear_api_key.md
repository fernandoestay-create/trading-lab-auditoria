# Paso pendiente: crear la API key de Exness

**Fecha: 2026-10-29.** Es lo ÚNICO que bloquea el laboratorio de trading.
Todo lo demás ya está construido y probado en el VPS.

## Lo que el VPS ya tiene

| Pieza | Estado |
|---|---|
| Llave privada Ed25519 | existe en el VPS, permisos 600, **no sale de ahí** |
| Llave pública | `LLAVE_PUBLICA_vps.pem`, en esta misma carpeta |
| Firmador Ed25519 | probado, 21 pruebas |
| Cliente de solo lectura | probado, 17 pruebas, IPv4 forzada |
| IP que verá Exness | `<IP-DEL-VPS>` (forzada a propósito) |
| **Credencial completa** | **FALTA — son 3 datos** |

## Los 3 datos que hay que traer

1. **API key identifier**
2. **Número de la cuenta de trading** asociada
3. **Host del "DNS widget"** (sin slash final)

Con esos tres se llena `~/.config/exness/env` en el VPS y corre la etapa 1.

## La pregunta que más importa

En el selector **"Trading account"** de Key Management: **¿aparece alguna cuenta DEMO?**

El contrato OpenAPI no distingue demo de real — `TradeMode` solo tiene
`enabled` y `trading_disabled`, y la API solo recibe un `account_id`. Así que si
la cuenta demo aparece en ese selector, **se puede operar en simulado por API**, y
se desbloquea la Fase J, que hoy está bloqueada porque la documentación no dice
nada sobre demo (cero menciones en 31 páginas y en el contrato).

## Configuración exacta del formulario

- Nombre: `trading-lab`
- Producto: **Trader API** (no Partnership, no Payments)
- Expiración: 12 meses. No dejarla sin vencimiento.
- Permisos: **los mínimos que permitan LEER** cuenta y datos de mercado.
  Si hay una opción SIN permiso de trading, esa.
- Allowed IPs: `<IP-DEL-VPS>`
- Par de llaves: **"I'll use my own public key"** y pegar el contenido de
  `LLAVE_PUBLICA_vps.pem`. NO dejar que Exness genere el par.

## Por qué permisos mínimos

Todavía no existe ninguna estrategia con ventaja demostrada. Una key que no
puede operar no puede equivocarse. Cuando corresponda, se crea una segunda.

## Por qué esa IP y no la IPv6

Medido el 2026-10-28: `www.exness-api.com` tiene registro AAAA y este VPS
prefiere IPv6, así que la API lo vería llegando desde `2a02:c207:2352:7171::1`
y no desde la IPv4 documentada. Con "Allowed IPs" en la IPv4, cada llamada
habría dado 403 sin explicar por qué. El cliente ahora fuerza IPv4.
