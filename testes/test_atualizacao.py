# -*- coding: utf-8 -*-
"""Atualização da base com os arquivos do INPE (docs/03 §5) e nowcast (docs/07 §9).

O servidor do INPE é simulado com os recortes reais de ``amostras/inpe`` (datas trocadas para
jan/fev de 2025, logo depois do fim de ``amostras/bases``); nada é baixado da internet.
"""

import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from core import atualizacao
from core.atualizacao import (
    ARQUIVO_ANTERIOR, ARQUIVO_CONTROLE, ARQUIVO_TRAVA, SemConexao, URL_DIARIO, atualizar_base,
    dias_de_arquivos_diarios, dias_faltantes, disponiveis, ler_csv_inpe, meses_fechados, no_formato_da_base,
    planejar, situacao_da_base,
)
from core.config import AMOSTRAS_BASES, AMOSTRAS_DIR, NOME_FOCOS_PARQUET
from core.estatisticas import cobertura_base, estatisticas_territorio
from core.focos import carregar_focos, focos_do_municipio
from core.nowcast import nowcast_territorio
from core.territorios import municipios_brasil

INPE = AMOSTRAS_DIR / "inpe"
DIAS_JAN = [date(2025, 1, d) for d in range(1, 32)]


def aqua(nome: str) -> int:
    return int((pd.read_csv(INPE / nome)["satelite"] == "AQUA_M-T").sum())


class ServidorFalso:
    """Imita o índice e os downloads do INPE com os arquivos de amostras/inpe."""

    def __init__(self, diarios: list[str], mensais: list[str], substituir: dict | None = None):
        self.diarios, self.mensais, self.substituir = diarios, mensais, substituir or {}
        self.baixados = []

    def listar(self, url):
        return self.diarios if url == URL_DIARIO else self.mensais

    def baixar(self, url, destino: Path):
        nome = url.rsplit("/", 1)[-1]
        self.baixados.append(nome)
        shutil.copy(INPE / self.substituir.get(nome, nome), destino)


@pytest.fixture
def bases(tmp_path):
    destino = tmp_path / "bases"
    shutil.copytree(AMOSTRAS_BASES, destino)
    return destino


def primeira_busca(bases):
    servidor = ServidorFalso(["focos_diario_br_20250201.csv", "focos_diario_br_20250202.csv",
                              "focos_diario_br_20250203.csv"], ["focos_mensal_br_202501.csv"])
    agora = datetime(2025, 2, 3, 18, tzinfo=timezone.utc)
    resultado = atualizar_base(bases, agora=agora, listar_fn=servidor.listar, baixar_fn=servidor.baixar,
                               progresso=lambda _: None)
    return resultado, servidor


# ------------------------------------------------------------------- Plano

def test_dias_faltantes():
    assert dias_faltantes(date(2025, 1, 30), [date(2025, 1, 10)], date(2025, 2, 1)) == [
        date(2025, 1, 10), date(2025, 1, 31), date(2025, 2, 1)]
    assert dias_faltantes(date(2025, 2, 1), [], date(2025, 2, 1)) == []


def test_plano_usa_diario_e_mensal_so_quando_falta_diario():
    diarios, mensais = disponiveis(["focos_diario_br_20250201.csv", "focos_mensal_br_202501.csv",
                                    "focos_mensal_br_202502.csv", "outro.csv"])
    faltantes = [date(2025, 1, 30), date(2025, 1, 31), date(2025, 2, 1), date(2025, 2, 2)]
    fontes, sem_fonte = planejar(faltantes, diarios, mensais)
    assert [(f.tipo, f.nome, f.dias) for f in fontes] == [
        ("mensal", "focos_mensal_br_202501.csv", faltantes[:2]),
        ("diario", "focos_diario_br_20250201.csv", [date(2025, 2, 1)]),
        ("mensal", "focos_mensal_br_202502.csv", [date(2025, 2, 2)]),   # diário ainda não publicado
    ]
    assert sem_fonte == []
    _, sem_fonte = planejar([date(2025, 3, 1)], diarios, mensais)
    assert sem_fonte == [date(2025, 3, 1)]


