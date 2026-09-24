import json
import os
from pathlib import Path
import unicodedata

# 1. Caminho do diretório
DIRETORIO_GEOJSON = Path("/home/lobs/SIG/FOCOS DE CALOR/")
ARQUIVO_SAIDA_PYTHON = Path("dicionario_municipios.py")


def normalizar_texto(texto):
    """Remove acentos, espaços extras e converte para maiúsculas para comparação."""
    if not texto:
        return ""
    nfd = unicodedata.normalize("NFD", str(texto))
    texto_sem_acento = "".join([c for c in nfd if not unicodedata.combining(c)])
    return texto_sem_acento.upper().strip()


# 2. Base de dados das Regiões de Integração do Pará
dados_regioes = {
    "Região Araguaia": [
        "Água Azul do Norte",
        "Bannach",
        "Conceição do Araguaia",
        "Cumaru do Norte",
        "Floresta do Araguaia",
        "Ourilândia do Norte",
        "Pau D'Arco",
        "Redenção",
        "Rio Maria",
        "Santa Maria das Barreiras",
        "Santana do Araguaia",
        "São Felix do Xingu",
        "São Félix do Xingu",
        "Sapucaia",
        "Tucumã",
        "Xinguara",
    ],
    "Região Baixo Amazonas": [
        "Alenquer",
        "Almerim",
        "Almeirim",
        "Belterra",
        "Curuá",
        "Faro",
        "Juruti",
        "Mojuí dos Campos",
        "Monte Alegre",
        "Óbidos",
        "Oriximiná",
        "Prainha",
        "Santarém",
        "Terra Santa",
    ],
    "Região Guamá": [
        "Castanhal",
        "Colares",
        "Curuçá",
        "Igarapé-Açu",
        "Inhangapi",
        "Magalhães Barata",
        "Maracanã",
        "Marapanim",
        "Santo Antônio do Tauá",
        "Santa Maria do Pará",
        "Santa Izabel do Pará",
        "São Caetano de Odivelas",
        "São Domingos do Capim",
        "São Francisco do Pará",
        "São João da Ponta",
        "São Miguel do Guamá",
        "Terra Alta",
        "Vigia",
    ],
    "Região Carajás": [
        "Bom Jesus do Tocantins",
        "Brejo Grande do Araguaia",
        "Canaã dos Carajás",
        "Curionópolis",
        "Eldorado dos Carajás",
        "Marabá",
        "Palestina do Pará",
        "Parauapebas",
        "Piçarra",
        "São Domingos do Araguaia",
        "São Geraldo do Araguaia",
        "São João do Araguaia",
    ],
    "Região Lago Tucuruí": [
        "Breu Branco",
        "Goianésia do Pará",
        "Itupiranga",
        "Jacundá",
        "Nova Ipixuna",
        "Novo Repartimento",
        "Tucuruí",
    ],
    "Região Marajó": [
        "Afuá",
        "Anajás",
        "Bagre",
        "Breves",
        "Cachoeira do Arari",
        "Chaves",
        "Curralinho",
        "Gurupá",
        "Melgaço",
        "Muaná",
        "Ponta de Pedras",
        "Portel",
        "Salvaterra",
        "Santa Cruz do Arari",
        "São Sebastião da Boa Vista",
        "Soure",
    ],
    "Região Guajará": [
        "Ananindeua",
        "Belém",
        "Benevides",
        "Marituba",
        "Santa Bárbara do Pará",
    ],
    "Região Rio Caeté": [
        "Augusto Correa",
        "Augusto Corrêa",
        "Bonito",
        "Bragança",
        "Cachoeira do Piriá",
        "Capanema",
        "Nova Timboteua",
        "Peixe-Boi",
        "Primavera",
        "Quatipuru",
        "Salinópolis",
        "Santa Luzia do Pará",
        "Santarém Novo",
        "São João de Pirabas",
        "Tracuateua",
        "Viseu",
    ],
    "Região Rio Capim": [
        "Abel Figueiredo",
        "Aurora do Pará",
        "Bujaru",
        "Capitão Poço",
        "Concórdia do Pará",
        "Dom Eliseu",
        "Garrafão do Norte",
        "Ipixuna do Pará",
        "Irituia",
        "Mãe do Rio",
        "Nova Esperança do Piriá",
        "Ourém",
        "Paragominas",
        "Rondon do Pará",
        "Tomé-Açu",
        "Ulianópolis",
    ],
    "Região Tapajós": [
        "Aveiro",
        "Itaituba",
        "Jacareacanga",
        "Novo Progresso",
        "Rurópolis",
        "Trairão",
    ],
    "Região Xingu": [
        "Altamira",
        "Anapu",
        "Brasil Novo",
        "Medicilândia",
        "Pacajá",
        "Placas",
        "Porto de Moz",
        "Senador José Porfírio",
        "Uruará",
        "Vitória do Xingu",
    ],
    "Região Tocantins": [
        "Abaetetuba",
        "Acará",
        "Baião",
        "Barcarena",
        "Cametá",
        "Igarapé-Miri",
        "Limoeiro do Ajuru",
        "Mocajuba",
        "Moju",
        "Oeiras do Pará",
        "Tailândia",
    ],
}

