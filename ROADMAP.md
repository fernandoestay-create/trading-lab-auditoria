# ROADMAP — Laboratorio de trading Exness

**Última actualización: 2026-10-29.**

## ✅ Hecho

**2026-10-29**
- Centinela diario instalado (cron 08:20), con alarma **verificada inyectando dos
  fallas reales**: anular el umbral del t-stat, y reintroducir el bug histórico del
  `sqrt(252)`. La segunda no se detectaba al principio: se agregó una guardia de
  **cifras**, no solo de veredicto.
- Firma Ed25519 y cliente de **solo lectura** (sin métodos de escritura, con cerrojo
  en tiempo de importación).
- **IPv4 forzada**: medido que el VPS salía por IPv6 y la API lo habría visto desde
  `2a02:c207:...` en vez de `<IP-DEL-VPS>` → 403 inexplicables.
- Par de llaves Ed25519 generado **en el VPS**, permisos 600.
- Registro de la tarea en la tabla única de `~/.claude/CLAUDE.md`.
- Descartado MiroFish (82.546 estrellas, AGPL-3.0): cero mediciones de acierto
  publicadas, y resuelve el problema que no tenemos.

**2026-10-28**
- Motor de riesgo, kill switch, backtester sin look-ahead, juez con 3 barreras,
  torneo con benchmarks, 6 estrategias clásicas, registro de experimentos (L-129),
  techo de recursos por systemd verificado en el kernel.
- **Seis bugs encontrados y corregidos**, en `docs/INFORME_LIMITACIONES.md`.

## 🔄 En progreso

- **Esperando la credencial de Exness.** El centinela la detecta solo y corre la
  etapa 1. Retomar desde `ESTADO.md`.

## ⏳ Pendiente priorizado

1. **Etapa 1**: costos reales desde la API (automática en cuanto exista la key).
2. **Escenarios de estrés** (Fase F, no necesita credencial): gap de fin de semana
   que salta el stop, latencia de 2 barras, régimen de volatilidad cambiado, Monte
   Carlo sobre el orden de las operaciones, swap triplicado. Los dos primeros son
   los que más probablemente tumben las estrategias que hoy pasan.
3. **Etapa 2**: histórico real → primer torneo sobre datos de verdad.
4. **Walk-forward y período sellado.** Mientras falten, el veredicto máximo posible
   sigue siendo "sobrevive en muestra".
5. **Etapa 3**: spread real por WebSocket + paper trading.
6. Repo privado en GitHub (`gh` no está instalado; el SSH sí autentica).

## 🧊 Backlog

- RAG de bibliografía (los 5 libros son comerciales: falta la ruta de los comprados).
- LLM como **crítico** de backtests, nunca como generador.
- Dashboard (el VPS no tiene capacidad hoy).

## 🐛 Issues conocidos

- El tope de riesgo subestima la pérdida real en medio spread por operación
  (nominal 50,00 → real 50,10). Documentado y fijado en una prueba.
- Con lote mínimo 0,01 y riesgo 0,5% sobre US$10.000, el stop más ancho operable son
  **5.000 ticks**. Limita qué estrategias son expresables.
- Los costos son **inventados** hasta que corra la etapa 1.

## 📊 Métricas

- 99 pruebas pasando · 2.036 líneas de código · ~1.400 de prueba
- 12 corridas registradas y auditables
- Costo acumulado en LLM: **0** (todo determinista, cero llamadas de modelo)
- Órdenes reales enviadas: **0**