def test_plano_prefere_arquivos_locais():
    locais = ({}, {(2025, 1): Path("/x/focos_mensal_br_202501.csv")})
    fontes, _ = planejar([date(2025, 1, 5)], {date(2025, 1, 5): "focos_diario_br_20250105.csv"}, {}, locais)
    assert fontes[0].local and fontes[0].tipo == "mensal"


# ---------------------------------------------------------------- Conversão

def test_le_so_o_satelite_de_referencia():
    focos = ler_csv_inpe(INPE / "focos_mensal_br_202501.csv", DIAS_JAN)
    assert len(focos) == aqua("focos_mensal_br_202501.csv")
    assert list(focos.columns) == ["lon", "lat", "data"]
    assert ler_csv_inpe(INPE / "focos_mensal_br_202501.csv", [date(2025, 1, 2)])["data"].eq("2025-01-02").all()


def test_csv_sem_coluna_e_recusado(tmp_path):
    ruim = tmp_path / "focos_diario_br_20250201.csv"
    pd.read_csv(INPE / "focos_diario_br_20250201.csv").drop(columns="satelite").to_csv(ruim, index=False)
    with pytest.raises(ValueError):
        ler_csv_inpe(ruim, [date(2025, 2, 1)])


def test_atribuicao_reproduz_a_base():
    """Município, UC e TI por ponto-no-polígono = os gravados na base consolidada (docs/03 §5)."""
    base = carregar_focos()
    nomes = {n for n, _, _ in municipios_brasil()[0]}
    base = base[base["NM_MUN"].isin(nomes)].sample(3000, random_state=1)
    refeito = no_formato_da_base(base[["lon", "lat", "data"]].reset_index(drop=True))
    for coluna in ("NM_MUN", "NM_UF", "SIGLA_UF", "UC", "TI", "ano", "mes"):
        assert (refeito[coluna].to_numpy() == base[coluna].to_numpy()).all(), coluna


# ----------------------------------------------------------- Atualização

def test_primeira_busca(bases):
    antes = pq.read_table(bases / NOME_FOCOS_PARQUET)
    resultado, servidor = primeira_busca(bases)
    assert resultado.situacao == "atualizada", resultado.mensagem
    # janeiro inteiro pelo mensal (fora da janela do diário), fevereiro pelos diários
    assert servidor.baixados == ["focos_mensal_br_202501.csv", "focos_diario_br_20250201.csv",
                                 "focos_diario_br_20250202.csv", "focos_diario_br_20250203.csv"]
    esperados = sum(aqua(n) for n in servidor.baixados)
    assert resultado.focos_novos == esperados
    assert resultado.ultimo_dia == date(2025, 2, 3)
    assert resultado.provisorios == [date(2025, 2, 3)]          # baixado no próprio dia

    depois = pq.read_table(bases / NOME_FOCOS_PARQUET)
    assert depois.schema == antes.schema
    assert depois.num_rows == antes.num_rows + esperados
    assert (bases / ARQUIVO_ANTERIOR).exists() and not (bases / ARQUIVO_TRAVA).exists()
    assert not (bases / ".baixando").exists()
    controle = json.loads((bases / ARQUIVO_CONTROLE).read_text(encoding="utf-8"))
    assert controle["ultimo_dia"] == "2025-02-03" and controle["provisorios"] == ["2025-02-03"]
    assert controle["historico"][-1]["focos_novos"] == esperados

    novos = carregar_focos(bases / NOME_FOCOS_PARQUET)
    novos = novos[novos["ano"] == 2025]
    assert set(novos["mes"]) == {1, 2}
    assert "SÃO FÉLIX DO XINGU" in set(novos["NM_MUN"])        # municípios da amostra
    assert (novos.loc[novos["lat"] > -3, "NM_MUN"] == "NONE").all()   # fora dos limites da amostra


