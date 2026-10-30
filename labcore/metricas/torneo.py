"""Torneo: compara estrategias bajo condiciones IDENTICAS.

Reglas del torneo:
  1. Mismo capital, mismo periodo, mismos datos, mismos costos, mismo
     motor de riesgo. Si una estrategia corre con otras condiciones, no
     esta compitiendo: esta haciendo otra cosa.
  2. Los benchmarks (azar y pasiva) compiten SIEMPRE. No son decorativos:
     son la vara.
  3. El ranking NO es por rentabilidad. Una estrategia que gana plata con
     12 operaciones y un drawdown del 30% esta por debajo de una que gana
     menos con 300 operaciones y 6%.
  4. "NINGUNA CALIFICA" es un resultado valido y frecuente. El torneo
     tiene que poder declararlo.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..backtest.costos import ModeloCostos
from ..backtest.mercado import Barra
from ..backtest.motor import Backtester
from ..riesgo.kill_switch import KillSwitch
from ..riesgo.modelo import InstrumentSpec, RiskLimits
from ..riesgo.motor import RiskEngine
from .desempeno import Desempeno, evaluar


@dataclass
class Participante:
    strategy_id: str
    familia: str
    desempeno: Desempeno
    resumen_corrida: str


class Torneo:
    def __init__(
        self,
        spec: InstrumentSpec,
        costos: ModeloCostos,
        barras: list[Barra],
        capital_inicial: float = 10_000.0,
        limites: RiskLimits | None = None,
        periodos_por_ano: float = 252.0,
        ruta_kill_switch=None,
    ) -> None:
        self.spec, self.costos, self.barras = spec, costos, barras
        self.capital_inicial = capital_inicial
        self.limites = limites or RiskLimits()
        self.periodos_por_ano = periodos_por_ano
        self.ruta_ks = ruta_kill_switch
        self.participantes: list[Participante] = []

    def correr(self, estrategias: list,
               n_pruebas_totales: int | None = None) -> list[Participante]:
        """n_pruebas = cuantas combinaciones se probaron EN TOTAL.

        OJO (bug corregido 2026-10-29): por defecto es el numero de
        estrategias de ESTE torneo, pero si el torneo es parte de un
        barrido sobre varios instrumentos, hay que pasar el total
        (instrumentos x estrategias). Declarar 10 cuando se probaron 70
        debilita la correccion por busqueda multiple 7 veces y puede
        certificar un artefacto. El data snooping se cuenta sobre TODO lo
        que se probo, no sobre lo que se mira al final.
        """
        n_pruebas = n_pruebas_totales or len(estrategias)
        self.participantes = []
        for e in estrategias:
            # Un kill switch LIMPIO por participante: si una corrida corta
            # el sistema, no puede contaminar a la siguiente.
            ks = KillSwitch(self.ruta_ks) if self.ruta_ks else _ks_temporal()
            ks.desactivar(por="torneo")
            motor = RiskEngine(self.limites, ks)
            bt = Backtester(
                self.spec, self.costos, motor,
                capital_inicial=self.capital_inicial,
                barras_minimas=getattr(e, "barras_minimas", 0),
            )
            r = bt.correr(self.barras, e)
            d = evaluar(r, self.periodos_por_ano, n_pruebas=n_pruebas)
            self.participantes.append(Participante(
                strategy_id=getattr(e, "strategy_id", e.__class__.__name__),
                familia=getattr(e, "familia", "?"),
                desempeno=d,
                resumen_corrida=r.resumen(),
            ))
        return self.participantes

    # ---------------- ranking ----------------

    @staticmethod
    def _puntaje(d: Desempeno) -> float:
        """Puntaje que NO depende solo de rentabilidad.

        Penaliza drawdown, exige muestra y usa el Sharpe DESINFLADO, no el
        bruto. Una estrategia con muchas operaciones y poco drawdown le
        gana a una con suerte y pocas operaciones.
        """
        # La MISMA barrera que el veredicto, importada de alla para que no
        # puedan separarse. Y se exige el t-stat corregido: sin eso, el
        # torneo certificaba estrategias sobre paseos aleatorios.
        from .desempeno import MIN_OPERACIONES
        if (d.n_operaciones < MIN_OPERACIONES
                or d.sharpe_desinflado <= 0
                or d.t_stat <= d.umbral_t_corregido):
            return float("-inf")
        castigo_dd = 1.0 + max(d.max_drawdown_pct, 0.0) * 5.0
        confianza = min(d.n_operaciones / 100.0, 1.0)
        return (d.sharpe_desinflado / castigo_dd) * confianza

    def ranking(self) -> list[Participante]:
        return sorted(
            self.participantes,
            key=lambda p: self._puntaje(p.desempeno), reverse=True,
        )

    def califican(self) -> list[Participante]:
        """Las que superan la vara. Puede estar vacia, y a menudo lo esta."""
        bench = max(
            (self._puntaje(p.desempeno) for p in self.participantes
             if p.familia == "benchmark"),
            default=float("-inf"),
        )
        return [
            p for p in self.participantes
            if self._puntaje(p.desempeno) > max(bench, 0.0)
            and p.familia != "benchmark"
        ]
    def informe(self) -> str:
        ls = [
            "=" * 108,
            f"TORNEO  |  {len(self.participantes)} participantes  |  "
            f"{len(self.barras)} barras  |  capital {self.capital_inicial:,.0f}  |  "
            f"spread x{self.costos.multiplicador_spread:g}",
            "=" * 108,
            f"{'#':<3} {'estrategia':<26} {'familia':<11} {'ops':>5} "
            f"{'neto':>10} {'sharpe':>7} {'desinf':>7} {'maxDD':>7} "
            f"{'PF':>6} {'win':>6} {'puntaje':>8}",
            "-" * 108,
        ]
        for i, p in enumerate(self.ranking(), 1):
            d = p.desempeno
            pt = self._puntaje(d)
            ls.append(
                f"{i:<3} {p.strategy_id:<26} {p.familia:<11} {d.n_operaciones:>5} "
                f"{d.retorno_neto:>+10.2f} {d.sharpe:>7.2f} "
                f"{d.sharpe_desinflado:>7.2f} {d.max_drawdown_pct:>6.1%} "
                f"{min(d.profit_factor, 99.9):>6.2f} {d.win_rate:>5.1%} "
                f"{('  -inf' if pt == float('-inf') else f'{pt:>8.3f}')}"
            )
        ls.append("-" * 108)
        cal = self.califican()
        if not cal:
            ls += [
                "VEREDICTO: NINGUNA ESTRATEGIA CALIFICA.",
                "",
                "Ninguna supera a los benchmarks con muestra suficiente y",
                "Sharpe desinflado positivo. La recomendacion es NO OPERAR.",
                "Esto es un resultado del experimento, no un error del sistema.",
            ]
        else:
            ls.append(f"CALIFICAN {len(cal)}, y solo EN MUESTRA:")
            for p in cal:
                ls.append(f"  - {p.strategy_id}: {p.desempeno.veredicto}")
            ls += [
                "",
                "ADVERTENCIA: sobrevivir en muestra no es evidencia de",
                "rentabilidad futura. Falta fuera de muestra, walk-forward y",
                "costos medidos en la cuenta real.",
            ]
        ls.append("=" * 108)
        return "\n".join(ls)


def _ks_temporal() -> KillSwitch:
    import tempfile
    from pathlib import Path
    return KillSwitch(Path(tempfile.mkdtemp(prefix="torneo-ks-")) / "ks.json")