# Criando mapa de busca normalizado
mapa_busca = {}
for regiao, municipios in dados_regioes.items():
    for mun in municipios:
        mapa_busca[normalizar_texto(mun)] = regiao


def extrair_municipios_dos_geojsons(diretorio):
    municipios_encontrados = set()

    # Busca por arquivos .geojson e .json
    arquivos = list(diretorio.glob("*.geojson")) + list(diretorio.glob("*.json"))

    print(f"Encontrados {len(arquivos)} arquivos para processar...")

    for arq in arquivos:
        try:
            with open(arq, "r", encoding="utf-8") as f:
                content = json.load(f)

            # Lida com FeatureCollection ou lista direta de Features
            features = (
                content.get("features", content)
                if isinstance(content, dict)
                else content
            )

            for feat in features:
                if isinstance(feat, dict):
                    props = feat.get("properties", {})
                    mun = props.get("Municipio")
                    if mun and isinstance(mun, str):
                        municipios_encontrados.add(mun.strip())

        except Exception as e:
            print(f"Erro ao ler o arquivo {arq.name}: {e}")

    return sorted(municipios_encontrados)


def gerar_codigo_python(municipios_originais, arquivo_saida):
    dict_mapeado = {}
    nao_encontrados = []

    for mun_orig in municipios_originais:
        mun_norm = normalizar_texto(mun_orig)
        regiao = mapa_busca.get(mun_norm)

        if regiao:
            dict_mapeado[mun_orig] = regiao
        else:
            dict_mapeado[mun_orig] = "Não Encontrado"
            nao_encontrados.append(mun_orig)

    # Conteúdo do código Python gerado
    conteudo_script = (
        '# -*- coding: utf-8 -*-\n'
        '"""\n'
        "Dicionario gerado automaticamente contendo a forma exata dos municipios\n"
        "observados nos arquivos GeoJSON e suas respectivas Regioes de Integração.\n"
        '"""\n\n'
        "MAPA_MUNICIPIO_REGIAO = {\n"
    )

    for mun, regiao in dict_mapeado.items():
        conteudo_script += f'    "{mun}": "{regiao}",\n'

    conteudo_script += "}\n"

    # Salva o novo código Python em arquivo
    with open(arquivo_saida, "w", encoding="utf-8") as f:
        f.write(conteudo_script)

    print(f"\n✅ Código Python gerado com sucesso em: {arquivo_saida.resolve()}")
    print(f"Total de municípios distintos registrados: {len(dict_mapeado)}")

    if nao_encontrados:
        print(
            f"\n⚠️ Os seguintes {len(nao_encontrados)} municípios não tiveram correspondência direta:"
        )
        for m in nao_encontrados:
            print(f" - {m}")


if __name__ == "__main__":
    if not DIRETORIO_GEOJSON.exists():
        print(f"Erro: O diretório '{DIRETORIO_GEOJSON}' não foi encontrado.")
    else:
        municipios = extrair_municipios_dos_geojsons(DIRETORIO_GEOJSON)
        gerar_codigo_python(municipios, ARQUIVO_SAIDA_PYTHON)