# -*- coding: utf-8 -*-
"""Atualização da base de focos com os arquivos do INPE (docs/03 §5).

Fontes (Programa Queimadas/INPE, focos do Brasil, todos os satélites):
- diário: ``focos_diario_br_AAAAMMDD.csv`` — só os últimos ~30 dias ficam no servidor;
- mensal: ``focos_mensal_br_AAAAMM.csv`` — todos os meses (o do mês corrente é parcial).

Para cada dia que falta na base: arquivo diário se existir, senão o mensal do mês. Do arquivo
fica só o satélite de referência (AQUA_M-T, o mesmo da base); município, UC e TI são atribuídos por
ponto-no-polígono, com as mesmas regras da base consolidada. A base é regravada de uma vez
(arquivo temporário + troca), com cópia da versão anterior.

Um dia baixado antes de terminar (mais ``MARGEM_DIA_FECHADO`` depois da meia-noite UTC) fica
**provisório** e é baixado de novo na próxima busca. Quando o mês termina e o INPE publica o arquivo
mensal, os dias que vieram dos arquivos diários são trocados pelo mensal consolidado (P17). O
controle fica em ``atualizacao_inpe.json``.
"""

import calendar

import json
import os
import re
import shutil
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from core.config import (
    APP_NOME, APP_VERSAO, BASES_DIR, NOME_FOCOS_PARQUET, VALORES_VAZIOS, caminho_ti, caminho_uc, pasta_municipios,
)
from core.territorios import carregar_areas_protegidas, indice_por_poligono, municipios_brasil

URL_DIARIO = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/"
URL_MENSAL = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/mensal/Brasil/"
SATELITE_REFERENCIA = "AQUA_M-T"
ARQUIVO_CONTROLE = "atualizacao_inpe.json"
ARQUIVO_ANTERIOR = "bdqueimadas_consolidado.anterior.parquet"   # cópia da base antes da última atualização
ARQUIVO_TRAVA = ".atualizando.lock"
ARQUIVO_NOWCAST = "nowcast.json"            # liga/desliga do nowcast (separado do controle, que a thread regrava)
CICLO_NOWCAST_H = 4                         # com o nowcast ligado, busca a cada 4 h
REPETIR_PENDENTE_MIN = 30                   # sem internet / falha: tenta de novo em 30 min
MARGEM_DIA_FECHADO = timedelta(hours=30)   # dia d fechado se baixado depois de d 00:00 UTC + 30 h
TEMPO_REDE_S = 120
TRAVA_VENCIDA_S = 3600
PADRAO_DIARIO = re.compile(r"focos_diario_br_(\d{8})\.csv")
PADRAO_MENSAL = re.compile(r"focos_mensal_br_(\d{6})\.csv")
COLUNAS_CSV = ["lat", "lon", "data_hora_gmt", "satelite"]
NONE = "NONE"


@dataclass
class Fonte:
    tipo: str                    # "diario" | "mensal"
    nome: str                    # nome do arquivo
    origem: str                  # URL ou caminho local
    dias: list[date]             # dias que serão tirados deste arquivo
    local: bool = False


@dataclass
class ResultadoAtualizacao:
    situacao: str                # atualizada | em_dia | sem_conexao | ocupada | erro
    mensagem: str
    focos_novos: int = 0
    dias: list[date] = field(default_factory=list)
    ultimo_dia: date | None = None
    provisorios: list[date] = field(default_factory=list)
    fontes: list[str] = field(default_factory=list)
    nao_publicados: list[date] = field(default_factory=list)

    @property
    def mudou_a_base(self) -> bool:
        return self.situacao == "atualizada"


class SemConexao(Exception):
    pass


# ---------------------------------------------------------------- Controle

def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def ler_controle(bases_dir: Path | None = None) -> dict:
    caminho = Path(bases_dir or BASES_DIR) / ARQUIVO_CONTROLE
    if not caminho.exists():
        return {}
    return json.loads(caminho.read_text(encoding="utf-8"))


