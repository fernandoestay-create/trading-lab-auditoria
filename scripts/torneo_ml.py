"""La ultima carta: los modelos de la Fase E contra las clasicas.

Todos bajo las MISMAS condiciones y juzgados por el MISMO juez, con la
correccion por busqueda multiple contando TODAS las combinaciones.
"""
from __future__ import annotations
import sys, warnings, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore"); logging.disable(logging.WARNING)

from labcore.backtest import ModeloCostos
from labcore.datos import INSTRUMENTOS, a_barras, descargar, validar
from labcore.estrategias import (
    Aleatoria, BandasBollinger, ComprarYMantener, CruceMedias, EstrategiaML,
    MACD, RSIReversion, RupturaDeRango, catalogo_ml,
)
from labcore.experimentos import RegistroExperimentos
from labcore.metricas import Torneo
from labcore.riesgo import InstrumentSpec, RiskLimits

CAPITAL = 2000.0


# Ventana de historia por instrumento. 4.000 barras diarias son ~16 anos:
# suficiente para el MinTRL de un Sharpe alto y mucho mas barato que 46
# anos. Medido el 2026-10-29: el random forest tarda ~65 s por cada 3.000
# barras, asi que la historia completa de 13 instrumentos pasaba de 50
# minutos y mi propio timeout la mataba.
MAX_BARRAS = 4000
# Reentrenar cada 500 en vez de 250: la mitad de ajustes de modelo. Es un
# parametro declarado, no un detalle escondido -- menos reentrenamientos
# significa que el modelo opera mas tiempo con informacion mas vieja.
REENTRENAR = 500


def participantes():
    cat = catalogo_ml()
    return [
        # --- los tres modelos del encargo ---
        EstrategiaML("logistica", cat["logistica"], umbral=0.55,
                     reentrenar_cada=REENTRENAR),
        EstrategiaML("bosque",    cat["bosque"],    umbral=0.55,
                     reentrenar_cada=REENTRENAR),
        EstrategiaML("gradiente", cat["gradiente"], umbral=0.55,
                     reentrenar_cada=REENTRENAR),
        # --- las clasicas, como vara ---
        CruceMedias(20, 50), MACD(), RupturaDeRango(20),
        RSIReversion(), BandasBollinger(),
        # --- benchmarks obligatorios ---
        Aleatoria(prob=0.04, semilla=7), ComprarYMantener(),
    ]


def main() -> int:
    reg = RegistroExperimentos()
    datos = {}
    for sim, cfg in INSTRUMENTOS.items():
        try: d, v = validar(sim, descargar(sim))
        except Exception: continue
        if not v.usable or len(d) < 1500:
            continue
        # Solo las ultimas MAX_BARRAS. Se recorta al FINAL, o sea se queda
        # con lo mas RECIENTE: usar los anos viejos de AAPL (a US$0,10)
        # mete regimenes que no se parecen en nada al mercado de hoy.
        datos[cfg["nombre"]] = (a_barras(d.tail(MAX_BARRAS), cfg["spread"]), cfg)
    n_total = len(datos) * len(participantes())
    print(f"ventana: ultimas {MAX_BARRAS} barras diarias (~16 anos) por "
          f"instrumento · reentrena cada {REENTRENAR}")
    print(f"US$ {CAPITAL:,.0f} · {len(datos)} instrumentos × "
          f"{len(participantes())} estrategias = {n_total} combinaciones")
    print("La correccion por busqueda multiple cuenta TODAS.")
    print()
    print("=" * 104)
    print(f"{'instrumento':<10} {'mejor estrategia':<24} {'familia':<17} "
          f"{'ops':>5} {'anual':>8} {'sharpe':>7} {'t':>6} {'umbral':>7} {'cal':>4}")
    print("-" * 104)
    ml_gana, cal_total = 0, 0
    for nombre, (barras, cfg) in sorted(datos.items()):
        spec = InstrumentSpec(
            nombre, cfg["contrato"], cfg["tick"], cfg["valor_tick"],
            0.01, 0.01, 0.01, cfg["grupo"])
        t = Torneo(spec, ModeloCostos(slippage_ticks=1.0), barras,
                   capital_inicial=CAPITAL, limites=RiskLimits())
        t.correr(participantes(), n_pruebas_totales=n_total)
        reg.anotar_torneo(
            t, etiqueta=f"torneo-ml/{nombre}",
            datos_descripcion="yfinance diario, spread relativo MODELADO",
            extra={"capital": CAPITAL, "n_pruebas_del_barrido": n_total})
        r = t.ranking()
        if not r:
            continue
        m = r[0]; d = m.desempeno
        anos = (barras[-1].ts - barras[0].ts).days / 365.25
        cagr = ((CAPITAL + d.retorno_neto)/CAPITAL)**(1/anos) - 1 if anos else 0
        cal = len(t.califican()); cal_total += cal
        if m.familia == "machine_learning":
            ml_gana += 1
        print(f"{nombre:<10} {m.strategy_id:<24} {m.familia:<17} "
              f"{d.n_operaciones:>5} {cagr:>+7.2%} {d.sharpe:>7.2f} "
              f"{d.t_stat:>6.2f} {d.umbral_t_corregido:>7.2f} {cal:>4}")
    print("-" * 104)
    print(f"instrumentos donde un modelo de ML quedo primero: "
          f"{ml_gana}/{len(datos)}")
    print(f"combinaciones que CALIFICAN (de {n_total}): {cal_total}")
    print()
    if cal_total == 0:
        print("VEREDICTO: NINGUNA CALIFICA, tampoco los modelos de ML.")
        print("Quedar primero en un ranking no es tener ventaja: todas")
        print("fueron rechazadas por el juez. La recomendacion es NO OPERAR.")
    else:
        print(f"CALIFICAN {cal_total}, y SOLO EN MUESTRA. Falta fuera de")
        print("muestra, walk-forward sobre periodo sellado y costos reales.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
