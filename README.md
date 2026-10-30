# Laboratorio de trading algorítmico — Exness

**Estado: LABORATORIO. No envía órdenes reales. No hay credenciales de trading cargadas.**

Runtime en disco local (`~/trading-lab`), NO en el montaje de Google Drive:
el montaje es FUSE por rclone y el VPS ya tiene presión de I/O medida.
Documentación de cara al usuario y punteros: ver `docs/`.

## Principio de diseño que ordena todo

El motor de riesgo (`labcore/riesgo/`) es **puro, determinista y sin red**.
Ningún LLM, ninguna estrategia y ningún agente puede modificarlo en caliente.
Deniega por defecto: una orden se aprueba solo si pasa TODAS las comprobaciones.
