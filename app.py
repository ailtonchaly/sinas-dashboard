import dash
from dash import dcc, html, Input, Output, dash_table, State
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

# =========================
# 1. CONFIGURAÇÃO E CARREGAR DADOS
# =========================

# Nome da coluna de Código de Levantamento
CODIGO_COL = 'Codigo_Fonte'
DISTRITO_COL = 'Distrito'

try:
    df = pd.read_excel("fontes_cleaned.xlsx")
    df['Data_Levantamento'] = pd.to_datetime(df['Data_Levantamento'])
    df['Ano'] = df['Data_Levantamento'].dt.year
    df['Mes'] = df['Data_Levantamento'].dt.month

    df = df[df['Provincia'] != 'Maputo Cidade'].copy()

    if CODIGO_COL not in df.columns:
        print(f"ATENÇÃO: A coluna '{CODIGO_COL}' não foi encontrada.")
        df[CODIGO_COL] = df.get('codigo', 'COD_FALTA')

    if DISTRITO_COL not in df.columns:
        print(f"ATENÇÃO: A coluna '{DISTRITO_COL}' não foi encontrada.")
        df[DISTRITO_COL] = df['Provincia'].astype(str) + '_TempDistrito'

    TARGET_YEAR = df['Ano'].max() if not df.empty else datetime.now().year
    df_2025 = df[df["Ano"] == TARGET_YEAR].copy()

except FileNotFoundError:
    print("ERRO: O arquivo 'fontes_cleaned.xlsx' não foi encontrado. Usando DataFrame vazio.")
    df = pd.DataFrame(columns=['Data_Levantamento', 'Provincia', DISTRITO_COL, CODIGO_COL, 'Ano', 'Mes'])
    df_2025 = df.copy()
    TARGET_YEAR = datetime.now().year

# =========================
# 2. DASH APP E ESTILOS
# =========================
app = dash.Dash(__name__,
                external_stylesheets=[dbc.themes.CYBORG, "https://use.fontawesome.com/releases/v5.8.1/css/all.css"],
                suppress_callback_exceptions=True
                )
server = app.server

UNIFORM_HEIGHT = '350px'


def make_kpi_card(title, value, icon, color):
    """Componente KPI Card com labels totalmente alinhados à esquerda (text-start)."""
    return dbc.Card(
        dbc.CardBody([
            html.Div(
                [
                    html.I(className=f"fas {icon} fa-lg", style={"color": color, "margin-right": "10px"}),
                    html.Span(title, style={"font-weight": "300", "font-size": "14px", "color": "white"}),
                ],
                className="d-flex align-items-center text-start"
            ),
            html.H3(value, className="mt-2 text-start",
                    style={"color": color, "font-size": "24px", "font-weight": "700"}),
        ]),
        className="shadow-lg rounded-3 mb-3 border-0",
        style={"background-color": "#212529"}
    )


# Sidebar com LOGO (ALTERAÇÃO AQUI)
sidebar = html.Div(
    [
        # NOVO: Inserção do Logo do SINAS
        html.Img(
            src=app.get_asset_url('00publicoview_001_geral_consulta-removebg-preview.png'),
            style={
                'width': '80%',
                'max-width': '180px',
                'height': 'auto',
                'display': 'block',
                'margin': '0 auto 1.5rem auto'  # Centraliza e adiciona margem
            },
            className="mb-4"
        ),
        html.Hr(style={"border": "1px solid #16a085"}),
        dbc.Nav(
            [
                dbc.NavLink([html.I(className="fas fa-cogs me-2"), "Dashboard"], href="/", active="exact",
                            style={"font-size": "14px"}),
                dbc.NavLink([html.I(className="fas fa-map-marked-alt me-2"), "Províncias"], href="/provincias",
                            active="exact", style={"font-size": "14px"}),
            ],
            vertical=True,
            pills=True,
        ),
    ],
    style={
        "position": "fixed",
        "top": 0, "left": 0, "bottom": 0, "width": "16rem",
        "padding": "2rem 1rem",
        "background-color": "#1c2125",
        "box-shadow": "2px 0 5px rgba(0,0,0,0.5)"
    },
)

