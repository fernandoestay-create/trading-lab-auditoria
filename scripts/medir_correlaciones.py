"""Mide la correlacion real y recalcula los grupos de riesgo."""
from __future__ import annotations
import sys, warnings, logging
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore"); logging.disable(logging.WARNING)
from labcore.correlaciones import agrupar, guardar, informe
from labcore.datos import INSTRUMENTOS, descargar, validar

def main() -> int:
    series = {}
    for sim, cfg in INSTRUMENTOS.items():
        try: d, v = validar(sim, descargar(sim))
        except Exception: continue
        if not v.usable: continue
        s = d["Close"].tail(1500); s.index = s.index.normalize()
        series[cfg["nombre"]] = s
    df = pd.DataFrame(series).dropna(how="all")
    r = np.log(df).diff()
    m = r.corr(min_periods=200)
    matriz = {a: {b: (None if pd.isna(m.loc[a, b]) else round(float(m.loc[a, b]), 4))
                  for b in m.columns} for a in m.columns}
    limpia = {a: {b: v for b, v in fila.items() if v is not None}
              for a, fila in matriz.items()}
    grupos = agrupar(limpia)
    guardar(grupos, matriz)
    print(f"medido sobre {len(r.dropna(how='all'))} dias, "
          f"{len(series)} instrumentos")
    print()
    print(informe())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