def test_segunda_busca_refaz_o_dia_provisorio(bases):
    primeira_busca(bases)
    servidor = ServidorFalso(["focos_diario_br_20250203.csv", "focos_diario_br_20250204.csv"], [],
                             substituir={"focos_diario_br_20250203.csv": "focos_diario_br_20250203_completo.csv"})
    resultado = atualizar_base(bases, agora=datetime(2025, 2, 4, 12, tzinfo=timezone.utc),
                               listar_fn=servidor.listar, baixar_fn=servidor.baixar, progresso=lambda _: None)
    assert servidor.baixados == ["focos_diario_br_20250203.csv", "focos_diario_br_20250204.csv"]
    assert resultado.provisorios == [date(2025, 2, 4)]
    focos = carregar_focos(bases / NOME_FOCOS_PARQUET)
    assert (focos["data"] == "2025-02-03").sum() == aqua("focos_diario_br_20250203_completo.csv")   # trocado
    assert (focos["data"] == "2025-02-04").sum() == aqua("focos_diario_br_20250204.csv")
    assert not focos[focos["ano"] == 2025].duplicated().any()


def test_base_em_dia(bases):
    primeira_busca(bases)
    controle = json.loads((bases / ARQUIVO_CONTROLE).read_text(encoding="utf-8"))
    controle["provisorios"] = []
    (bases / ARQUIVO_CONTROLE).write_text(json.dumps(controle), encoding="utf-8")
    resultado = atualizar_base(bases, agora=datetime(2025, 2, 3, 23, tzinfo=timezone.utc),
                               listar_fn=pytest.fail, progresso=lambda _: None)
    assert resultado.situacao == "em_dia"


def test_sem_conexao_nao_altera_a_base(bases):
    def sem_rede(url):
        raise SemConexao("rede indisponível")
    antes = (bases / NOME_FOCOS_PARQUET).read_bytes()
    resultado = atualizar_base(bases, agora=datetime(2025, 2, 3, 18, tzinfo=timezone.utc), listar_fn=sem_rede,
                               progresso=lambda _: None)
    assert resultado.situacao == "sem_conexao" and "31/12/2024" in resultado.mensagem
    assert (bases / NOME_FOCOS_PARQUET).read_bytes() == antes
    assert situacao_da_base(bases)["ultima_busca"] is not None          # tentou hoje: não repete sozinho


def test_falha_no_download_deixa_os_dias_para_depois(bases):
    servidor = ServidorFalso(["focos_diario_br_20250201.csv", "focos_diario_br_20250202.csv"],
                             ["focos_mensal_br_202501.csv"])
    def baixar(url, destino):
        if url.endswith("202501.csv"):
            raise SemConexao("caiu")
        servidor.baixar(url, destino)
    resultado = atualizar_base(bases, agora=datetime(2025, 2, 2, 20, tzinfo=timezone.utc),
                               listar_fn=servidor.listar, baixar_fn=baixar, progresso=lambda _: None)
    assert resultado.situacao == "atualizada" and "próxima busca" in resultado.mensagem
    assert set(DIAS_JAN) <= set(resultado.provisorios)                  # janeiro fica pendente


def test_formato_inesperado_e_recusado(bases, tmp_path):
    ruim = tmp_path / "ruim.csv"
    ruim.write_text("id,lat,lon\n1,2,3\n", encoding="utf-8")
    servidor = ServidorFalso(["focos_diario_br_20250101.csv"], [])
    servidor.baixar = lambda url, destino: shutil.copy(ruim, destino)
    antes = (bases / NOME_FOCOS_PARQUET).read_bytes()
    resultado = atualizar_base(bases, agora=datetime(2025, 1, 1, 12, tzinfo=timezone.utc),
                               listar_fn=servidor.listar, baixar_fn=servidor.baixar, progresso=lambda _: None)
    assert resultado.situacao == "erro" and "não foi alterada" in resultado.mensagem
    assert (bases / NOME_FOCOS_PARQUET).read_bytes() == antes
    assert not (bases / ARQUIVO_TRAVA).exists()


def test_trava(bases):
    (bases / ARQUIVO_TRAVA).touch()
    assert atualizar_base(bases, listar_fn=pytest.fail).situacao == "ocupada"


def test_importar_pasta_local_sem_internet(bases):
    resultado = atualizar_base(bases, pasta_local=INPE, online=False,
                               agora=datetime(2025, 2, 2, 23, tzinfo=timezone.utc), progresso=lambda _: None)
    assert resultado.situacao == "atualizada"
    assert situacao_da_base(bases)["ultima_busca"] is None              # não conta como busca no INPE