def gravar_controle(controle: dict, bases_dir: Path | None = None):
    caminho = Path(bases_dir or BASES_DIR) / ARQUIVO_CONTROLE
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(controle, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, caminho)


def ultimo_dia_da_base(caminho_parquet: Path) -> date:
    datas = pq.read_table(caminho_parquet, columns=["data"]).column("data")
    return date.fromisoformat(pc.max(datas).as_py())


def situacao_da_base(bases_dir: Path | None = None) -> dict:
    """Último dia, dias provisórios e última busca (para a tela)."""
    bases_dir = Path(bases_dir or BASES_DIR)
    controle = ler_controle(bases_dir)
    parquet = bases_dir / NOME_FOCOS_PARQUET
    ultimo = controle.get("ultimo_dia") or (ultimo_dia_da_base(parquet).isoformat() if parquet.exists() else None)
    return {
        "ultimo_dia": date.fromisoformat(ultimo) if ultimo else None,
        "provisorios": [date.fromisoformat(d) for d in controle.get("provisorios", [])],
        "ultima_busca": datetime.fromisoformat(controle["ultima_busca"]) if controle.get("ultima_busca") else None,
        "historico": controle.get("historico", []),
    }


# ---------------------------------------------------------- Servidor do INPE

def abrir_url(url: str, timeout: int = TEMPO_REDE_S):
    pedido = urllib.request.Request(url, headers={"User-Agent": f"{APP_NOME}/{APP_VERSAO}"})
    return urllib.request.urlopen(pedido, timeout=timeout)


def listar(url: str) -> list[str]:
    """Nomes dos .csv da página de índice do servidor."""
    try:
        with abrir_url(url) as resposta:
            html = resposta.read().decode("utf-8", "replace")
    except OSError as erro:
        raise SemConexao(f"Não foi possível acessar {url}: {erro}") from erro
    return sorted(set(re.findall(r'href="(focos_[a-z]+_br_\d+\.csv)"', html)))


def baixar(url: str, destino: Path):
    """Baixa para ``destino`` (arquivo temporário até terminar)."""
    temporario = destino.with_name(destino.name + ".parcial")
    try:
        with abrir_url(url) as resposta, open(temporario, "wb") as arquivo:
            shutil.copyfileobj(resposta, arquivo, length=1 << 20)
    except OSError as erro:
        temporario.unlink(missing_ok=True)
        raise SemConexao(f"Falha ao baixar {url}: {erro}") from erro
    os.replace(temporario, destino)


def disponiveis(nomes: list[str]) -> tuple[dict[date, str], dict[tuple[int, int], str]]:
    """(dia → arquivo diário, (ano, mês) → arquivo mensal)."""
    diarios, mensais = {}, {}
    for nome in nomes:
        if m := PADRAO_DIARIO.fullmatch(nome):
            diarios[datetime.strptime(m.group(1), "%Y%m%d").date()] = nome
        elif m := PADRAO_MENSAL.fullmatch(nome):
            mensais[(int(m.group(1)[:4]), int(m.group(1)[4:]))] = nome
    return diarios, mensais


# ------------------------------------------------------------------ Plano

def dias_faltantes(ultimo_dia: date, provisorios: list[date], hoje: date) -> list[date]:
    """Dias depois do último da base até hoje (UTC), mais os provisórios."""
    novos = [ultimo_dia + timedelta(days=i) for i in range(1, (hoje - ultimo_dia).days + 1)]
    return sorted(set(novos) | set(provisorios))


