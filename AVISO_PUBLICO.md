# Aviso

Esta es una copia **pública y anonimizada** del laboratorio, publicada para que
pueda ser auditada por terceros.

Se reemplazaron por marcadores: la IP del servidor, los números de cuenta, las
rutas del usuario, el correo y la llave pública de la API. Se quitaron los
archivos de resultados (`*.jsonl`), la cartera y la configuración local, porque
contienen huellas y resultados de una cuenta concreta.

El historial completo vive en un repositorio privado. Acá hay un solo commit.

**Este sistema no opera con dinero real.** Opera una cuenta de práctica (demo) de
Exness. La credencial de la cuenta real existe pero está bloqueada por un cerrojo
que exige dos variables de ambiente y autorización escrita del dueño — ver
`docs/AUTORIZACION_CUENTA_REAL.md`.

## Qué auditar

1. Que no exista camino alguno hacia la cuenta real sin autorización explícita
   (`labcore/exness/entorno.py`).
2. Que el motor de riesgo (`labcore/riesgo/motor.py`) no se pueda eludir.
3. Que el backtester no tenga look-ahead ni fuga de datos
   (`labcore/backtest/mercado.py`, `labcore/estrategias/aprendizaje.py`).
4. Que las métricas reportadas sean reproducibles.

Los 14 bugs que el autor ya encontró y corrigió están en
`docs/TUNING_aprendizaje.md`. El valor de una auditoría está en los que **no** vio.

    pip install -e .  # o: python -m pytest tests/ -q   (190 pruebas)