def test_dias_dos_arquivos_diarios_ficam_registrados(bases):
    primeira_busca(bases)
    controle = json.loads((bases / ARQUIVO_CONTROLE).read_text(encoding="utf-8"))
    assert controle["dias_diarios"] == ["2025-02-01", "2025-02-02", "2025-02-03"]   # janeiro veio do mensal
    # controle antigo, sem a lista: reconstruída pelo histórico
    assert dias_de_arquivos_diarios({"historico": controle["historico"]}) == {
        date(2025, 2, 1), date(2025, 2, 2), date(2025, 2, 3)}


def test_meses_fechados():
    dias = {date(2025, 1, 30), date(2025, 1, 31), date(2025, 2, 1)}
    # 31/01 fecha 30 h depois da meia-noite UTC: 01/02 às 06:00
    assert meses_fechados(dias, datetime(2025, 2, 1, 5, tzinfo=timezone.utc)) == {}
    assert meses_fechados(dias, datetime(2025, 2, 1, 7, tzinfo=timezone.utc)) == {
        (2025, 1): [date(2025, 1, 30), date(2025, 1, 31)]}


def test_mes_fechado_e_trocado_pelo_mensal_consolidado(bases):
    """P17: quando fevereiro fecha e o INPE publica o mensal, os dias diários de fevereiro saem dele."""
    primeira_busca(bases)
    mensal_fev = bases.parent / "focos_mensal_br_202502.csv"
    pd.concat([pd.read_csv(INPE / f"focos_diario_br_2025020{d}.csv") for d in (1, 2)]
              + [pd.read_csv(INPE / "focos_diario_br_20250203_completo.csv")]).to_csv(mensal_fev, index=False)
    servidor = ServidorFalso([f"focos_diario_br_202503{d:02d}.csv" for d in (1, 2)], ["focos_mensal_br_202502.csv"])
    servidor.baixar = lambda url, destino: (servidor.baixados.append(url.rsplit("/", 1)[-1]),
                                            shutil.copy(mensal_fev if "202502" in url else INPE /
                                                        "focos_diario_br_20250204.csv", destino))
    agora = datetime(2025, 3, 2, 12, tzinfo=timezone.utc)
    resultado = atualizar_base(bases, agora=agora, listar_fn=servidor.listar, baixar_fn=servidor.baixar,
                               progresso=lambda _: None)
    assert resultado.situacao == "atualizada", resultado.mensagem
    assert "focos_mensal_br_202502.csv" in servidor.baixados
    controle = json.loads((bases / ARQUIVO_CONTROLE).read_text(encoding="utf-8"))
    assert not any(d.startswith("2025-02") for d in controle["dias_diarios"])        # consolidados
    focos = carregar_focos(bases / NOME_FOCOS_PARQUET)
    assert (focos["data"] == "2025-02-03").sum() == aqua("focos_diario_br_20250203_completo.csv")
    assert not focos[focos["ano"] == 2025].duplicated().any()


# ------------------------------------------------------------------- Nowcast

def test_nowcast():
    df = carregar_focos()
    cobertura = cobertura_base(df)
    focos = focos_do_municipio(df, "Pará", "SÃO FÉLIX DO XINGU")
    n = nowcast_territorio(focos, "SÃO FÉLIX DO XINGU", date(2024, 12, 31), cobertura[0])
    assert n.anos_comparados == [2023]
    assert len(n.serie) == 30 and n.serie["data"].iloc[-1] == date(2024, 12, 31)
    est = estatisticas_territorio(focos, "SÃO FÉLIX DO XINGU", 2023, 2024, cobertura)
    i = n.indicadores
    assert i["acumulado_ano"] == est.mensal.loc[2024, "Total"]          # mesmos focos (polígono)
    assert i["media_acumulado"] == est.mensal.loc[2023, "Total"]
    assert i["ultimos_30"] == int(est.diario.loc["12/2024", "Total"]) - int(est.diario.loc["12/2024", 1])
    assert n.serie["media"].tolist() == [est.diario.loc["12/2023", d.day] for d in n.serie["data"]]
    assert i["posicao_acumulado"] == 1 and i["anos_ranking"] == 2      # 2024 > 2023
    assert (n.recentes(7)["dias_atras"] < 7).all()
    # P20: média da janela de 7 dias (o dia ±3) — 15/12/2024 compara com 12 a 18/12/2023
    dia = n.serie[n.serie["data"] == date(2024, 12, 15)].iloc[0]
    janela = [est.diario.loc["12/2023", d] for d in range(12, 19)]
    assert dia["media_janela"] == pytest.approx(sum(janela) / 7)
    assert set(n.focos["idade"]) <= {"Último dia", "1–2 dias antes", "3–6 dias antes", "7–29 dias antes"}


