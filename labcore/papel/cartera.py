"""Cartera de papel: operaciones ficticias sobre precios REALES.

Persiste en disco y sobrevive reinicios. Distingue las tres cosas que la
Fase J exige y que casi todos confunden:

  SENAL   -> la estrategia dijo algo
  ORDEN   -> la senal paso el motor de riesgo y se dimensiono
  TRATO   -> la orden se "ejecuto" al precio de la barra siguiente

Una senal que el riesgo veto NO es una operacion perdida: es el sistema
funcionando. Se cuentan por separado para que no se confundan nunca.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

RUTA = Path.home() / "trading-lab" / "papel"


@dataclass
class PosicionPapel:
    instrumento: str
    estrategia: str
    side: str
    volume: float
    precio_entrada: float
    stop_loss: float
    take_profit: float | None
    riesgo_inicial: float
    abierta_en: str
    razon_apertura: str


@dataclass
class TratoPapel:
    instrumento: str
    estrategia: str
    side: str
    volume: float
    precio_entrada: float
    precio_salida: float
    stop_loss: float
    abierta_en: str
    cerrada_en: str
    razon_apertura: str
    razon_cierre: str
    riesgo_inicial: float
    pnl_bruto: float
    costo_comision: float
    costo_swap: float
    pnl_neto: float
    # En multiplos del riesgo inicial: la unidad que permite comparar
    # operaciones de instrumentos distintos.
    resultado_r: float


@dataclass
class Cartera:
    capital_inicial: float
    equity: float
    peak_equity: float
    abiertas: list[PosicionPapel] = field(default_factory=list)
    cerradas: list[TratoPapel] = field(default_factory=list)
    # Observaciones, no solo resultados (regla del vigilante silencioso).
    senales_vistas: int = 0
    ordenes_evaluadas: int = 0
    ordenes_vetadas: int = 0
    vetos_por_codigo: dict[str, int] = field(default_factory=dict)
    sin_poder_dimensionar: int = 0
    dias_operados: int = 0
    ultimo_dia: str = ""
    creada_en: str = ""

    # ---------- persistencia ----------

    @classmethod
    def cargar(cls, ruta: Path | None = None,
               capital_inicial: float = 1000.0) -> "Cartera":
        f = (ruta or RUTA) / "cartera.json"
        if not f.exists():
            return cls(capital_inicial=capital_inicial,
                       equity=capital_inicial, peak_equity=capital_inicial,
                       creada_en=datetime.now(timezone.utc).isoformat())
        d = json.loads(f.read_text(encoding="utf-8"))
        c = cls(**{k: v for k, v in d.items()
                   if k not in ("abiertas", "cerradas")})
        c.abiertas = [PosicionPapel(**x) for x in d.get("abiertas", [])]
        c.cerradas = [TratoPapel(**x) for x in d.get("cerradas", [])]
        return c

    def guardar(self, ruta: Path | None = None) -> None:
        base = ruta or RUTA
        base.mkdir(parents=True, exist_ok=True)
        d = asdict(self)
        f = base / "cartera.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, f)        # atomico: un corte no deja medio archivo
        # Diario append-only de tratos, para poder aprender despues.
        with open(base / "tratos.jsonl", "w", encoding="utf-8") as fh:
            for t in self.cerradas:
                fh.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")

    # ---------- metricas ----------

    @property
    def drawdown(self) -> float:
        return ((self.peak_equity - self.equity) / self.peak_equity
                if self.peak_equity > 0 else 0.0)

    @property
    def retorno_pct(self) -> float:
        return ((self.equity - self.capital_inicial) / self.capital_inicial
                if self.capital_inicial else 0.0)

    def resumen(self) -> str:
        n = len(self.cerradas)
        gan = [t for t in self.cerradas if t.pnl_neto > 0]
        suma_r = sum(t.resultado_r for t in self.cerradas)
        lineas = [
            f"capital inicial US$ {self.capital_inicial:,.2f}",
            f"equity actual    US$ {self.equity:,.2f}  "
            f"({self.retorno_pct:+.2%})",
            f"drawdown         {self.drawdown:.2%}",
            f"dias operados    {self.dias_operados}   ultimo: {self.ultimo_dia}",
            "",
            # PAREJA obligatoria: cuantas entraron y cuantas salieron.
            f"senales={self.senales_vistas}  ordenes_evaluadas="
            f"{self.ordenes_evaluadas}  vetadas={self.ordenes_vetadas}  "
            f"sin_dimensionar={self.sin_poder_dimensionar}",
            f"posiciones abiertas={len(self.abiertas)}  cerradas={n}",
        ]
        if n:
            lineas += [
                f"aciertos {len(gan)}/{n} ({len(gan)/n:.1%})  "
                f"resultado acumulado {suma_r:+.2f}R  "
                f"promedio {suma_r/n:+.3f}R",
            ]
        if self.senales_vistas and not self.cerradas and not self.abiertas:
            lineas.append(
                "ATENCION: hubo senales y NINGUNA operacion. Revisa los vetos "
                "antes de leer esto como 'no habia oportunidades'.")
        if self.vetos_por_codigo:
            lineas.append("vetos: " + ", ".join(
                f"{k}={v}" for k, v in sorted(
                    self.vetos_por_codigo.items(), key=lambda kv: -kv[1])))
        return "\n".join(lineas)
