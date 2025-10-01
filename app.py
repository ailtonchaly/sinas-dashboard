import pandas as pd
from dash import Dash, dcc, html, dash_table
import plotly.express as px
import plotly.graph_objects as go

# ---------------- Arquivo de dados ----------------
ARQUIVO_FONTES = "fontes_cleaned.xlsx"  # ou "fontes_cleaned.csv"


# ---------------- Ler dados ----------------
def ler_levantamentos():
    try:
        df = pd.read_excel(ARQUIVO_FONTES)  # se for CSV, use pd.read_csv
    except FileNotFoundError:
        raise Exception(f"Arquivo {ARQUIVO_FONTES} não encontrado. Coloque o arquivo no mesmo diretório do app.py")

    df['Data_Levantamento'] = pd.to_datetime(df['Data_Levantamento'])
    df = df[(df['Data_Levantamento'].dt.year == 2025) & (df['Provincia'] != 'Maputo Cidade')]
    df['Ano_Mes'] = df['Data_Levantamento'].dt.to_period('M').astype(str)
    return df


# ---------------- Processar dados ----------------
def preparar_dados(df):
    df_mes_geral = df.groupby('Ano_Mes').size().reset_index(name='Total_Levantamentos')
    df_prov_mes = df.groupby(['Provincia', 'Ano_Mes']).size().reset_index(name='Total_Levantamentos')

    ranking_ativas = df.groupby('Provincia').size().reset_index(name='Total_Levantamentos').sort_values(
        by='Total_Levantamentos', ascending=False)
    ranking_paradas = df.groupby('Provincia')['Data_Levantamento'].max().reset_index().sort_values(
        by='Data_Levantamento')

    kpi_total = df.shape[0]
    kpi_prov = df['Provincia'].nunique()
    kpi_ultimo = df['Data_Levantamento'].max()
    kpi_media_mensal = df_mes_geral['Total_Levantamentos'].mean()

    return df_mes_geral, df_prov_mes, ranking_ativas, ranking_paradas, kpi_total, kpi_prov, kpi_ultimo, kpi_media_mensal


# ---------------- Criar gráficos ----------------
def criar_graficos(df_mes_geral, df_prov_mes, ranking_ativas, ranking_paradas):
    fig_linha = px.line(df_mes_geral, x='Ano_Mes', y='Total_Levantamentos', markers=True,
                        title='Levantamentos 2025 (Geral)',
                        labels={'Ano_Mes': 'Ano-Mês', 'Total_Levantamentos': 'Total Levantamentos'})
    fig_linha.update_traces(line=dict(color='#2E86AB', width=4), marker=dict(size=9))
    fig_linha.update_layout(plot_bgcolor='#F4F6F7', paper_bgcolor='#F4F6F7', font=dict(family='Arial', size=12))

    fig_barras_prov = px.bar(df_prov_mes, x='Ano_Mes', y='Total_Levantamentos', color='Provincia', barmode='group',
                             title='Levantamentos por Província',
                             labels={'Ano_Mes': 'Ano-Mês', 'Total_Levantamentos': 'Total Levantamentos'})
    fig_barras_prov.update_layout(xaxis_tickangle=-45, plot_bgcolor='#F4F6F7', paper_bgcolor='#F4F6F7',
                                  font=dict(family='Arial', size=12))

    fig_ranking_ativas = px.bar(ranking_ativas, x='Total_Levantamentos', y='Provincia', orientation='h',
                                color='Total_Levantamentos', color_continuous_scale='Greens',
                                title='Ranking Províncias Mais Ativas')
    fig_ranking_ativas.update_layout(yaxis={'categoryorder': 'total ascending'}, plot_bgcolor='#F4F6F7',
                                     paper_bgcolor='#F4F6F7')

    fig_paradas = px.bar(ranking_paradas, x='Provincia', y='Data_Levantamento',
                         title='Províncias com Últimos Levantamentos Mais Antigos',
                         color='Data_Levantamento', color_continuous_scale='Reds')
    fig_paradas.update_layout(plot_bgcolor='#F4F6F7', paper_bgcolor='#F4F6F7', font=dict(family='Arial', size=12))

    fig_media = go.Figure(go.Indicator(
        mode="number+delta",
        value=df_mes_geral['Total_Levantamentos'].mean(),
        number={'prefix': "Média Mensal: "},
        delta={'reference': df_mes_geral['Total_Levantamentos'].mean() * 1.1, 'relative': True},
        title={"text": "Média de Levantamentos por Mês"}))
    fig_media.update_layout(paper_bgcolor='#F4F6F7')

    return fig_linha, fig_barras_prov, fig_ranking_ativas, fig_paradas, fig_media


