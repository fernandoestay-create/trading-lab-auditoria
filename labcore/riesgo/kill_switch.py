"""Kill switch persistente.

NO vive en /tmp: un reinicio borraria el corte y el sistema se reactivaria
solo, que es exactamente el fallo silencioso que hay que evitar.
Escritura atomica (temporal + replace) para que un corte de luz no deje
un archivo a medio escribir que luego no se pueda leer.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

RUTA_DEFECTO = Path.home() / ".trading-lab" / "kill_switch.json"


class KillSwitch:
    def __init__(self, ruta: Path | None = None) -> None:
        self.ruta = ruta or RUTA_DEFECTO
        self.ruta.parent.mkdir(parents=True, exist_ok=True)

    def activo(self) -> bool:
        """Ante cualquier duda, devuelve True (fail-safe).

        Si el archivo existe pero esta corrupto NO se asume que todo esta
        bien: se asume detenido. Un parser roto no debe habilitar trading.
        """
        if not self.ruta.exists():
            return False
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return True
        return bool(datos.get("activo", True))

    def motivo(self) -> str:
        try:
            return str(
                json.loads(self.ruta.read_text(encoding="utf-8")).get("motivo", "")
            )
        except (json.JSONDecodeError, OSError):
            return "archivo de kill switch ilegible: se asume detenido"

    def activar(self, motivo: str, por: str = "sistema") -> None:
        self._escribir({"activo": True, "motivo": motivo, "por": por})

    def desactivar(self, por: str = "humano") -> None:
        self._escribir({"activo": False, "motivo": "", "por": por})

    def _escribir(self, datos: dict) -> None:
        datos["ts"] = datetime.now(timezone.utc).isoformat()
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.ruta)
