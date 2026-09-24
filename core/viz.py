"""
===============================================================================
AUTOSIMD-FOCOS - Módulo de Visualização Gráfica Interativa (Plotly)
Sala de Informações e Monitoramento de Desastres (SIMD) / CEDEC-PA
===============================================================================
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Paletas Institucionais SIMD
PALETA_CORES = {
    "primaria": "#D97706",   # Laranja Defesa Civil
    "secundaria": "#1E3A8A", # Azul Escuro Institucional
    "perigo": "#DC2626",     # Vermelho Emergência
    "alerta": "#F59E0B",     # Laranja Alerta
    "atencao": "#EAB308",    # Amarelo Atenção
    "normal": "#10B981",     # Verde Normal
}

PALETA_DENSIDADE = {
    "Baixa": "#9CA3AF",       # Cinza
    "Moderada": "#EAB308",    # Amarelo
    "Alta": "#F97316",        # Laranja
    "Muito Alta": "#DC2626"   # Vermelho
}

PALETA_RECORRENCIA = {
    "Esporádica (≤ 25% dos anos)": "#9CA3AF",
    "Frequente (25% a 50% dos anos)": "#EAB308",
    "Alta Recorrência (50% a 75% dos anos)": "#F97316",
    "Sistemática / Crítica (> 75% dos anos)": "#DC2626"
}


class VisualizadorSIMD:

    @staticmethod
    def _criar_grid_km(df: pd.DataFrame, tam_grid_km: float = 10.0) -> pd.DataFrame:
        """Converte lat/lon em centros de quadrículas regulares configuráveis em km."""
        df_grid = df.copy()
        lat_media = df_grid['Latitude'].mean()

        step_lat = tam_grid_km / 111.0
        step_lon = tam_grid_km / (111.0 * np.cos(np.radians(lat_media)))

        df_grid['lat_grid'] = (np.floor(df_grid['Latitude'] / step_lat) * step_lat + step_lat / 2).round(4)
        df_grid['lon_grid'] = (np.floor(df_grid['Longitude'] / step_lon) * step_lon + step_lon / 2).round(4)
        return df_grid

    @staticmethod
    def plot_serie_historica(df_serie: pd.DataFrame, municipio: str) -> go.Figure:
        """Gera gráfico duplo de barras (Total de Focos) e linha (FRP Médio) por Ano."""
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        fig.add_trace(
            go.Bar(
                x=df_serie['Ano'],
                y=df_serie['total_focos'],
                name="Total de Focos",
                marker_color=PALETA_CORES["primaria"],
                hovertemplate="Ano: %{x}<br>Total de Focos: %{y:,}<extra></extra>"
            ),
            secondary_y=False
        )

        if 'frp_medio' in df_serie.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_serie['Ano'],
                    y=df_serie['frp_medio'],
                    name="FRP Médio (MW)",
                    mode="lines+markers",
                    line=dict(color=PALETA_CORES["secundaria"], width=3),
                    marker=dict(size=8),
                    hovertemplate="Ano: %{x}<br>FRP Médio: %{y:.1f} MW<extra></extra>"
                ),
                secondary_y=True
            )

        fig.update_layout(
            title=f"<b>Evolução Histórica de Focos de Calor — {municipio.upper()}</b>",
            template="plotly_white",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(type='category', title="Ano")
        )

        fig.update_yaxes(title_text="<b>Total de Focos</b>", secondary_y=False)
        fig.update_yaxes(title_text="<b>FRP Médio (MW)</b>", secondary_y=True)

        return fig

    @staticmethod
    def plot_perfil_sazonal(df_sazonal: pd.DataFrame, municipio: str) -> go.Figure:
        """Gera gráfico de barras e linha do perfil mensal de focos."""
        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=df_sazonal['mes_nome'],
                y=df_sazonal['media_focos'],
                name="Média Mensal",
                marker_color=PALETA_CORES["secundaria"],
                opacity=0.85,
                hovertemplate="Mês: %{x}<br>Média Histórica: %{y:.1f}<extra></extra>"
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df_sazonal['mes_nome'],
                y=df_sazonal['max_focos'],
                name="Máximo Histórico",
                mode="lines+markers",
                line=dict(color=PALETA_CORES["perigo"], width=2, dash="dash"),
                marker=dict(size=6),
                hovertemplate="Mês: %{x}<br>Máximo Registrado: %{y:,}<extra></extra>"
            )
        )

        fig.update_layout(
            title=f"<b>Perfil Sazonal Mensal de Focos — {municipio.upper()}</b>",
            xaxis_title="Mês do Ano",
            yaxis_title="Quantidade de Focos",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        return fig

    @staticmethod
    def plot_anomalia_zscore(df_zscore: pd.DataFrame, municipio: str, ano: int = 2026) -> go.Figure:
        """Gera gráfico de anomalia Z-Score com diagnóstico operacional."""
        mapa_cores = {
            "EMERGÊNCIA (Z >= 2.0)": PALETA_CORES["perigo"],
            "ALERTA (1.5 <= Z < 2.0)": PALETA_CORES["alerta"],
            "ATENÇÃO (1.0 <= Z < 1.5)": PALETA_CORES["atencao"],
            "NORMAL (Z < 1.0)": PALETA_CORES["normal"]
        }

        df_zscore['cor'] = df_zscore['nivel_alerta'].map(lambda x: mapa_cores.get(x, PALETA_CORES["normal"]))

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=df_zscore['Mes'],
                y=df_zscore['focos_ano_alvo'],
                marker_color=df_zscore['cor'],
                name=f"Focos em {ano}",
                text=df_zscore['z_score'].apply(lambda z: f"Z: {z:.1f}"),
                textposition='auto',
                hovertemplate="Mês: %{x}<br>Focos: %{y}<br>Média Histórica: %{customdata[0]:.1f}<br>Nível: %{customdata[1]}<extra></extra>",
                customdata=df_zscore[['media_hist', 'nivel_alerta']]
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df_zscore['Mes'],
                y=df_zscore['media_hist'],
                name="Média Histórica",
                mode="lines+markers",
                line=dict(color="#475569", width=2, dash="dot")
            )
        )

        fig.update_layout(
            title=f"<b>Diagnóstico de Anomalias Z-Score ({ano}) — {municipio.upper()}</b>",
            xaxis=dict(
                title="Mês",
                tickmode='array',
                tickvals=list(range(1, 13)),
                ticktext=['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
            ),
            yaxis_title="Quantidade de Focos",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        return fig

    @staticmethod
    def plot_mapa_densidade(
        df_muni: pd.DataFrame,
        municipio: str,
        tam_grid_km: float = 10.0,
        **kwargs
    ) -> go.Figure:
        """Gera mapa de densidade em quadrículas configuráveis por Ano."""
        df_valid = df_muni.dropna(subset=['Latitude', 'Longitude']).copy()

        if df_valid.empty:
            fig = go.Figure()
            fig.add_annotation(text="Sem coordenadas válidas para gerar o mapa.", showarrow=False)
            return fig

        df_valid['Ano'] = df_valid['Ano'].astype(int)
        df_grid = VisualizadorSIMD._criar_grid_km(df_valid, tam_grid_km)

        grid = (
            df_grid.groupby(['Ano', 'lat_grid', 'lon_grid'])
            .size()
            .reset_index(name='focos_celula')
        )

        grid['rank_pct'] = grid.groupby('Ano')['focos_celula'].rank(method='first', pct=True)

        condicoes = [
            grid['rank_pct'] <= 0.25,
            (grid['rank_pct'] > 0.25) & (grid['rank_pct'] <= 0.50),
            (grid['rank_pct'] > 0.50) & (grid['rank_pct'] <= 0.75),
            grid['rank_pct'] > 0.75
        ]
        categorias = ['Baixa', 'Moderada', 'Alta', 'Muito Alta']

        grid['Densidade'] = np.select(condicoes, categorias, default='Baixa')
        grid = grid.sort_values(by='Ano')

        lat_centro = grid['lat_grid'].mean()
        lon_centro = grid['lon_grid'].mean()

        fig = px.scatter_mapbox(
            grid,
            lat='lat_grid',
            lon='lon_grid',
            size='focos_celula',
            color='Densidade',
            category_orders={'Densidade': ['Baixa', 'Moderada', 'Alta', 'Muito Alta']},
            color_discrete_map=PALETA_DENSIDADE,
            animation_frame='Ano',
            size_max=20,
            zoom=8,
            center=dict(lat=lat_centro, lon=lon_centro),
            mapbox_style='open-street-map',
            title=f"<b>Densidade de Focos em Quadrículas de {tam_grid_km:g}km × {tam_grid_km:g}km — {municipio.upper()}</b>",
            hover_data={'lat_grid': False, 'lon_grid': False, 'focos_celula': True, 'rank_pct': False},
            labels={'focos_celula': 'Focos na Quadrícula', 'Densidade': 'Faixa'},
        )

        fig.update_layout(
            margin=dict(l=10, r=10, t=50, b=10),
            legend_title_text='Nível de Densidade',
        )

        return fig

    @staticmethod
    def plot_mapa_recorrencia(
        df_muni: pd.DataFrame,
        municipio: str,
        tam_grid_km: float = 10.0,
        **kwargs
    ) -> go.Figure:
        """Gera mapa de Recorrência Histórica por quadrículas configuráveis."""
        df_valid = df_muni.dropna(subset=['Latitude', 'Longitude']).copy()

        if df_valid.empty:
            fig = go.Figure()
            fig.add_annotation(text="Sem dados para cálculo de recorrência.", showarrow=False)
            return fig

        df_valid['Ano'] = df_valid['Ano'].astype(int)
        total_anos_serie = df_valid['Ano'].nunique()

        df_grid = VisualizadorSIMD._criar_grid_km(df_valid, tam_grid_km)

        grid_rec = (
            df_grid.groupby(['lat_grid', 'lon_grid'])
            .agg(
                anos_com_fogo=('Ano', 'nunique'),
                total_focos_historico=('Ano', 'count'),
                ultimo_ano=('Ano', 'max')
            )
            .reset_index()
        )

        grid_rec['pct_recorrencia'] = (grid_rec['anos_com_fogo'] / total_anos_serie) * 100

        condicoes = [
            grid_rec['pct_recorrencia'] <= 25,
            (grid_rec['pct_recorrencia'] > 25) & (grid_rec['pct_recorrencia'] <= 50),
            (grid_rec['pct_recorrencia'] > 50) & (grid_rec['pct_recorrencia'] <= 75),
            grid_rec['pct_recorrencia'] > 75
        ]
        categorias = [
            "Esporádica (≤ 25% dos anos)",
            "Frequente (25% a 50% dos anos)",
            "Alta Recorrência (50% a 75% dos anos)",
            "Sistemática / Crítica (> 75% dos anos)"
        ]

        grid_rec['Grau_Recorrencia'] = np.select(condicoes, categorias, default="Esporádica (≤ 25% dos anos)")

        lat_centro = grid_rec['lat_grid'].mean()
        lon_centro = grid_rec['lon_grid'].mean()

        fig = px.scatter_mapbox(
            grid_rec,
            lat='lat_grid',
            lon='lon_grid',
            size='total_focos_historico',
            color='Grau_Recorrencia',
            category_orders={'Grau_Recorrencia': categorias},
            color_discrete_map=PALETA_RECORRENCIA,
            size_max=22,
            zoom=8,
            center=dict(lat=lat_centro, lon=lon_centro),
            mapbox_style='open-street-map',
            title=f"<b>Grau de Recorrência Histórica ({tam_grid_km:g}km × {tam_grid_km:g}km) — {municipio.upper()}</b>",
            hover_data={
                'lat_grid': False,
                'lon_grid': False,
                'anos_com_fogo': True,
                'pct_recorrencia': ':.1f',
                'total_focos_historico': True,
                'ultimo_ano': True
            },
            labels={
                'anos_com_fogo': 'Anos com Fogo',
                'pct_recorrencia': '% Recorrência',
                'total_focos_historico': 'Total Focos Histórico',
                'ultimo_ano': 'Último Ano',
                'Grau_Recorrencia': 'Classificação'
            }
        )

        fig.update_layout(
            margin=dict(l=10, r=10, t=50, b=10),
            legend_title_text='Grau de Persistência',
        )

        return fig

    @staticmethod
    def plot_mapa_clusters(df_clusters: pd.DataFrame, municipio: str) -> go.Figure:
        """Gera mapa de adensamentos por DBSCAN."""
        if df_clusters.empty:
            fig = go.Figure()
            fig.add_annotation(text="Nenhum cluster detectado.", showarrow=False)
            return fig

        fig = px.scatter_mapbox(
            df_clusters,
            lat='lat_centro',
            lon='lon_centro',
            size='total_focos',
            color='frp_acumulado',
            color_continuous_scale="YlOrRd",
            size_max=35,
            zoom=8,
            mapbox_style="open-street-map",
            title=f"<b>Núcleos Quentes de Focos (DBSCAN) — {municipio.upper()}</b>",
            hover_data={"total_focos": True, "frp_acumulado": ":.1f"}
        )

        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    @staticmethod
    def exportar_geopackage_qgis(df_muni: pd.DataFrame, municipio: str, tam_grid_km: float, arquivo_saida: str):
        """Exporta a grade vetorial para abertura direta no QGIS."""
        try:
            import geopandas as gpd
            from shapely.geometry import box

            df_valid = df_muni.dropna(subset=['Latitude', 'Longitude']).copy()
            lat_media = df_valid['Latitude'].mean()

            step_lat = tam_grid_km / 111.0
            step_lon = tam_grid_km / (111.0 * np.cos(np.radians(lat_media)))

            df_valid['lat_grid'] = (np.floor(df_valid['Latitude'] / step_lat) * step_lat + step_lat / 2).round(4)
            df_valid['lon_grid'] = (np.floor(df_valid['Longitude'] / step_lon) * step_lon + step_lon / 2).round(4)

            grid_stats = df_valid.groupby(['lat_grid', 'lon_grid']).agg(
                total_focos=('Ano', 'count'),
                anos_com_fogo=('Ano', 'nunique'),
                ultimo_ano=('Ano', 'max')
            ).reset_index()

            geometrias = [
                box(
                    row['lon_grid'] - step_lon / 2,
                    row['lat_grid'] - step_lat / 2,
                    row['lon_grid'] + step_lon / 2,
                    row['lat_grid'] + step_lat / 2
                ) for _, row in grid_stats.iterrows()
            ]

            gdf = gpd.GeoDataFrame(grid_stats, geometry=geometrias, crs="EPSG:4326")
            gdf.to_file(arquivo_saida, driver="GPKG")
            print(f"[OK] Camada vetorial QGIS salva: {arquivo_saida}")
        except Exception as e:
            print(f"[AVISO] Não foi possível exportar GeoPackage QGIS: {e}")