# ---------------- Criar dashboard ----------------
def criar_dashboard(fig_linha, fig_barras_prov, fig_ranking_ativas, fig_paradas, fig_media,
                    ranking_ativas, ranking_paradas, kpi_total, kpi_prov, kpi_ultimo, kpi_media_mensal):
    app = Dash(__name__)
    app.title = "Dashboard Levantamentos SINAS 2025 - Super Top"

    app.layout = html.Div([
        html.H1("Dashboard Levantamentos SINAS 2025",
                style={'textAlign': 'center', 'marginBottom': 20, 'color': '#1F618D'}),

        html.Div([
            html.Div([html.H4("Total Levantamentos 2025"), html.P(f"{kpi_total}")],
                     style={'width': '20%', 'display': 'inline-block', 'textAlign': 'center',
                            'backgroundColor': '#D6EAF8', 'padding': 20, 'margin': 5, 'borderRadius': 10}),
            html.Div([html.H4("Número de Províncias"), html.P(f"{kpi_prov}")],
                     style={'width': '20%', 'display': 'inline-block', 'textAlign': 'center',
                            'backgroundColor': '#D5F5E3', 'padding': 20, 'margin': 5, 'borderRadius': 10}),
            html.Div([html.H4("Último Levantamento"), html.P(f"{kpi_ultimo.date()}")],
                     style={'width': '20%', 'display': 'inline-block', 'textAlign': 'center',
                            'backgroundColor': '#FADBD8', 'padding': 20, 'margin': 5, 'borderRadius': 10}),
            html.Div([html.H4("Média Mensal"), html.P(f"{kpi_media_mensal:.2f}")],
                     style={'width': '20%', 'display': 'inline-block', 'textAlign': 'center',
                            'backgroundColor': '#FCF3CF', 'padding': 20, 'margin': 5, 'borderRadius': 10})
        ], style={'display': 'flex', 'justifyContent': 'center', 'marginBottom': 30}),

        html.Div([
            html.Div(dcc.Graph(figure=fig_linha),
                     style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'}),
            html.Div(dcc.Graph(figure=fig_barras_prov),
                     style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginLeft': '4%'})
        ], style={'marginBottom': 40}),

        html.H2("Ranking Províncias Mais Ativas", style={'color': '#1F618D'}),
        dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in ranking_ativas.columns],
            data=ranking_ativas.to_dict('records'),
            sort_action='native',
            filter_action='native',
            style_table={'overflowX': 'auto', 'marginBottom': 30},
            style_cell={'textAlign': 'center', 'padding': 5},
            style_header={'backgroundColor': '#27AE60', 'color': 'white', 'fontWeight': 'bold'}
        ),

        html.Div([
            html.Div(dcc.Graph(figure=fig_paradas), style={'width': '48%', 'display': 'inline-block'}),
            html.Div(dcc.Graph(figure=fig_media), style={'width': '48%', 'display': 'inline-block', 'marginLeft': '4%'})
        ], style={'marginTop': 40})
    ], style={'width': '95%', 'margin': 'auto'})

    return app


# ---------------- Execução ----------------
if __name__ == "__main__":
    df = ler_levantamentos()
    df_mes_geral, df_prov_mes, ranking_ativas, ranking_paradas, kpi_total, kpi_prov, kpi_ultimo, kpi_media_mensal = preparar_dados(
        df)
    fig_linha, fig_barras_prov, fig_ranking_ativas, fig_paradas, fig_media = criar_graficos(
        df_mes_geral, df_prov_mes, ranking_ativas, ranking_paradas)
    app = criar_dashboard(fig_linha, fig_barras_prov, fig_ranking_ativas, fig_paradas, fig_media,
                          ranking_ativas, ranking_paradas, kpi_total, kpi_prov, kpi_ultimo, kpi_media_mensal)
    app.run_server(host="0.0.0.0", port=8050, debug=False)
