import dash
from dash import dcc, html, Input, Output, dash_table, State
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime
from functools import reduce

# =========================
# 1. CONFIGURAÇÃO E CARREGAR DADOS MULTI-INFRA
# =========================

# Parâmetros de Nomes de Coluna
CODIGO_COL = 'Codigo_Fonte'
DISTRITO_COL = 'Distrito'
DATA_COL = 'Data_Levantamento'
ERROR_FLAG_COL = 'Erros_DAM_Simulados'
PROVINCIA_COL = 'Provincia'  # Constante para clareza (sem acento)

# Parâmetros de Priorização de Inactividade e Novos KPIs
DAYS_THRESHOLD = 14
INATIVIDADE_SCORE_NAME = 'Pontos de Inactividade (PI)'
DAYS_COLS = ['Dias Parados (Fontes)', 'Dias Parados (SAA)', 'Dias Parados (Comunidades)']
DAYS_ACTIVE_THRESHOLD = 30


def load_and_clean(file_name, data_col_name):
    """Carrega o ficheiro, padroniza as colunas de data e filtra Maputo Cidade."""
    try:
        # Certifique-se de que os ficheiros 'fontes_cleaned.xlsx', 'saa_cleaned.xlsx',
        # e 'comunidades_cleaned.xlsx' estão disponíveis na mesma pasta.
        df = pd.read_excel(file_name)

        if data_col_name not in df.columns:
            print(
                f"ERRO DE COLUNA CRÍTICO no ficheiro '{file_name}': A coluna de data '{data_col_name}' não foi encontrada.")
            return pd.DataFrame(columns=[PROVINCIA_COL, DISTRITO_COL, DATA_COL, 'Ano', 'Mes', CODIGO_COL])

        df[DATA_COL] = pd.to_datetime(df[data_col_name], errors='coerce')
        df = df[df[PROVINCIA_COL] != 'Maputo Cidade'].copy()

        if file_name == "fontes_cleaned.xlsx" and CODIGO_COL not in df.columns:
            print(f"ERRO CRÍTICO: O ficheiro {file_name} não tem a coluna de código '{CODIGO_COL}'.")
            return pd.DataFrame(columns=[PROVINCIA_COL, DISTRITO_COL, DATA_COL, 'Ano', 'Mes', CODIGO_COL])

        df['Ano'] = df[DATA_COL].dt.year
        df['Mes'] = df[DATA_COL].dt.month

        return df
    except FileNotFoundError:
        print(f"ERRO: O ficheiro '{file_name}' não foi encontrado. Usando DataFrame vazio.")
        return pd.DataFrame(columns=[PROVINCIA_COL, DISTRITO_COL, DATA_COL, 'Ano', 'Mes', CODIGO_COL])
    except Exception as e:
        print(f"ERRO geral ao processar {file_name}: {e}")
        return pd.DataFrame(columns=[PROVINCIA_COL, DISTRITO_COL, DATA_COL, 'Ano', 'Mes', CODIGO_COL])


# Carregando as 3 Fontes de Dados
df_fontes = load_and_clean("fontes_cleaned.xlsx", DATA_COL)
df_saa = load_and_clean("saa_cleaned.xlsx", DATA_COL)
df_comunidades = load_and_clean("comunidades_cleaned.xlsx", DATA_COL)

# SIMULAÇÃO DE ERRO DE QUALIDADE (DAM)
if not df_fontes.empty:
    df_fontes[ERROR_FLAG_COL] = df_fontes[CODIGO_COL].isna().astype(int)

# DataFrame de Levantamentos (usado para o Dashboard Geral e filtros)
df = df_fontes.copy()

# Determinação do Ano Alvo
TARGET_YEAR = df['Ano'].max() if not df.empty else datetime.now().year
df_2025 = df[df["Ano"] == TARGET_YEAR].copy()


# =========================
# FUNÇÕES DE CÁLCULO DE INACTVIDADE E GERAIS
# =========================

def calculate_last_activity(df_base, infra_name):
    """Calcula os dias parados por distrito para um dado dataframe."""
    hoje = pd.to_datetime(datetime.now().date())

    last_reg = df_base.groupby([DISTRITO_COL, PROVINCIA_COL])[DATA_COL].max().reset_index()
    last_reg[f'Dias Parados ({infra_name})'] = (hoje - last_reg[DATA_COL]).dt.days

    return last_reg[[DISTRITO_COL, PROVINCIA_COL, f'Dias Parados ({infra_name})']]


