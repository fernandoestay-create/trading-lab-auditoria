"""Metricas de desempeno, con la incertidumbre incluida.

La regla que ordena este modulo: un resultado historico NO es un hallazgo.
Toda metrica que se reporte va acompanada de cuanta confianza merece dado
el numero de observaciones y el numero de estrategias que se probaron.

Un Sharpe de 1,2 medido sobre 40 operaciones y elegido entre 200 candidatas
no es un Sharpe de 1,2: es ruido con buena presentacion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Barras por ano segun temporalidad, para anualizar.
PERIODOS_POR_ANO = {
    "M1": 60 * 24 * 252, "M5": 12 * 24 * 252, "M15": 4 * 24 * 252,
    "H1": 24 * 252, "H4": 6 * 252, "D1": 252,
}


@dataclass(frozen=True)
class Desempeno:
    n_operaciones: int
    operaciones_por_ano: float
    t_stat: float
    umbral_t_corregido: float
    retorno_neto: float
    retorno_pct: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    profit_factor: float
    win_rate: float
    expectancy: float
    expectancy_r: float          # expectancy en multiplos del riesgo inicial
    sharpe_desinflado: float     # corregido por cuantas estrategias se probaron
    anos_minimos_necesarios: float
    costos_totales: float
    veredicto: str

    def __str__(self) -> str:
        return (
            f"ops={self.n_operaciones} neto={self.retorno_neto:+.2f} "
            f"({self.retorno_pct:+.2%}) sharpe={self.sharpe:.2f} "
            f"desinflado={self.sharpe_desinflado:.2f} "
            f"maxDD={self.max_drawdown_pct:.2%} PF={self.profit_factor:.2f} "
            f"win={self.win_rate:.1%} E[R]={self.expectancy_r:+.3f}R "
            f"| {self.veredicto}"
        )


def _retornos_por_operacion(pnls: np.ndarray, capital: float) -> np.ndarray:
    if capital <= 0:
        return np.array([])
    return pnls / capital


def sharpe(retornos: np.ndarray, periodos_por_ano: float = 252.0) -> float:
    if retornos.size < 2:
        return 0.0
    sd = float(np.std(retornos, ddof=1))
    if sd == 0.0:
        return 0.0
    return float(np.mean(retornos)) / sd * math.sqrt(periodos_por_ano)


def sortino(retornos: np.ndarray, periodos_por_ano: float = 252.0) -> float:
    """Solo castiga la volatilidad a la baja."""
    if retornos.size < 2:
        return 0.0
    malos = retornos[retornos < 0]
    if malos.size == 0:
        return float("inf") if float(np.mean(retornos)) > 0 else 0.0
    dd = float(np.sqrt(np.mean(malos ** 2)))
    if dd == 0.0:
        return 0.0
    return float(np.mean(retornos)) / dd * math.sqrt(periodos_por_ano)


def max_drawdown(curva: np.ndarray) -> float:
    """Caida maxima desde un maximo previo, en fraccion. Siempre >= 0."""
    if curva.size == 0:
        return 0.0
    picos = np.maximum.accumulate(curva)
    with np.errstate(divide="ignore", invalid="ignore"):
        caidas = np.where(picos > 0, (picos - curva) / picos, 0.0)
    return float(np.max(caidas))


def sharpe_desinflado(
    sr_observado: float, n: int, n_pruebas: int,
    asimetria: float = 0.0, curtosis: float = 3.0,
) -> float:
    """Sharpe corregido por BUSQUEDA MULTIPLE (Bailey y Lopez de Prado).

    Probar 200 estrategias y quedarse con la mejor produce un Sharpe alto
    por construccion, incluso si ninguna tiene ventaja. Esta funcion
    descuenta ese efecto: devuelve el Sharpe que quedaria despues de
    restar el maximo esperado por azar dado n_pruebas.

    ADVERTENCIA documentada: esta correccion NO es suficiente. Hay evidencia
    publicada de que un oraculo deliberadamente tramposo pasa este filtro
    intacto. Un desinflado positivo es necesario, no suficiente.
    """
    if n < 2 or n_pruebas < 1:
        return 0.0
    # Maximo esperado de n_pruebas variables normales estandar.
    if n_pruebas == 1:
        e_max = 0.0
    else:
        g = 0.5772156649015329  # Euler-Mascheroni
        inv = _norm_ppf(1.0 - 1.0 / n_pruebas)
        inv2 = _norm_ppf(1.0 - 1.0 / (n_pruebas * math.e))
        e_max = (1 - g) * inv + g * inv2
    # Error estandar del Sharpe, corregido por asimetria y curtosis.
    var = (1 - asimetria * sr_observado
           + (curtosis - 1) / 4.0 * sr_observado ** 2) / (n - 1)
    se = math.sqrt(max(var, 1e-12))
    # El descuento esta en unidades de Sharpe: se resta el maximo
    # esperado por azar (e_max) escalado por el error estandar.
    return sr_observado - e_max * se


def anos_minimos(sr_objetivo: float, asimetria: float = 0.0,
                 curtosis: float = 3.0, confianza: float = 0.95) -> float:
    """Cuantos anos de historia hacen falta para que un Sharpe de
    sr_objetivo sea distinguible de cero con esa confianza (MinTRL).

    Es la cifra que la critica puso sobre la mesa: con Sharpe 0,5 son del
    orden de 13 anos. Si tu serie es mas corta que esto, el backtest no
    puede concluir, por limpio que este.
    """
    if sr_objetivo <= 0:
        return float("inf")
    z = _norm_ppf(confianza)
    num = 1 - asimetria * sr_objetivo + (curtosis - 1) / 4.0 * sr_objetivo ** 2
    return 1.0 + num * (z / sr_objetivo) ** 2


def _norm_ppf(p: float) -> float:
    """Inversa de la normal estandar (Acklam). Evita depender de scipy."""
    if not 0.0 < p < 1.0:
        raise ValueError("p debe estar en (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def evaluar(
    resultado, periodos_por_ano: float = 252.0, n_pruebas: int = 1,
) -> Desempeno:
    """Convierte un ResultadoBacktest en un Desempeno con veredicto.

    n_pruebas es CUANTAS estrategias/configuraciones se probaron en total
    para llegar a esta. Si mientes aqui, todo lo demas miente.

    ANUALIZACION (bug corregido el 2026-10-28): el Sharpe se anualiza con
    la frecuencia REAL de operaciones, medida como operaciones / anos de
    datos. Anualizar retornos por operacion con sqrt(252) asume una
    operacion diaria; con 55 operaciones en 12 anos eso inflaba el Sharpe
    unas 7 veces y el laboratorio certificaba estrategias sobre ruido.
    El parametro periodos_por_ano quedo sin uso a proposito: se conserva
    en la firma por compatibilidad y se ignora.
    """
    cerradas = [o for o in resultado.operaciones if not o.abierta]
    cap = resultado.capital_inicial
    if not cerradas:
        # Con nombre, no por posicion: contar argumentos a mano es como
        # se cuelan los errores que acabo de cometer.
        return Desempeno(
            n_operaciones=0, operaciones_por_ano=0.0, t_stat=0.0,
            umbral_t_corregido=float("inf"),
            retorno_neto=0.0, retorno_pct=0.0,
            sharpe=0.0, sortino=0.0, max_drawdown_pct=max_drawdown(
                np.array([e for _, e in resultado.curva_equity], dtype=float)),
            profit_factor=0.0, win_rate=0.0, expectancy=0.0, expectancy_r=0.0,
            sharpe_desinflado=0.0, anos_minimos_necesarios=float("inf"),
            costos_totales=0.0,
            veredicto="SIN OPERACIONES: no hay nada que evaluar",
        )

    pnls = np.array([o.pnl_neto for o in cerradas], dtype=float)
    rs = _retornos_por_operacion(pnls, cap)
    curva = np.array([e for _, e in resultado.curva_equity], dtype=float)
    ganancias = pnls[pnls > 0]
    perdidas = pnls[pnls < 0]

    # Frecuencia real de operaciones, medida sobre el periodo de datos.
    anos = _anos_de_datos(resultado)
    ops_ano = len(cerradas) / anos if anos > 0 else 0.0
    sr = sharpe(rs, ops_ano)
    costos = sum(o.costo_comision - o.costo_swap for o in cerradas)
    riesgos = np.array([o.riesgo_inicial for o in cerradas], dtype=float)
    en_r = pnls / np.where(riesgos > 0, riesgos, np.nan)

    pf = (float(ganancias.sum()) / abs(float(perdidas.sum()))
          if perdidas.size and perdidas.sum() != 0 else float("inf"))
    sr_des = sharpe_desinflado(
        sr, len(cerradas), n_pruebas,
        asimetria=float(_asimetria(rs)), curtosis=float(_curtosis(rs)),
    )
    min_anos = anos_minimos(abs(sr)) if sr != 0 else float("inf")

    # Prueba de hipotesis directa sobre el P&L medio por operacion, con
    # el umbral corregido por busqueda multiple (Sidak). Esto es
    # independiente del Sharpe y de su anualizacion: si el t-stat no
    # supera el umbral, no hay nada que reportar.
    sd_pnl = float(np.std(pnls, ddof=1)) if pnls.size > 1 else 0.0
    t_stat = (float(pnls.mean()) / (sd_pnl / math.sqrt(pnls.size))
              if sd_pnl > 0 else 0.0)
    alfa_corr = 1.0 - (1.0 - 0.05) ** (1.0 / max(n_pruebas, 1))
    umbral_t = _norm_ppf(1.0 - alfa_corr)

    return Desempeno(
        n_operaciones=len(cerradas),
        operaciones_por_ano=ops_ano,
        t_stat=t_stat,
        umbral_t_corregido=umbral_t,
        retorno_neto=float(pnls.sum()),
        retorno_pct=float(pnls.sum()) / cap if cap else 0.0,
        sharpe=sr,
        sortino=sortino(rs, periodos_por_ano),
        max_drawdown_pct=max_drawdown(curva),
        profit_factor=pf,
        win_rate=float(ganancias.size) / len(cerradas),
        expectancy=float(pnls.mean()),
        expectancy_r=float(np.nanmean(en_r)) if en_r.size else 0.0,
        sharpe_desinflado=sr_des,
        anos_minimos_necesarios=min_anos,
        costos_totales=float(costos),
        veredicto=_veredicto(len(cerradas), sr, sr_des, n_pruebas,
                             t_stat, umbral_t),
    )


def _anos_de_datos(resultado) -> float:
    """Anos calendario que cubre la curva de equity."""
    c = resultado.curva_equity
    if len(c) < 2:
        return 0.0
    return max((c[-1][0] - c[0][0]).days / 365.25, 1e-9)


def _asimetria(x: np.ndarray) -> float:
    if x.size < 3:
        return 0.0
    sd = np.std(x, ddof=1)
    return 0.0 if sd == 0 else float(np.mean(((x - x.mean()) / sd) ** 3))


def _curtosis(x: np.ndarray) -> float:
    if x.size < 4:
        return 3.0
    sd = np.std(x, ddof=1)
    return 3.0 if sd == 0 else float(np.mean(((x - x.mean()) / sd) ** 4))


# Minimo de operaciones para que cualquier veredicto distinto de
# "no concluyente" sea posible. Es la misma barrera que usa el puntaje
# del torneo: si estos dos numeros se separan, el juez se contradice.
MIN_OPERACIONES = 100


def _veredicto(n: int, sr: float, sr_des: float, n_pruebas: int,
               t_stat: float, umbral_t: float) -> str:
    """El veredicto por defecto es NO CONCLUYENTE. Para decir otra cosa
    hay que superar TRES barreras a la vez, no dar un numero positivo."""
    if n < MIN_OPERACIONES:
        return (f"NO CONCLUYENTE: {n} operaciones, hacen falta "
                f"{MIN_OPERACIONES}. Bajo ese numero cualquier metrica es "
                f"anecdota, por buena que se vea")
    if sr <= 0:
        return "RECHAZADA: Sharpe no positivo"
    if t_stat <= umbral_t:
        return (f"RECHAZADA: t={t_stat:.2f} no supera el umbral corregido "
                f"de {umbral_t:.2f} para {n_pruebas} pruebas. El resultado "
                f"es compatible con azar")
    if sr_des <= 0:
        return (f"RECHAZADA: el Sharpe de {sr:.2f} desaparece al corregir "
                f"por las {n_pruebas} pruebas realizadas")
    return (f"SOBREVIVE EN MUESTRA (Sharpe {sr:.2f}, t={t_stat:.2f} sobre "
            f"umbral {umbral_t:.2f}): no es una promesa de rentabilidad. "
            f"Falta fuera de muestra, walk-forward y costos reales medidos")