def planejar(faltantes: list[date], diarios: dict, mensais: dict, locais: dict | None = None
             ) -> tuple[list[Fonte], list[date]]:
    """Arquivo de cada dia: local > diário do servidor > mensal do servidor. Devolve (fontes, sem fonte)."""
    locais_diarios, locais_mensais = locais or ({}, {})
    por_arquivo: dict[tuple, Fonte] = {}
    sem_fonte = []
    for dia in faltantes:
        mes = (dia.year, dia.month)
        if dia in locais_diarios:
            chave = ("diario", locais_diarios[dia], True)
        elif mes in locais_mensais:
            chave = ("mensal", locais_mensais[mes], True)
        elif dia in diarios:
            chave = ("diario", URL_DIARIO + diarios[dia], False)
        elif mes in mensais:
            chave = ("mensal", URL_MENSAL + mensais[mes], False)
        else:
            sem_fonte.append(dia)
            continue
        tipo, origem, local = chave
        if chave not in por_arquivo:
            por_arquivo[chave] = Fonte(tipo, Path(origem).name if local else origem.rsplit("/", 1)[-1],
                                       str(origem), [], local)
        por_arquivo[chave].dias.append(dia)
    return list(por_arquivo.values()), sem_fonte


def arquivos_locais(pasta: Path | None) -> tuple[dict[date, Path], dict[tuple[int, int], Path]]:
    if not pasta:
        return {}, {}
    arquivos = {a.name: a for a in Path(pasta).glob("focos_*_br_*.csv")}
    diarios, mensais = disponiveis(list(arquivos))
    return ({d: arquivos[n] for d, n in diarios.items()}, {m: arquivos[n] for m, n in mensais.items()})


# --------------------------------------------------------------- Conversão

def ler_csv_inpe(caminho: Path, dias: list[date]) -> pd.DataFrame:
    """Focos do satélite de referência nos ``dias`` pedidos (lon, lat, data)."""
    bruto = pd.read_csv(caminho, usecols=COLUNAS_CSV, dtype={"satelite": str, "data_hora_gmt": str})
    faltando = set(COLUNAS_CSV) - set(bruto.columns)
    if faltando:
        raise ValueError(f"{caminho.name}: colunas ausentes {sorted(faltando)} — formato do INPE mudou?")
    bruto = bruto[bruto["satelite"].str.strip() == SATELITE_REFERENCIA]
    bruto = bruto.assign(data=bruto["data_hora_gmt"].str.strip().str[:10])
    bruto = bruto[bruto["data"].isin({d.isoformat() for d in dias})]
    return pd.DataFrame({"lon": bruto["lon"].astype(float).to_numpy(), "lat": bruto["lat"].astype(float).to_numpy(),
                         "data": bruto["data"].to_numpy()})


def no_formato_da_base(focos: pd.DataFrame, municipios=None, areas=None) -> pd.DataFrame:
    """Acrescenta ano, mês, município (IBGE), UF, UC e TI por ponto-no-polígono (docs/03 §5)."""
    nomes, geometrias = municipios if municipios is not None else municipios_brasil()
    areas = areas if areas is not None else carregar_areas_protegidas(caminho_uc(), caminho_ti())
    lon, lat = focos["lon"].to_numpy(), focos["lat"].to_numpy()
    i_mun = indice_por_poligono(lon, lat, geometrias)
    tabela_mun = np.array(nomes + [(NONE, NONE, NONE)], dtype=object)
    saida = pd.DataFrame({
        "lon": lon, "lat": lat,
        "ano": pd.to_numeric(focos["data"].str[:4]).astype("int32").to_numpy(),
        "mes": pd.to_numeric(focos["data"].str[5:7]).astype("int32").to_numpy(),
        "data": focos["data"].to_numpy(),
        "NM_MUN": [t[0] for t in tabela_mun[i_mun]],
        "NM_UF": [t[1] for t in tabela_mun[i_mun]],
        "SIGLA_UF": [t[2] for t in tabela_mun[i_mun]],
    })
    for tipo in ("UC", "TI"):
        do_tipo = [a for a in areas if a["tipo"] == tipo]
        rotulos = np.array([a["nome"].upper() for a in do_tipo] + [NONE], dtype=object)
        saida[tipo] = rotulos[indice_por_poligono(lon, lat, [a["geom"] for a in do_tipo], menor_vence=True)]
    for coluna in ("NM_MUN", "NM_UF", "SIGLA_UF"):
        saida.loc[saida[coluna].isin(VALORES_VAZIOS), coluna] = NONE
    return saida