def calculate_inatividade_score(row):
    """Calcula a pontuação de inactividade (0 a 3) com base nos 3 indicadores de Dias Parados (Limite: 14 dias)."""
    parados = 0
    for col_name in DAYS_COLS:
        # Se o distrito tem valor 9999 (nunca registou) ou está acima do limite
        if row[col_name] >= DAYS_THRESHOLD:
            parados += 1
    return parados


def get_full_inatividade_df(df_fontes, df_saa, df_comunidades):
    """Cria e calcula o DataFrame de Inactividade de Cadastro para todos os distritos."""

    # ----------------------------------------------------
    # 1. CÁLCULO DE INACTIVIDADE TEMPORAL (PI)
    # ----------------------------------------------------
    df_dias_fontes = calculate_last_activity(df_fontes, 'Fontes')
    df_dias_saa = calculate_last_activity(df_saa, 'SAA')
    df_dias_comunidades = calculate_last_activity(df_comunidades, 'Comunidades')

    data_frames = [df_dias_fontes, df_dias_saa, df_dias_comunidades]

    # Merge usando a constante PROVINCIA_COL
    df_inatividade = reduce(lambda left, right: pd.merge(left, right, on=[DISTRITO_COL, PROVINCIA_COL], how='outer'),
                            data_frames)

    # Max_Dias_Parados -> O número de dias mais recente (mínimo de dias parados) para o distrito entre as 3 infraestruturas
    df_inatividade['Max_Dias_Parados'] = df_inatividade[DAYS_COLS].min(
        axis=1)  # Usamos MIN para encontrar o registo MAIS RECENTE (menor n° de dias parados)
    df_inatividade = df_inatividade.fillna(9999)
    df_inatividade[INATIVIDADE_SCORE_NAME] = df_inatividade.apply(calculate_inatividade_score, axis=1)

    def calculate_average_inactive_days(row):
        # A média de dias parados SÓ para as infraestruturas que TÊM registo (valor != 9999)
        valid_days = [row[col] for col in DAYS_COLS if row[col] != 9999]
        # Aqui usamos MAX dos dias parados válidos, para ter a pior situação de inatividade
        return max(valid_days) if valid_days else 9999

    df_inatividade['Inactividade_Media_Dias'] = df_inatividade.apply(calculate_average_inactive_days, axis=1)

    # ----------------------------------------------------
    # 2. CÁLCULO DE INACTIVIDADE CRÍTICA ANUAL (CADASTRO)
    # ----------------------------------------------------

    # Obter a lista de distritos que fizeram cadastro em CADA INFRA no ANO ATUAL
    distritos_ativos_fontes_ano = df_fontes[df_fontes['Ano'] == TARGET_YEAR][DISTRITO_COL].unique()
    distritos_ativos_saa_ano = df_saa[df_saa['Ano'] == TARGET_YEAR][DISTRITO_COL].unique()
    distritos_ativos_comunidades_ano = df_comunidades[df_comunidades['Ano'] == TARGET_YEAR][DISTRITO_COL].unique()

    # Combinar as listas: se fez cadastro em PELO MENOS UMA INFRA, é considerado ATIVO no ano
    distritos_que_fizeram_cadastro_ano = set(distritos_ativos_fontes_ano).union(
        set(distritos_ativos_saa_ano),
        set(distritos_ativos_comunidades_ano)
    )

    # Adicionar a flag de inatividade crítica: False se não fez cadastro no ano atual
    df_inatividade['Cadastro_Ano_Atual'] = df_inatividade[DISTRITO_COL].isin(distritos_que_fizeram_cadastro_ano)

    return df_inatividade


# Cálculos globais para uso no dashboard Home
df_inatividade_geral = get_full_inatividade_df(df_fontes, df_saa, df_comunidades)

# =========================
# 2. DASH APP E ESTILOS
# =========================
app = dash.Dash(__name__,
                external_stylesheets=[dbc.themes.CYBORG, "https://use.fontawesome.com/releases/v5.8.1/css/all.css"],
                suppress_callback_exceptions=True
                )