content = html.Div(id="page-content", style={"margin-left": "18rem", "margin-right": "2rem", "padding": "2rem 1rem"})
app.layout = html.Div([dcc.Location(id="url"), sidebar, content])


# =========================
# 3. CALLBACKS (LÓGICA INALTERADA)
# =========================

@app.callback(Output("page-content", "children"), [Input("url", "pathname")])
def render_page_content(pathname):
    if pathname == "/":
        # CÁLCULOS DO DASHBOARD GERAL
        total_levantamentos = len(df_2025)
        provincias_ativas = df_2025["Provincia"].nunique()
        ultimo_registo = df["Data_Levantamento"].max()
        dias_desde_ult = (pd.to_datetime("today").normalize() - ultimo_registo).days
        df_mes_geral = df_2025.groupby('Mes').size().reset_index(name='Total_Levantamentos')
        media_mensal = df_mes_geral['Total_Levantamentos'].mean() if not df_mes_geral.empty else 0
        ranking_paradas = df.groupby("Provincia")["Data_Levantamento"].max().reset_index()
        hoje = pd.to_datetime(datetime.now().date())
        ranking_paradas["Dias_Parados"] = (hoje - ranking_paradas["Data_Levantamento"]).dt.days
        ranking_paradas['Data_Levantamento'] = ranking_paradas['Data_Levantamento'].dt.strftime('%Y-%m-%d')
        ranking_paradas = ranking_paradas.sort_values("Dias_Parados", ascending=False).head(5).reset_index(drop=True)
        ranking_paradas.columns = ['Província', 'Último Registo', 'Dias Parados']
        df_ranking_total = df_2025.groupby("Provincia").size().reset_index(name='Total')
        df_ranking_total = df_ranking_total.sort_values('Total', ascending=True)

        # GRÁFICOS DO DASHBOARD GERAL
        fig_ranking = px.bar(df_ranking_total, x='Total', y='Provincia', orientation='h',
                             title=f"📈 RANKING DE TOTAL DE LEVANTAMENTOS POR PROVÍNCIA",
                             color='Total', color_continuous_scale="Plotly3",
                             labels={"Total": "Total Levantamentos"},
                             template="plotly_dark")
        fig_ranking.update_layout(yaxis_title=None, xaxis_title="Total", margin=dict(t=30), title_font_size=13,
                                  title_x=0.5)

        fig_consistencia_line = go.Figure(data=[go.Scatter(x=df_mes_geral['Mes'], y=df_mes_geral['Total_Levantamentos'],
                                                           mode='lines+markers', line=dict(color='#f1c40f', width=3),
                                                           marker=dict(size=8, symbol='circle'))])
        fig_consistencia_line.update_layout(
            title=f"📉 CONSISTÊNCIA MENSAL (TENDÊNCIA) DE LEVANTAMENTOS",
            xaxis_title="Mês", yaxis_title="Total Levantamentos", margin=dict(t=30),
            title_font_size=13, title_x=0.5, xaxis=dict(tickmode='array', tickvals=list(range(1, 13))),
            template="plotly_dark"
        )

        fig_consistencia_bar = px.bar(df_mes_geral, x='Mes', y='Total_Levantamentos',
                                      title=f"📊 CONSISTÊNCIA MENSAL (MAGNITUDE) DE LEVANTAMENTOS",
                                      labels={'Total_Levantamentos': 'Total Levantamentos', 'Mes': 'Mês'},
                                      text_auto=True, template="plotly_dark")
        fig_consistencia_bar.update_traces(marker_color='#16a085', opacity=0.8)
        fig_consistencia_bar.update_layout(xaxis_tickvals=list(range(1, 13)), margin=dict(t=30), title_font_size=13,
                                           title_x=0.5)

        # LAYOUT DO DASHBOARD GERAL
        return html.Div([
            html.H4(f"RESUMO GERAL DE DESEMPENHO - ANO {TARGET_YEAR}", className="mb-4 text-uppercase",
                    style={"color": "#16a085", "font-weight": "500"}),
            dbc.Row([
                dbc.Col(make_kpi_card("Total Levantamentos", f"{total_levantamentos:,}", "fa-database", "#3498db"),
                        md=3),
                dbc.Col(make_kpi_card("Províncias Ativas", provincias_ativas, "fa-map-marked-alt", "#e67e22"), md=3),
                dbc.Col(make_kpi_card("Média Mensal", f"{media_mensal:.0f}", "fa-chart-line", "#2ecc71"), md=3),
                dbc.Col(make_kpi_card("Dias Desde Último Registo", f"{dias_desde_ult} dias", "fa-bell", "#e74c3c"),
                        md=3),
            ]),
            dbc.Row([
                dbc.Col(
                    html.Div([
                        html.H5("🚨 TOP 5 PROVÍNCIAS COM LEVANTAMENTOS MAIS ANTIGOS",
                                className="mb-3 text-center text-uppercase",
                                style={"color": "white", "font-weight": "500", "font-size": "13px"}),
                        dash_table.DataTable(
                            id='table-paradas',
                            columns=[{"name": i, "id": i} for i in ranking_paradas.columns],
                            data=ranking_paradas.to_dict('records'),
                            style_table={'height': '100%'},
                            style_header={'backgroundColor': '#34495e', 'fontWeight': 'bold', 'color': 'white',
                                          'border': '1px solid #1c2125'},
                            style_data={'backgroundColor': '#212529', 'color': 'white', 'border': '1px solid #1c2125'},
                            style_cell={'textAlign': 'center', 'fontSize': '12px', 'padding': '8px'}
                        )
                    ], style={'height': UNIFORM_HEIGHT}),
                    md=6
                ),
                dbc.Col(dcc.Graph(figure=fig_ranking, style={'height': UNIFORM_HEIGHT}), md=6),
            ], className="mt-3"),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=fig_consistencia_line, style={'height': UNIFORM_HEIGHT}), md=6),
                dbc.Col(dcc.Graph(figure=fig_consistencia_bar, style={'height': UNIFORM_HEIGHT}), md=6),
            ], className="mt-3")
        ])

    elif pathname == "/provincias":
        # LAYOUT DA PÁGINA DE PROVÍNCIAS
        return html.Div([
            html.H4("ANÁLISE DETALHADA POR PROVÍNCIA E DISTRITO", className="mb-4 text-uppercase",
                    style={"color": "#16a085", "font-weight": "500"}),
            dbc.Row([
                dbc.Col(
                    dcc.Dropdown(
                        id="dropdown-provincia",
                        options=[{"label": prov, "value": prov} for prov in sorted(df["Provincia"].unique())],
                        placeholder="1. Selecione a Província (Obrigatório)",
                        style={"color": "#212529", "font-size": "14px"}
                    ), md=4
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id="dropdown-distrito",
                        placeholder="2. Selecione o Distrito (Para Detalhe Específico)",
                        disabled=True,
                        style={"color": "#212529", "font-size": "14px"}
                    ), md=4
                )
            ]),
            html.Div(id="provincia-content", className="mt-4")
        ])

    return dbc.Jumbotron([
        html.H1("404: Página não encontrada", className="text-danger"),
        html.Hr(),
        html.P(f"A página {pathname} não existe...")
    ])