def incorporar(caminho_parquet: Path, novos: pd.DataFrame, dias: list[date]) -> int:
    """Troca os focos dos ``dias`` na base pelos ``novos``; grava a base anterior ao lado. Devolve o total."""
    caminho_parquet = Path(caminho_parquet)
    base = pq.read_table(caminho_parquet)
    manter = pc.invert(pc.is_in(base.column("data"), value_set=pa.array([d.isoformat() for d in dias])))
    base = base.filter(manter)
    novos = pa.Table.from_pandas(novos[base.schema.names], schema=base.schema, preserve_index=False)
    final = pa.concat_tables([base, novos])
    temporario = caminho_parquet.with_name(caminho_parquet.name + ".novo")
    pq.write_table(final, temporario, compression="snappy")
    shutil.copy2(caminho_parquet, caminho_parquet.with_name(ARQUIVO_ANTERIOR))
    os.replace(temporario, caminho_parquet)
    return final.num_rows


# ------------------------------------------------------------------ Trava

def _travar(bases_dir: Path) -> bool:
    trava = bases_dir / ARQUIVO_TRAVA
    if trava.exists() and time.time() - trava.stat().st_mtime > TRAVA_VENCIDA_S:
        trava.unlink(missing_ok=True)            # sobra de uma atualização interrompida
    try:
        os.close(os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False


# -------------------------------------------------------------- Principal

def atualizar_base(bases_dir: Path | None = None, pasta_local: Path | None = None, online: bool = True,
                   agora: datetime | None = None, listar_fn=None, baixar_fn=None, progresso=print
                   ) -> ResultadoAtualizacao:
    """Busca os dias que faltam (e os provisórios), incorpora à base e registra o controle.

    ``pasta_local`` = arquivos ``focos_*_br_*.csv`` já baixados (usados antes do servidor);
    ``online=False`` usa só a pasta local. ``listar_fn``/``baixar_fn`` existem para os testes.
    """
    bases_dir = Path(bases_dir or BASES_DIR)
    agora = agora or agora_utc()
    parquet = bases_dir / NOME_FOCOS_PARQUET
    if not parquet.exists():
        return ResultadoAtualizacao("erro", f"Base de focos não encontrada: {parquet}")
    if not _travar(bases_dir):
        return ResultadoAtualizacao("ocupada", "Outra atualização da base já está em andamento.")
    try:
        return _atualizar(bases_dir, parquet, pasta_local, online, agora, listar_fn or listar, baixar_fn or baixar,
                          progresso)
    except (ValueError, KeyError, pd.errors.ParserError) as erro:   # arquivo do INPE em formato inesperado
        return ResultadoAtualizacao("erro", f"Atualização recusada, a base não foi alterada: {erro}")
    finally:
        (bases_dir / ARQUIVO_TRAVA).unlink(missing_ok=True)


def dias_de_arquivos_diarios(controle: dict) -> set[date]:
    """Dias da base que vieram de arquivos diários e ainda não foram trocados pelo mensal."""
    if "dias_diarios" in controle:
        return {date.fromisoformat(d) for d in controle["dias_diarios"]}
    dias = set()                                 # controle antigo: reconstrói pelo histórico
    for registro in controle.get("historico", []):
        for nome in registro.get("arquivos", []):
            if m := PADRAO_DIARIO.fullmatch(nome):
                dias.add(datetime.strptime(m.group(1), "%Y%m%d").date())
    return dias


def meses_fechados(dias: set[date], agora: datetime) -> dict[tuple[int, int], list[date]]:
    """(ano, mês) já terminados (com a margem) → dias que vieram de arquivos diários."""
    meses: dict[tuple[int, int], list[date]] = {}
    for dia in sorted(dias):
        ultimo = date(dia.year, dia.month, calendar.monthrange(dia.year, dia.month)[1])
        if agora >= datetime(ultimo.year, ultimo.month, ultimo.day, tzinfo=timezone.utc) + MARGEM_DIA_FECHADO:
            meses.setdefault((dia.year, dia.month), []).append(dia)
    return meses


def _atualizar(bases_dir, parquet, pasta_local, online, agora, listar_fn, baixar_fn, progresso):
    controle = ler_controle(bases_dir)
    ultimo = date.fromisoformat(controle["ultimo_dia"]) if controle.get("ultimo_dia") else ultimo_dia_da_base(parquet)
    provisorios = [date.fromisoformat(d) for d in controle.get("provisorios", [])]
    faltantes = dias_faltantes(ultimo, provisorios, agora.date())
    diarios_na_base = dias_de_arquivos_diarios(controle)
    a_consolidar = meses_fechados(diarios_na_base, agora)
    if online:                                   # importar só arquivos locais não conta como busca no INPE
        controle["ultima_busca"] = agora.isoformat(timespec="seconds")

    diarios, mensais, erro_rede = {}, {}, None
    if online and (faltantes or a_consolidar):
        try:
            if faltantes:
                diarios, _ = disponiveis(listar_fn(URL_DIARIO))
            if a_consolidar or min(faltantes) < min(diarios, default=agora.date()):   # mensal necessário
                _, mensais = disponiveis(listar_fn(URL_MENSAL))
        except SemConexao as erro:
            erro_rede = erro
    locais = arquivos_locais(pasta_local)
    # Meses fechados com arquivo mensal publicado (no servidor ou na pasta local): o mês inteiro sai dele
    consolidar = {mes: dias for mes, dias in a_consolidar.items() if mes in mensais or mes in locais[1]}
    fora_dos_consolidados = [d for d in faltantes if (d.year, d.month) not in consolidar]
    fontes, sem_fonte = planejar(fora_dos_consolidados, diarios, mensais, locais)
    for mes, dias in consolidar.items():
        dias = sorted(set(dias) | {d for d in faltantes if (d.year, d.month) == mes})
        if mes in locais[1]:
            fontes.append(Fonte("mensal", locais[1][mes].name, str(locais[1][mes]), dias, True))
        else:
            fontes.append(Fonte("mensal", mensais[mes], URL_MENSAL + mensais[mes], dias))

    if not faltantes and not fontes:
        gravar_controle(controle, bases_dir)
        return ResultadoAtualizacao("em_dia", f"Base em dia (até {ultimo:%d/%m/%Y}).", ultimo_dia=ultimo)
    if not fontes:
        gravar_controle(controle, bases_dir)
        if erro_rede:
            return ResultadoAtualizacao("sem_conexao", f"Sem conexão com o servidor do INPE — usando a base até "
                                        f"{ultimo:%d/%m/%Y}. ({erro_rede})", ultimo_dia=ultimo,
                                        provisorios=provisorios)
        return ResultadoAtualizacao("em_dia", f"Nenhum arquivo novo publicado pelo INPE (base até {ultimo:%d/%m/%Y}).",
                                    ultimo_dia=ultimo, provisorios=provisorios, nao_publicados=sem_fonte)

    pasta_baixados = bases_dir / ".baixando"
    pasta_baixados.mkdir(exist_ok=True)
    partes, dias_lidos, novos_provisorios, nomes = [], [], set(), []
    try:
        for fonte in fontes:
            progresso(f"Lendo {fonte.nome} ({len(fonte.dias)} dia(s))...")
            if fonte.local:
                arquivo, baixado_em = Path(fonte.origem), datetime.fromtimestamp(
                    Path(fonte.origem).stat().st_mtime, timezone.utc)
            else:
                arquivo, baixado_em = pasta_baixados / fonte.nome, agora
                try:
                    baixar_fn(fonte.origem, arquivo)
                except SemConexao as erro:
                    erro_rede = erro
                    continue                             # os dias deste arquivo ficam para a próxima busca
            partes.append(ler_csv_inpe(arquivo, fonte.dias))
            dias_lidos += fonte.dias
            if fonte.tipo == "diario":
                diarios_na_base |= set(fonte.dias)
            else:
                diarios_na_base -= set(fonte.dias)
            nomes.append(fonte.nome)
            novos_provisorios |= {d for d in fonte.dias
                                  if baixado_em < datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
                                  + MARGEM_DIA_FECHADO}
            if not fonte.local:
                arquivo.unlink(missing_ok=True)
    finally:
        shutil.rmtree(pasta_baixados, ignore_errors=True)

    if not dias_lidos:
        gravar_controle(controle, bases_dir)
        return ResultadoAtualizacao("sem_conexao", f"Não foi possível baixar os arquivos do INPE — usando a base até "
                                    f"{ultimo:%d/%m/%Y}. ({erro_rede})", ultimo_dia=ultimo, provisorios=provisorios)

    lidos_csv = pd.concat(partes, ignore_index=True)
    if lidos_csv.empty:                          # comum no início do dia: nada a cruzar com os limites
        novos = pd.DataFrame(columns=pq.read_schema(parquet).names)
    else:
        progresso("Atribuindo município, UC e TI aos focos novos...")
        novos = no_formato_da_base(lidos_csv, municipios_brasil(pasta_municipios(bases_dir)),
                                   carregar_areas_protegidas(caminho_uc(bases_dir), caminho_ti(bases_dir)))
    progresso("Gravando a base de focos...")
    total = incorporar(parquet, novos, dias_lidos)

    lidos = set(dias_lidos)
    ultimo_novo = max([ultimo, *dias_lidos])
    restantes = sorted((set(provisorios) - lidos) | novos_provisorios
                       | {d for d in faltantes if d not in lidos and d < ultimo_novo})   # buracos para a próxima
    controle.update({
        "ultimo_dia": ultimo_novo.isoformat(),
        "provisorios": [d.isoformat() for d in restantes],
        "dias_diarios": [d.isoformat() for d in sorted(diarios_na_base)],
    })
    controle.setdefault("historico", []).append({
        "em": agora.isoformat(timespec="seconds"), "arquivos": nomes, "dias": len(lidos),
        "de": min(lidos).isoformat(), "ate": max(lidos).isoformat(), "focos_novos": len(novos), "total": total,
    })
    controle["historico"] = controle["historico"][-50:]
    gravar_controle(controle, bases_dir)
    mensagem = (f"Base atualizada: {len(novos)} focos de {min(lidos):%d/%m/%Y} a {max(lidos):%d/%m/%Y} "
                f"({len(nomes)} arquivo(s) do INPE). Dados até {ultimo_novo:%d/%m/%Y}.")
    if erro_rede:
        mensagem += f" Alguns arquivos não foram baixados e ficam para a próxima busca ({erro_rede})."
    return ResultadoAtualizacao("atualizada", mensagem, len(novos), sorted(lidos), ultimo_novo, restantes, nomes,
                                sem_fonte)


# ----------------------------------------------------------- Segundo plano

def versao_da_base(bases_dir: Path | None = None) -> int:
    """Muda sempre que a base de focos é regravada (a tela recarrega os dados quando muda)."""
    caminho = Path(bases_dir or BASES_DIR) / NOME_FOCOS_PARQUET
    return caminho.stat().st_mtime_ns if caminho.exists() else 0


def nowcast_ligado(bases_dir: Path | None = None) -> bool:
    caminho = Path(bases_dir or BASES_DIR) / ARQUIVO_NOWCAST
    try:
        return bool(json.loads(caminho.read_text(encoding="utf-8")).get("ligado"))
    except (OSError, ValueError):
        return False


def gravar_nowcast(ligado: bool, bases_dir: Path | None = None):
    caminho = Path(bases_dir or BASES_DIR) / ARQUIVO_NOWCAST
    caminho.write_text(json.dumps({"ligado": bool(ligado)}), encoding="utf-8")


class AtualizadorFocos:
    """Busca focos novos no INPE numa thread, sem travar o programa (modelo do AutoSIMD-HIDRO).

    - ao abrir o programa: uma busca em segundo plano (a tela já abre com a base local);
    - nowcast ligado: busca na hora e depois a cada ``CICLO_NOWCAST_H`` horas;
    - falha (sem internet, servidor fora do ar): tenta de novo em ``REPETIR_PENDENTE_MIN`` minutos.
    Uma instância por processo do Streamlit (``app.obter_atualizador``), compartilhada pelas sessões.
    """

    def __init__(self, bases_dir: Path | None = None, atualizar_fn=None, agora_fn=datetime.now):
        self.bases_dir = Path(bases_dir or BASES_DIR)
        self._atualizar_fn = atualizar_fn or atualizar_base
        self._agora = agora_fn
        self._trava = threading.Lock()
        self._pedido = threading.Event()
        self._thread = None
        self.estado = {"em_execucao": False, "etapa": "", "inicio": None, "proxima": None, "gatilho": None,
                       "ultimo_resultado": None, "ultimo_fim": None}

    @property
    def nowcast(self) -> bool:
        return nowcast_ligado(self.bases_dir)

    def definir_nowcast(self, ligado: bool):
        """Ligar = buscar agora e depois a cada 4 h; desligar = só a busca de quando o programa abre."""
        gravar_nowcast(ligado, self.bases_dir)
        if ligado:
            self.solicitar("nowcast")
        else:
            with self._trava:
                resultado = self.estado["ultimo_resultado"]
                if resultado is None or resultado.situacao in ("atualizada", "em_dia"):
                    self.estado["proxima"] = None

    def iniciar(self, buscar_ao_abrir: bool = True):
        with self._trava:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._laco, name="atualizador-focos", daemon=True)
            self._thread.start()
        if buscar_ao_abrir or self.nowcast:
            self.solicitar("abertura do programa")

    def solicitar(self, gatilho: str):
        with self._trava:
            self.estado["gatilho"] = gatilho
        self._pedido.set()

    def instantaneo(self) -> dict:
        with self._trava:
            return dict(self.estado)

    def _progresso(self, texto: str):
        with self._trava:
            self.estado["etapa"] = texto

    def executar_uma_vez(self):
        """Uma busca completa (usada pela thread; chamada direto nos testes)."""
        with self._trava:
            gatilho = self.estado["gatilho"] or ("nowcast" if self.nowcast else "nova tentativa")
            self.estado.update(em_execucao=True, inicio=self._agora(), etapa="Iniciando", gatilho=gatilho)
        try:
            resultado = self._atualizar_fn(self.bases_dir, progresso=self._progresso)
        except Exception as erro:            # a thread nunca pode morrer
            resultado = ResultadoAtualizacao("erro", f"Erro inesperado na atualização: {erro}")
        agora = self._agora()
        with self._trava:
            self.estado.update(em_execucao=False, etapa="", gatilho=None, ultimo_resultado=resultado,
                               ultimo_fim=agora)
            if resultado.situacao == "ocupada":
                self.estado["proxima"] = agora + timedelta(minutes=1)
            elif resultado.situacao not in ("atualizada", "em_dia"):
                self.estado["proxima"] = agora + timedelta(minutes=REPETIR_PENDENTE_MIN)
            elif self.nowcast:
                self.estado["proxima"] = agora + timedelta(hours=CICLO_NOWCAST_H)
            else:
                self.estado["proxima"] = None
        return resultado

    def _laco(self):
        while True:
            self._pedido.wait(timeout=30)
            pedido = self._pedido.is_set()
            self._pedido.clear()
            with self._trava:
                proxima = self.estado["proxima"]
            if pedido or (proxima is not None and self._agora() >= proxima):
                self.executar_uma_vez()