server = app.server

UNIFORM_HEIGHT = '350px'


def make_kpi_card(title, value, icon, color, size="h3"):
    """
    Componente KPI Card.
    """
    try:
        ValueTag = getattr(html, size.upper())
    except AttributeError:
        ValueTag = html.Div

    return dbc.Card(
        dbc.CardBody([
            html.Div(
                [
                    html.I(className=f"fas {icon} fa-lg", style={"color": color, "margin-right": "10px"}),
                    html.Span(title, style={"font-weight": "300", "font-size": "14px", "color": "white"}),
                ],
                className="d-flex align-items-center text-start"
            ),
            ValueTag(value, className="mt-2 text-start",
                     style={"color": color, "font-size": "24px", "font-weight": "700"}),
        ]),
        className="shadow-lg rounded-3 mb-3 border-0",
        style={"background-color": "#212529"}
    )


# Sidebar com LOGO
sidebar = html.Div(
    [
        html.Img(
            src=app.get_asset_url('00publicoview_001_geral_consulta-removebg-preview.png'),
            style={
                'width': '80%',
                'max-width': '180px',
                'height': 'auto',
                'display': 'block',
                'margin': '0 auto 1.5rem auto'
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
# 3. CALLBACKS
# =========================

@app.callback(
    Output("dropdown-distrito", "options"),
    Output("dropdown-distrito", "disabled"),
    Output("dropdown-distrito", "value"),
    Input("dropdown-provincia", "value")
)
def set_distrito_options(selected_provincia):
    if not selected_provincia:
        return [], True, None

    df_prov = df[df[PROVINCIA_COL] == selected_provincia]
    distritos = sorted(df_prov[DISTRITO_COL].unique())
    options = [{"label": d, "value": d} for d in distritos]

    return options, False, None


# 3.2 Callback para atualizar o conteúdo detalhado (Província ou Distrito)
@app.callback(
    Output("provincia-content", "children"),
    Input("dropdown-provincia", "value"),
    Input("dropdown-distrito", "value")
)
def update_detail_content(provincia, distrito):
    if not provincia:
        return html.P("Selecione uma província para iniciar a análise detalhada.", style={"color": "gray"})

    # Filtra os 3 dataframes pela província selecionada
    df_prov_fontes = df_fontes[df_fontes[PROVINCIA_COL] == provincia].copy()
    df_prov_saa = df_saa[df_saa[PROVINCIA_COL] == provincia].copy()
    df_prov_comunidades = df_comunidades[df_comunidades[PROVINCIA_COL] == provincia].copy()

    # Cálculos de Inactividade (obtém df_inatividade_prov com a coluna 'Cadastro_Ano_Atual')
    df_inatividade_prov = get_full_inatividade_df(df_prov_fontes, df_prov_saa, df_prov_comunidades)
    df_tabela_inatividade = df_inatividade_prov[
        [DISTRITO_COL, INATIVIDADE_SCORE_NAME, 'Inactividade_Media_Dias'] + DAYS_COLS].copy()

    df_tabela_inatividade = df_tabela_inatividade.sort_values(
        [INATIVIDADE_SCORE_NAME, 'Inactividade_Media_Dias'],
        ascending=[False, False]
    )

    # CÁLCULO KPI DE QUALIDADE (PROVÍNCIA)
    total_fontes_prov = len(df_prov_fontes)
    total_saa_prov = len(df_prov_saa)
    total_comunidades_prov = len(df_prov_comunidades)
    total_levantamentos_infra = total_fontes_prov + total_saa_prov + total_comunidades_prov
    total_erros_dam_prov = df_prov_fontes[ERROR_FLAG_COL].sum() if not df_prov_fontes.empty else 0
    percent_erros_dam_prov = (total_erros_dam_prov / total_fontes_prov) * 100 if total_fontes_prov else 0

    # CÁLCULO KPI DE CADASTRO ANUAL CRÍTICA (PROVÍNCIA)
    # Contagem de distritos onde 'Cadastro_Ano_Atual' é False
    distritos_sem_cadastro_ano = (~df_inatividade_prov['Cadastro_Ano_Atual']).sum()

    # Cálculo do KPI de COBERTURA e FREQUÊNCIA para a Província
    total_distritos_na_prov = df_inatividade_prov[DISTRITO_COL].nunique()
    distritos_ativos_30d = df_inatividade_prov[df_inatividade_prov['Max_Dias_Parados'] <= DAYS_ACTIVE_THRESHOLD][
        DISTRITO_COL].nunique()
    percent_distritos_ativos = (distritos_ativos_30d / total_distritos_na_prov) * 100 if total_distritos_na_prov else 0

    # Frequência: Média de Dias de Inactividade
    inatividade_media = df_inatividade_prov[df_inatividade_prov['Inactividade_Media_Dias'] != 9999][
        'Inactividade_Media_Dias'].mean()
    inatividade_media = inatividade_media if not pd.isna(inatividade_media) else 0

    # Formatando os números para a visualização
    for col in DAYS_COLS:
        df_tabela_inatividade[col] = df_tabela_inatividade[col].apply(
            lambda x: f"{int(x):,} dias" if x != 9999 else "NUNCA REGISTOU")

    # Formatação da Inactividade Média
    df_tabela_inatividade['Inactividade_Media_Dias'] = df_tabela_inatividade['Inactividade_Media_Dias'].apply(
        lambda x: f"{int(x):,} dias" if x != 9999 else "NUNCA REGISTOU")

    # Estilos condicionais para a Tabela de Inactividade
    style_data_conditional = [
        {'if': {'filter_query': f'{{{INATIVIDADE_SCORE_NAME}}} = 3'},
         'backgroundColor': '#c0392b', 'color': 'white', 'fontWeight': 'bold'},
        {'if': {'filter_query': f'{{{INATIVIDADE_SCORE_NAME}}} = 2'},
         'backgroundColor': '#e67e22', 'color': 'white'},
        {'if': {'filter_query': f'{{{INATIVIDADE_SCORE_NAME}}} = 1'},
         'backgroundColor': '#f39c12', 'color': 'black'},
        {'if': {'filter_query': f'{{{INATIVIDADE_SCORE_NAME}}} = 0'},
         'backgroundColor': '#27ae60', 'color': 'white'},
    ]

    # =========================================================================
    # LÓGICA DE DETALHE POR DISTRITO
    # =========================================================================
    if distrito and provincia:
        df_trabalho = df_prov_fontes[(df_prov_fontes[DISTRITO_COL] == distrito)].copy()

        # KPIS de Detalhe de Distrito
        total_fontes_distrito = len(df_trabalho)
        total_saa_distrito = len(df_prov_saa[df_prov_saa[DISTRITO_COL] == distrito])
        total_comunidades_distrito = len(df_prov_comunidades[df_prov_comunidades[DISTRITO_COL] == distrito])
        total_levantamentos_infra_distrito = total_fontes_distrito + total_saa_distrito + total_comunidades_distrito

        # CÁLCULO KPI DE QUALIDADE (DISTRITO)
        total_erros_dam_distrito = df_trabalho[ERROR_FLAG_COL].sum() if not df_trabalho.empty else 0
        percent_erros_dam_distrito = (
                                                 total_erros_dam_distrito / total_fontes_distrito) * 100 if total_fontes_distrito else 0

        df_inat_distrito = df_inatividade_prov[df_inatividade_prov[DISTRITO_COL] == distrito].to_dict('records')[0]
        pi_score = df_inat_distrito[INATIVIDADE_SCORE_NAME]

        if pi_score == 3:
            inatividade_status = f"INACTIVO TOTAL (PI={pi_score})"
            inatividade_color = "#c0392b"
        elif pi_score >= 1:
            inatividade_status = f"INACTIVO PARCIAL (PI={pi_score})"
            inatividade_color = "#e67e22"
        else:
            inatividade_status = f"DISTRITO ACTIVO"
            inatividade_color = "#16a085"

        fig_historico = px.histogram(df_trabalho, x="Ano", nbins=10,
                                     title=f"EVOLUÇÃO HISTÓRICA DE LEVANTAMENTOS (FONTES)",
                                     labels={'count': 'Total Levantamentos'},
                                     text_auto=True, template="plotly_dark")
        fig_historico.update_traces(marker_color='#e67e22', opacity=0.8)
        fig_historico.update_layout(title_font_size=13, margin=dict(t=30), title_x=0.5, height=350)

        df_tabela = df_trabalho[[DATA_COL, CODIGO_COL, DISTRITO_COL]].copy()
        df_tabela[DATA_COL] = df_tabela[DATA_COL].dt.strftime('%Y-%m-%d')
        df_tabela = df_tabela.sort_values(DATA_COL, ascending=False).head(10).reset_index(drop=True)
        df_tabela.columns = ['Data', 'Código', 'Distrito']

        return html.Div([
            html.H4(f"DETALHE DO DISTRITO: {distrito.upper()} ({provincia.upper()})", className="mb-4 text-uppercase",
                    style={"color": "#f1c40f", "font-weight": "500"}),

            dbc.Row([
                dbc.Col(make_kpi_card("Total Levantamentos (3 INFRA)", f"{total_levantamentos_infra_distrito:,}",
                                      "fa-database", "#16a085"), md=3),
                dbc.Col(make_kpi_card("Qualidade: % Erros DAM (FONTES)", f"{percent_erros_dam_distrito:.1f}%",
                                      "fa-check-circle", "#f1c40f"), md=3),
                dbc.Col(make_kpi_card("Inactividade Média", df_inat_distrito['Inactividade_Media_Dias'], "fa-clock",
                                      "#e67e22"), md=3),
                dbc.Col(make_kpi_card("Pontos de Inactividade", inatividade_status, "fa-ban", inatividade_color), md=3),
            ], className="mb-4"),

            dbc.Row([
                dbc.Col(html.Div([
                    html.H5(f"🚨 DIAS PARADOS POR INFRAESTRUTURA (Limite: {DAYS_THRESHOLD} Dias)",
                            className="mb-3 text-center text-uppercase",
                            style={"color": "white", "font-weight": "500", "font-size": "13px"}),
                    dash_table.DataTable(
                        id='table-inatividade-distrito-detalhe',
                        columns=[
                            {"name": "Pontos (PI)", "id": INATIVIDADE_SCORE_NAME},
                            {"name": "Média Inactividade", "id": 'Inactividade_Media_Dias'},
                            {"name": "Fontes", "id": "Dias Parados (Fontes)"},
                            {"name": "SAA", "id": "Dias Parados (SAA)"},
                            {"name": "Comunidades", "id": "Dias Parados (Comunidades)"}
                        ],
                        data=[df_inat_distrito],
                        style_table={'height': '100%'},
                        style_header={'backgroundColor': '#34495e', 'fontWeight': 'bold', 'color': 'white',
                                      'border': '1px solid #1c2125'},
                        style_data={'backgroundColor': '#212529', 'color': 'white', 'border': '1px solid #1c2125'},
                        style_cell={'textAlign': 'center', 'fontSize': '12px', 'padding': '8px'},
                        style_data_conditional=style_data_conditional
                    )
                ], style={'height': '150px'}), md=12),
            ], className="mt-3"),

            dbc.Row([
                dbc.Col(dcc.Graph(figure=fig_historico, style={'height': UNIFORM_HEIGHT}), md=6),
                dbc.Col(
                    html.Div([
                        html.H5(f"📝 AMOSTRA DOS ÚLTIMOS REGISTOS (FONTES)", className="mb-3 text-center text-uppercase",
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

        # GRÁFICOS (Baseados apenas em Fontes para histórico)
        fig_anos = px.histogram(df_prov_fontes, x="Ano", nbins=10,
                                title=f"EVOLUÇÃO HISTÓRICA DE LEVANTAMENTOS (FONTES)",
                                labels={'count': 'Total Levantamentos'},
                                text_auto=True, template="plotly_dark")
        fig_anos.update_traces(marker_color='#e67e22', opacity=0.8)
        fig_anos.update_layout(title_font_size=13, margin=dict(t=30), title_x=0.5, height=350)

        df_ranking_distrito = df_prov_fontes.groupby(DISTRITO_COL).size().reset_index(name='Total')
        df_ranking_distrito = df_ranking_distrito.sort_values('Total', ascending=True)

        fig_ranking_dist = px.bar(df_ranking_distrito, x='Total', y=DISTRITO_COL, orientation='h',
                                  title=f"🥇 RANKING DE TOTAL DE LEVANTAMENTOS POR DISTRITO (FONTES)",
                                  color='Total', color_continuous_scale="Viridis",
                                  labels={"Total": "Total Levantamentos"},
                                  template="plotly_dark")
        fig_ranking_dist.update_layout(yaxis_title=None, xaxis_title="Total", margin=dict(t=30), title_font_size=13,
                                       title_x=0.5, height=350)

        # LAYOUT DE RESUMO DE PROVÍNCIA
        return html.Div([
            html.H4(f"RESUMO GERAL DA PROVÍNCIA: {provincia.upper()}", className="mb-4 text-uppercase",
                    style={"color": "#f1c40f", "font-weight": "500"}),

            dbc.Row([
                dbc.Col(make_kpi_card("Total Levantamentos (3 INFRA)", f"{total_levantamentos_infra:,}", "fa-database",
                                      "#16a085"), md=3),
                dbc.Col(make_kpi_card("% Distritos Activos (30d)", f"{percent_distritos_ativos:.1f}%", "fa-sitemap",
                                      "#3498db"), md=3),
                dbc.Col(make_kpi_card("Qualidade: % Erros DAM (FONTES)", f"{percent_erros_dam_prov:.1f}%",
                                      "fa-check-circle", "#f1c40f"), md=3),
                dbc.Col(
                    make_kpi_card(f"Distritos Sem Cadastro (Ano {TARGET_YEAR})", distritos_sem_cadastro_ano, "fa-fire",
                                  "#e74c3c"), md=3),
            ], className="mb-4"),

            dbc.Row([
                dbc.Col(dcc.Graph(figure=fig_anos, style={'height': UNIFORM_HEIGHT}), md=6),
                dbc.Col(dcc.Graph(figure=fig_ranking_dist, style={'height': UNIFORM_HEIGHT}), md=6),
            ], className="mt-3"),

            dbc.Row([
                dbc.Col(
                    html.Div([
                        html.H5(
                            f"🚨 PONTOS DE INACTIVIDADE (PI) - Distritos Sem Levantamento Recente (Limite: {DAYS_THRESHOLD} Dias)",
                            className="mb-3 text-center text-uppercase",
                            style={"color": "white", "font-weight": "500", "font-size": "13px"}),
                        dash_table.DataTable(
                            id='table-distrito-inatividade',
                            columns=[
                                {"name": "Distrito", "id": DISTRITO_COL},
                                {"name": "Pontos (PI)", "id": INATIVIDADE_SCORE_NAME},
                                {"name": "Média Inactividade", "id": 'Inactividade_Media_Dias'},
                                {"name": "Fontes", "id": "Dias Parados (Fontes)"},
                                {"name": "SAA", "id": "Dias Parados (SAA)"},
                                {"name": "Comunidades", "id": "Dias Parados (Comunidades)"}
                            ],
                            data=df_tabela_inatividade.to_dict('records'),
                            style_table={'height': '100%', 'overflowY': 'auto'},
                            style_header={'backgroundColor': '#34495e', 'fontWeight': 'bold', 'color': 'white',
                                          'border': '1px solid #1c2125'},
                            style_data={'backgroundColor': '#212529', 'color': 'white', 'border': '1px solid #1c2125'},
                            style_cell={'textAlign': 'center', 'fontSize': '12px', 'padding': '8px'},
                            style_data_conditional=style_data_conditional
                        )
                    ], style={'height': UNIFORM_HEIGHT}),
                    md=12
                ),
            ], className="mt-3")
        ])


@app.callback(Output("page-content", "children"), [Input("url", "pathname")])
def render_page_content(pathname):
    # Lógica do Dashboard Geral
    if pathname == "/":

        # CÁLCULOS TOTAIS MULTI-INFRA (Geral)
        total_fontes_geral = len(df_fontes)
        total_saa_geral = len(df_saa)
        total_comunidades_geral = len(df_comunidades)
        total_levantamentos_geral = total_fontes_geral + total_saa_geral + total_comunidades_geral

        # KPIS de Desempenho (Baseados em df_inatividade_geral)
        total_distritos_pais = df_inatividade_geral[DISTRITO_COL].nunique()
        total_provincias_pais = df_inatividade_geral[PROVINCIA_COL].nunique()

        # CÁLCULO KPI DE INATIVIDADE ANUAL CRÍTICA (GERAL) - NOVO FOCO PROVINCIAL

        # 1. Contar Distritos Sem Cadastro (Cadastro_Ano_Atual == False) por Província
        df_ranking_prov_sem_cadastro = df_inatividade_geral[~df_inatividade_geral['Cadastro_Ano_Atual']] \
            .groupby(PROVINCIA_COL).size().reset_index(name='Distritos Sem Cadastro')

        # Renomear para a exibição na tabela (usando o acento para melhor visualização)
        df_ranking_prov_tabela = df_ranking_prov_sem_cadastro.copy()
        df_ranking_prov_tabela.columns = ['Província', f'Distritos Sem Cadastro (Ano {TARGET_YEAR})']
        df_ranking_prov_tabela = df_ranking_prov_tabela.sort_values(f'Distritos Sem Cadastro (Ano {TARGET_YEAR})',
                                                                    ascending=False)

        # 2. Identificar Províncias Sem Cadastro Total (100% dos distritos inativos no ano)
        # Total de distritos por província
        df_distritos_por_prov = df_inatividade_geral.groupby(PROVINCIA_COL)[DISTRITO_COL].nunique().reset_index(
            name='Total Distritos')

        # Merge usando PROVINCIA_COL (Sem acento)
        df_analise_prov = pd.merge(df_distritos_por_prov, df_ranking_prov_sem_cadastro, on=PROVINCIA_COL,
                                   how='left').fillna(0)
        df_analise_prov['Distritos Sem Cadastro'] = df_analise_prov['Distritos Sem Cadastro'].astype(int)

        # Contagem: Se Total Distritos == Distritos Sem Cadastro, a província está 'morta' no ano
        provincias_sem_cadastro_anual = len(
            df_analise_prov[df_analise_prov['Total Distritos'] == df_analise_prov['Distritos Sem Cadastro']])

        # CÁLCULO KPI DE QUALIDADE (GERAL)
        total_erros_dam_geral = df_fontes[ERROR_FLAG_COL].sum() if not df_fontes.empty else 0
        percent_erros_dam_geral = (total_erros_dam_geral / total_fontes_geral) * 100 if total_fontes_geral else 0

        # KPI de COBERTURA (AGORA POR PROVÍNCIA)
        # Províncias ativas são aquelas que têm pelo menos um distrito com Max_Dias_Parados <= 30
        df_activos = df_inatividade_geral[df_inatividade_geral['Max_Dias_Parados'] <= DAYS_ACTIVE_THRESHOLD]
        provincias_activas = df_activos[PROVINCIA_COL].nunique()
        percent_provincias_activas = (provincias_activas / total_provincias_pais) * 100 if total_provincias_pais else 0

        # KPIS ANUAIS (Baseados em Fontes)

        # CORREÇÃO: Usar o valor mínimo de Max_Dias_Parados no df_inatividade_geral (garante a consistência multi-infra)
        if df_inatividade_geral.empty or df_inatividade_geral['Max_Dias_Parados'].min() == 9999:
            dias_desde_ult = "N/A"
        else:
            # O dia mais recente é o menor Max_Dias_Parados
            dias_desde_ult = int(df_inatividade_geral['Max_Dias_Parados'].min())

        df_mes_geral = df_2025.groupby('Mes').size().reset_index(name='Total_Levantamentos')

        # Figuras (gráficos)
        fig_ranking = px.bar(
            df_2025.groupby(PROVINCIA_COL).size().reset_index(name='Total').sort_values('Total', ascending=True),
            x='Total', y=PROVINCIA_COL, orientation='h',
            title=f"📈 RANKING DE TOTAL DE LEVANTAMENTOS POR PROVÍNCIA (ANO {TARGET_YEAR})",
            color='Total', color_continuous_scale="Plotly3",
            labels={"Total": "Total Levantamentos"},
            template="plotly_dark")
        fig_ranking.update_layout(yaxis_title=None, xaxis_title="Total", margin=dict(t=30), title_font_size=13,
                                  title_x=0.5)

        fig_consistencia_line = go.Figure(data=[go.Scatter(x=df_mes_geral['Mes'], y=df_mes_geral['Total_Levantamentos'],
                                                           mode='lines+markers', line=dict(color='#f1c40f', width=3),
                                                           marker=dict(size=8, symbol='circle'))])
        fig_consistencia_line.update_layout(
            title=f"📉 CONSISTÊNCIA MENSAL (TENDÊNCIA) DE LEVANTAMENTOS (FONTES)",
            xaxis_title="Mês", yaxis_title="Total Levantamentos", margin=dict(t=30),
            title_font_size=13, title_x=0.5, xaxis=dict(tickmode='array', tickvals=list(range(1, 13))),
            template="plotly_dark"
        )

        return html.Div([
            html.H4(f"RESUMO NACIONAL DE DESEMPENHO E CADASTRO", className="mb-4 text-uppercase",
                    style={"color": "#16a085", "font-weight": "500"}),

            # LINHA 1: KPIS TOTAIS MULTI-INFRA
            dbc.Row([
                dbc.Col(make_kpi_card("TOTAL LEVANTAMENTOS (3 INFRA)", f"{total_levantamentos_geral:,}", "fa-globe",
                                      "#16a085"), md=3),
                dbc.Col(make_kpi_card("Total Fontes", f"{total_fontes_geral:,}", "fa-tint", "#3498db"), md=3),
                dbc.Col(make_kpi_card("Total SAA", f"{total_saa_geral:,}", "fa-building", "#e67e22"), md=3),
                dbc.Col(make_kpi_card("Total Comunidades", f"{total_comunidades_geral:,}", "fa-users", "#8e44ad"),
                        md=3),
            ], className="mb-4"),

            # LINHA 2: KPIS DE DESEMPENHO (COBERTURA, QUALIDADE, PRIORIZAÇÃO, DATA)
            dbc.Row([
                dbc.Col(make_kpi_card("% Províncias Activas (30d)", f"{percent_provincias_activas:.1f}%", "fa-sitemap",
                                      "#3498db"), md=3),
                dbc.Col(make_kpi_card("Qualidade: % Erros DAM (FONTES)", f"{percent_erros_dam_geral:.1f}%",
                                      "fa-check-circle", "#f1c40f"), md=3),
                dbc.Col(
                    make_kpi_card(f"Províncias Sem Cadastro Total (Ano {TARGET_YEAR})", provincias_sem_cadastro_anual,
                                  "fa-fire", "#e74c3c"), md=3),
                dbc.Col(
                    make_kpi_card("Dias Desde Levantamento Recente", f"{dias_desde_ult} dias", "fa-bell", "#c0392b"),
                    md=3),
            ]),

            # GRÁFICOS E TABELAS
            dbc.Row([
                dbc.Col(
                    html.Div([
                        html.H5(f"🚨 TOP PROVÍNCIAS C/ MAIS DISTRITOS SEM CADASTRO (ANO {TARGET_YEAR})",
                                className="mb-3 text-center text-uppercase",
                                style={"color": "white", "font-weight": "500", "font-size": "13px"}),
                        dash_table.DataTable(
                            id='table-top-inatividade-provincial',
                            columns=[{"name": i, "id": i} for i in df_ranking_prov_tabela.columns],
                            data=df_ranking_prov_tabela.to_dict('records'),
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
                dbc.Col(dcc.Graph(figure=go.Figure(data=[go.Pie(
                    labels=['Fontes', 'SAA', 'Comunidades'],
                    values=[total_fontes_geral, total_saa_geral, total_comunidades_geral],
                    hole=.3,
                    marker=dict(colors=['#3498db', '#e67e22', '#8e44ad'])
                )]).update_layout(title_text='DISTRIBUIÇÃO DOS LEVANTAMENTOS (3 INFRA.)', title_font_size=13,
                                  title_x=0.5, template='plotly_dark'), style={'height': UNIFORM_HEIGHT}), md=6),

            ], className="mt-3")
        ])


    elif pathname == "/provincias":
        return html.Div([
            html.H4("ANÁLISE DE CADASTRO E LEVANTAMENTO POR PROVÍNCA E DISTRITO", className="mb-4 text-uppercase",
                    style={"color": "#16a085", "font-weight": "500"}),
            dbc.Row([
                dbc.Col(
                    dcc.Dropdown(
                        id="dropdown-provincia",
                        options=[{"label": prov, "value": prov} for prov in sorted(df[PROVINCIA_COL].unique())],
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=True)