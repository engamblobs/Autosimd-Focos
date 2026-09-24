import pandas as pd
import requests

URL = "https://panorama.sipam.gov.br/painel-do-fogo/api/v1/eventos"

# Definindo parâmetros de busca para o histórico
params = {
    "uf": "PA",  # Filtra direto no Pará
    "dt_inicio": "2024-01-01",  # Ajuste o período desejado
    "dt_fim": "2026-08-17",
    "limit": 10000,  # Aumenta o limite de retorno por consulta
}

headers = {"accept": "application/json"}

print("🔄 Solicitando histórico de dados da API...")
response = requests.get(URL, headers=headers, params=params)

if response.status_code == 200:
    dados = response.json()

    # Se a API retornar uma estrutura paginada (ex: {"features": [...]})
    registros = (
        dados["features"]
        if isinstance(dados, dict) and "features" in dados
        else dados
    )
    df = pd.DataFrame(registros)

    print(
        f"✅ Total de eventos históricos recuperados: {len(df)} registros\n"
    )

    # --- ESTATÍSTICAS GERAIS DA BASE ---
    print("=" * 65)
    print(" 📊 ESTATÍSTICAS MACRO DA BASE DE DADOS (PARÁ) ")
    print("=" * 65)

    # 1. Distribuição por Status do Evento
    print("\n1. Distribuição por Status do Evento:")
    if "status_evento" in df.columns:
        print(df["status_evento"].value_counts().to_string())

    # 2. Métricas de Área e Persistência
    print("\n2. Métricas de Impacto:")
    area_total = (
        df["area_total_evento"].sum() if "area_total_evento" in df.columns else 0
    )
    area_media = (
        df["area_total_evento"].mean()
        if "area_total_evento" in df.columns
        else 0
    )
    persistencia_max = (
        df["persistencia_dias"].max() if "persistencia_dias" in df.columns else 0
    )
    persistencia_media = (
        df["persistencia_dias"].mean() if "persistencia_dias" in df.columns else 0
    )

    print(f"• Área Total Queimada/Afetada: {area_total:,.2f} hectares")
    print(f"• Área Média por Evento: {area_media:,.2f} hectares")
    print(f"• Duração Média do Fogo: {persistencia_media:.1f} dias")
    print(f"• Maior Duração de Evento: {persistencia_max} dias")

    # 3. Evolução Temporal (Ano/Mês)
    if "dt_minima" in df.columns:
        df["dt_minima"] = pd.to_datetime(df["dt_minima"], errors="coerce")
        df["ano_mes"] = df["dt_minima"].dt.to_period("M")

        print("\n3. Evolução Histórica (Top 10 Meses com Mais Ocorrências):")
        historico_mensal = (
            df.groupby("ano_mes")
            .agg(qtd_eventos=("id_evento", "count"), area_ha=("area_total_evento", "sum"))
            .sort_values(by="qtd_eventos", ascending=False)
        )
        print(historico_mensal.head(10).to_string())

else:
    print(
        f"❌ Erro ao consultar a API: {response.status_code} - {response.text}"
    )