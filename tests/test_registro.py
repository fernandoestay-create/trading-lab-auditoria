"""Pruebas del registro de experimentos.

Existe por L-129: una metrica que no persiste no es una metrica. Lo que se
prueba aqui no es que escriba un archivo, sino que el archivo permita
RESPONDER "sobre que lo mediste" sin volver a correr nada.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from labcore.backtest import Barra, ModeloCostos
from labcore.estrategias import Aleatoria, ComprarYMantener, CruceMedias
from labcore.experimentos import RegistroExperimentos, huella_barras, version_codigo
from labcore.metricas import Torneo
from labcore.riesgo import InstrumentSpec

UTC = timezone.utc
EURUSD = InstrumentSpec(
    symbol="EURUSD", contract_size=100_000, tick_size=0.00001,
    tick_value_account_ccy=1.0, min_volume=0.01, volume_step=0.01,
    margin_rate=0.01, correlation_group="USD_MAJOR",
)


def barras(n=400, semilla=1):
    import random
    rng = random.Random(semilla)
    d0 = datetime(2020, 1, 6, tzinfo=UTC)
    out, p = [], 1.1000
    for i in range(n):
        c = p * (1 + rng.gauss(0, 0.005))
        r = abs(rng.gauss(0, 0.003)) * p
        out.append(Barra(d0 + timedelta(days=i), p, max(p, c) + r / 2,
                         min(p, c) - r / 2, c, 1000.0, 0.00002))
        p = c
    return out


@pytest.fixture
def torneo_corrido():
    t = Torneo(EURUSD, ModeloCostos(), barras(), capital_inicial=10_000.0)
    t.correr([CruceMedias(10, 30), Aleatoria(semilla=3), ComprarYMantener()])
    return t


# ---------- la huella ata el numero a SUS datos ----------

def test_la_huella_cambia_si_cambia_un_solo_precio():
    a = barras(50, semilla=1)
    b = list(a)
    v = b[10]
    b[10] = Barra(v.ts, v.open, v.high, v.low, v.close + 0.00001,
                  v.volume, v.spread)
    assert huella_barras(a) != huella_barras(b)


def test_la_huella_es_estable_para_los_mismos_datos():
    assert huella_barras(barras(50, 1)) == huella_barras(barras(50, 1))


# ---------- persistencia ----------

def test_la_corrida_queda_en_disco_y_se_puede_auditar(tmp_path, torneo_corrido):
    r = RegistroExperimentos(tmp_path / "c.jsonl")
    rid = r.anotar_torneo(
        torneo_corrido, etiqueta="prueba",
        datos_descripcion="serie sintetica de prueba", semilla=1)
    assert (tmp_path / "c.jsonl").exists()
    texto = r.auditar(rid)
    # Las cuatro cosas que L-129 exige para que el numero sea defendible
    assert "huella datos  :" in texto      # 1. que datos
    assert "n_pruebas     :" in texto      # 2. con que parametros
    assert "codigo        :" in texto      # 3. con que codigo
    assert "participantes" in texto        # 4. que salio


def test_guarda_TODOS_los_participantes_no_solo_el_ganador(tmp_path, torneo_corrido):
    r = RegistroExperimentos(tmp_path / "c.jsonl")
    rid = r.anotar_torneo(torneo_corrido, etiqueta="x",
                          datos_descripcion="y", semilla=1)
    c = next(c for c in r.corridas() if c["run_id"] == rid)
    assert len(c["resultados"]) == 3
    ids = {x["strategy_id"] for x in c["resultados"]}
    assert "comprar-y-mantener" in ids     # el benchmark tambien queda


def test_es_append_no_sobrescribe(tmp_path, torneo_corrido):
    r = RegistroExperimentos(tmp_path / "c.jsonl")
    a = r.anotar_torneo(torneo_corrido, etiqueta="1", datos_descripcion="d")
    b = r.anotar_torneo(torneo_corrido, etiqueta="2", datos_descripcion="d")
    assert a != b
    assert len(r.corridas()) == 2


def test_cada_linea_es_json_valido(tmp_path, torneo_corrido):
    """Si una linea no es JSON, DuckDB y grep dejan de servir."""
    r = RegistroExperimentos(tmp_path / "c.jsonl")
    r.anotar_torneo(torneo_corrido, etiqueta="x", datos_descripcion="d")
    for l in (tmp_path / "c.jsonl").read_text(encoding="utf-8").splitlines():
        if l.strip():
            json.loads(l)


def test_una_linea_corrupta_se_DENUNCIA_no_se_salta(tmp_path, torneo_corrido):
    """Saltarse una linea mala en silencio es perder una corrida sin aviso."""
    ruta = tmp_path / "c.jsonl"
    r = RegistroExperimentos(ruta)
    r.anotar_torneo(torneo_corrido, etiqueta="buena", datos_descripcion="d")
    with open(ruta, "a", encoding="utf-8") as fh:
        fh.write("{esto no es json\n")
    cs = r.corridas()
    assert len(cs) == 2
    assert any(str(c.get("run_id", "")).startswith("CORRUPTA") for c in cs)


def test_nan_e_infinito_no_se_vuelven_null(tmp_path, torneo_corrido):
    """float('inf') en JSON estandar es invalido; se guarda como texto."""
    r = RegistroExperimentos(tmp_path / "c.jsonl")
    rid = r.anotar_torneo(torneo_corrido, etiqueta="x", datos_descripcion="d")
    c = next(c for c in r.corridas() if c["run_id"] == rid)
    crudo = json.dumps(c)
    assert "NaN" not in crudo.replace('"NaN"', "")   # solo como texto citado
    # la pasiva tiene anos_minimos infinito: tiene que estar, no ser null
    vals = [x["desempeno"]["anos_minimos_necesarios"] for x in c["resultados"]]
    assert all(v is not None for v in vals)


# ---------- el arbol sucio se declara ----------

def test_version_codigo_declara_si_el_arbol_esta_sucio():
    v = version_codigo()
    assert set(v) >= {"git_sha", "arbol_sucio", "reproducible"}
    # reproducible solo puede ser True si hay sha Y el arbol esta limpio
    if v["reproducible"]:
        assert v["git_sha"] and v["arbol_sucio"] is False