@app.callback(
    Output("dropdown-distrito", "options"),
    Output("dropdown-distrito", "disabled"),
    Output("dropdown-distrito", "value"),
    Input("dropdown-provincia", "value")
)
def set_distrito_options(selected_provincia):
    if not selected_provincia:
        return [], True, None

    df_prov = df[df["Provincia"] == selected_provincia]
    distritos = sorted(df_prov[DISTRITO_COL].unique())
    options = [{"label": d, "value": d} for d in distritos]

    return options, False, None


@app.callback(
    Output("provincia-content", "children"),
    Input("dropdown-provincia", "value"),
    Input("dropdown-distrito", "value")
)
def update_detail_content(provincia, distrito):
    if not provincia:
        return html.P("Selecione uma província para iniciar a análise detalhada.", style={"color": "gray"})

    if distrito and provincia:
        # 1. Caso: Selecionou um DISTRITO ESPECÍFICO
        df_trabalho = df[(df["Provincia"] == provincia) & (df[DISTRITO_COL] == distrito)].copy()
        df_pai = df[df["Provincia"] == provincia].copy()
        titulo_principal = f"DETALHE DO DISTRITO: {distrito.upper()} ({provincia.upper()})"

        total_trabalho = len(df_trabalho)
        total_pai = len(df_pai)
        percentual_pai = (total_trabalho / total_pai) * 100 if total_pai else 0

        fig_historico = px.histogram(df_trabalho, x="Ano", nbins=10,
                                     title=f"EVOLUÇÃO HISTÓRICA DE LEVANTAMENTOS NO DISTRITO",
                                     labels={'count': 'Total Levantamentos'},
                                     text_auto=True, template="plotly_dark")
        fig_historico.update_traces(marker_color='#e67e22', opacity=0.8)
        fig_historico.update_layout(title_font_size=13, margin=dict(t=30), title_x=0.5, height=350)

        df_tabela = df_trabalho[['Data_Levantamento', CODIGO_COL, DISTRITO_COL]].copy()
        df_tabela['Data_Levantamento'] = df_tabela['Data_Levantamento'].dt.strftime('%Y-%m-%d')
        df_tabela = df_tabela.sort_values('Data_Levantamento', ascending=False).head(10).reset_index(drop=True)
        df_tabela.columns = ['Data', 'Código', 'Distrito']

        # LAYOUT DE DETALHE DE DISTRITO
        return html.Div([
            html.H4(titulo_principal, className="mb-4 text-uppercase",
                    style={"color": "#f1c40f", "font-weight": "500"}),

            dbc.Row([
                dbc.Col(make_kpi_card("Total Levantamentos no Distrito", f"{total_trabalho:,}", "fa-check-circle",
                                      "#16a085"), md=3),
                dbc.Col(make_kpi_card("Anos com Levantamentos", df_trabalho["Ano"].nunique(), "fa-history", "#8e44ad"),
                        md=3),
                dbc.Col(
                    make_kpi_card(f"% da Província ({provincia})", f"{percentual_pai:.1f}%", "fa-sitemap", "#3498db"),
                    md=3),
                dbc.Col(make_kpi_card("Dias Desde Último Registo",
                                      f"{(pd.to_datetime('today').normalize() - df_trabalho['Data_Levantamento'].max()).days} dias",
                                      "fa-clock", "#c0392b"), md=3),
            ], className="mb-4"),

            dbc.Row([
                dbc.Col(dcc.Graph(figure=fig_historico, style={'height': UNIFORM_HEIGHT}), md=6),
                dbc.Col(
                    html.Div([
                        html.H5(f"📝 AMOSTRA DOS ÚLTIMOS REGISTOS ({distrito.upper()})",
                                className="mb-3 text-center text-uppercase",
                                style={"color": "white", "font-weight": "500", "font-size": "13px"}),
                        dash_table.DataTable(
                            id='table-detail', columns=[{"name": i, "id": i} for i in df_tabela.columns],
                            data=df_tabela.to_dict('records'), style_table={'height': UNIFORM_HEIGHT},
                            style_header={'backgroundColor': '#34495e', 'fontWeight': 'bold', 'color': 'white',
                                          'border': '1px solid #1c2125'},
                            style_data={'backgroundColor': '#212529', 'color': 'white', 'border': '1px solid #1c2125'},
                            style_cell={'textAlign': 'center', 'fontSize': '12px', 'padding': '8px'}
                        )
                    ], style={'height': UNIFORM_HEIGHT}), md=6
                ),
            ], className="mt-3"),
        ])


    else:
        # 2. Caso: Selecionou APENAS a PROVÍNCIA (Padrão)
        df_prov = df[df["Provincia"] == provincia].copy()

        total_prov = len(df_prov)
        dias_parados_prov = (pd.to_datetime("today").normalize() - df_prov["Data_Levantamento"].max()).days

        fig_anos = px.histogram(df_prov, x="Ano", nbins=10,
                                title=f"EVOLUÇÃO HISTÓRICA DE LEVANTAMENTOS ({provincia.upper()})",
                                labels={'count': 'Total Levantamentos'},
                                text_auto=True, template="plotly_dark")
        fig_anos.update_traces(marker_color='#e67e22', opacity=0.8)
        fig_anos.update_layout(title_font_size=13, margin=dict(t=30), title_x=0.5, height=350)

        df_ranking_distrito = df_prov.groupby(DISTRITO_COL).size().reset_index(name='Total')
        df_ranking_distrito = df_ranking_distrito.sort_values('Total', ascending=True)

        fig_ranking_dist = px.bar(df_ranking_distrito, x='Total', y=DISTRITO_COL, orientation='h',
                                  title=f"🥇 RANKING DE TOTAL DE LEVANTAMENTOS POR DISTRITO",
                                  color='Total', color_continuous_scale="Viridis",
                                  labels={"Total": "Total Levantamentos"},
                                  template="plotly_dark")
        fig_ranking_dist.update_layout(yaxis_title=None, xaxis_title="Total", margin=dict(t=30), title_font_size=13,
                                       title_x=0.5, height=350)

        ranking_paradas_dist = df_prov.groupby(DISTRITO_COL)["Data_Levantamento"].max().reset_index()
        ranking_paradas_dist["Dias_Parados"] = (
                    pd.to_datetime("today").normalize() - ranking_paradas_dist["Data_Levantamento"]).dt.days
        ranking_paradas_dist['Data_Levantamento'] = ranking_paradas_dist['Data_Levantamento'].dt.strftime('%Y-%m-%d')
        ranking_paradas_dist = ranking_paradas_dist.sort_values("Dias_Parados", ascending=False).reset_index(drop=True)
        ranking_paradas_dist.columns = ['Distrito', 'Último Registo', 'Dias Parados']

        tabela_distrito = dash_table.DataTable(
            id='table-distrito-resumo',
            columns=[{"name": i, "id": i} for i in ranking_paradas_dist.columns],
            data=ranking_paradas_dist.to_dict('records'),
            style_table={'height': '100%'},
            style_header={'backgroundColor': '#34495e', 'fontWeight': 'bold', 'color': 'white',
                          'border': '1px solid #1c2125'},
            style_data={'backgroundColor': '#212529', 'color': 'white', 'border': '1px solid #1c2125'},
            style_cell={'textAlign': 'center', 'fontSize': '12px', 'padding': '8px'}
        )

        # LAYOUT DE RESUMO DE PROVÍNCIA
        return html.Div([
            html.H4(f"RESUMO GERAL DA PROVÍNCIA: {provincia.upper()}", className="mb-4 text-uppercase",
                    style={"color": "#f1c40f", "font-weight": "500"}),

            dbc.Row([
                dbc.Col(make_kpi_card("Total Levantamentos", f"{total_prov:,}", "fa-check-circle", "#16a085"), md=3),
                dbc.Col(make_kpi_card("Anos com Levantamentos", df_prov["Ano"].nunique(), "fa-history", "#8e44ad"),
                        md=3),
                dbc.Col(
                    make_kpi_card("Distritos Ativos", df_prov[DISTRITO_COL].nunique(), "fa-map-marker-alt", "#3498db"),
                    md=3),
                dbc.Col(make_kpi_card("Dias Desde Último Registo", f"{dias_parados_prov} dias", "fa-clock", "#c0392b"),
                        md=3),
            ], className="mb-4"),

            dbc.Row([
                dbc.Col(dcc.Graph(figure=fig_anos, style={'height': UNIFORM_HEIGHT}), md=6),
                dbc.Col(dcc.Graph(figure=fig_ranking_dist, style={'height': UNIFORM_HEIGHT}), md=6),
            ], className="mt-3"),

            dbc.Row([
                dbc.Col(
                    html.Div([
                        html.H5("🚨 DIAS PARADOS POR DISTRITO (RISCO)", className="mb-3 text-center text-uppercase",
                                style={"color": "white", "font-weight": "500", "font-size": "13px"}),
                        tabela_distrito
                    ], style={'height': UNIFORM_HEIGHT}),
                    md=12
                ),
            ], className="mt-3")
        ])


# =========================
# 4. RUN
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=True)