def test_dia_sem_focos_do_satelite_de_referencia(bases, monkeypatch, tmp_path):
    vazio = tmp_path / "vazio.csv"
    tabela = pd.read_csv(INPE / "focos_diario_br_20250201.csv")
    tabela[tabela["satelite"] != "AQUA_M-T"].to_csv(vazio, index=False)        # só outros satélites
    monkeypatch.setattr(atualizacao, "municipios_brasil", pytest.fail)          # nem lê os limites
    servidor = ServidorFalso(["focos_diario_br_20250101.csv"], [])
    servidor.baixar = lambda url, destino: shutil.copy(vazio, destino)
    antes = pq.read_table(bases / NOME_FOCOS_PARQUET).num_rows
    resultado = atualizar_base(bases, agora=datetime(2025, 1, 1, 15, tzinfo=timezone.utc),
                               listar_fn=servidor.listar, baixar_fn=servidor.baixar, progresso=lambda _: None)
    assert resultado.situacao == "atualizada" and resultado.focos_novos == 0
    assert resultado.provisorios == [date(2025, 1, 1)]
    assert pq.read_table(bases / NOME_FOCOS_PARQUET).num_rows == antes


# ------------------------------------------------------- Segundo plano

class Relogio:
    def __init__(self, agora):
        self.agora = agora

    def __call__(self):
        return self.agora


def test_atualizador_agenda_a_proxima_busca(bases):
    """Nowcast ligado: próxima busca em 4 h; falha: nova tentativa em 30 min; desligado: nada agendado."""
    from core.atualizacao import CICLO_NOWCAST_H, REPETIR_PENDENTE_MIN, AtualizadorFocos, ResultadoAtualizacao
    relogio = Relogio(datetime(2026, 10, 22, 10, 0))
    respostas = []
    atualizador = AtualizadorFocos(bases, atualizar_fn=lambda *a, **k: respostas.pop(0), agora_fn=relogio)

    respostas.append(ResultadoAtualizacao("em_dia", "ok"))
    atualizador.executar_uma_vez()
    assert atualizador.instantaneo()["proxima"] is None                       # nowcast desligado

    atualizador.definir_nowcast(True)
    assert atualizacao.nowcast_ligado(bases)
    respostas.append(ResultadoAtualizacao("atualizada", "ok"))
    atualizador.executar_uma_vez()
    assert atualizador.instantaneo()["proxima"] == relogio.agora + timedelta(hours=CICLO_NOWCAST_H)

    respostas.append(ResultadoAtualizacao("sem_conexao", "sem internet"))
    atualizador.executar_uma_vez()
    estado = atualizador.instantaneo()
    assert estado["proxima"] == relogio.agora + timedelta(minutes=REPETIR_PENDENTE_MIN)
    assert estado["ultimo_resultado"].situacao == "sem_conexao" and not estado["em_execucao"]

    atualizador.definir_nowcast(False)
    assert not atualizacao.nowcast_ligado(bases)


def test_atualizador_nunca_morre(bases):
    from core.atualizacao import AtualizadorFocos

    def explode(*a, **k):
        raise RuntimeError("falha inesperada")
    atualizador = AtualizadorFocos(bases, atualizar_fn=explode)
    resultado = atualizador.executar_uma_vez()
    assert resultado.situacao == "erro" and "falha inesperada" in resultado.mensagem


def test_versao_da_base_muda_ao_gravar(bases):
    from core.atualizacao import versao_da_base
    antes = versao_da_base(bases)
    primeira_busca(bases)
    assert versao_da_base(bases) != antes
