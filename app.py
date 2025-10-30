# ============================================================
# 🌞 DASHBOARD EGAUGE MULTI-PROYECTOS
# Versión para Render (sin ngrok)
# ============================================================

import os
import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dash import Dash, dcc, html, Input, Output, State, MATCH, ALL
import dash
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import pytz
from time import sleep

# ----------------------------
# CONSTANTES Y CONFIG
# ----------------------------
TZ = pytz.timezone("America/Santo_Domingo")
REFRESH_SECONDS = 60
PORT = int(os.environ.get("PORT", 8050))

UMBRAL_POTENCIA = 10  # W, umbral de producción mínima para inversores

THEME_COLORS = {
    "light": {"bg": "#f4f6f9", "text": "#333333", "card": "#ffffff"},
    "dark": {"bg": "#121212", "text": "#f0f0f0", "card": "#1e1e1e"}
}

# ----------------------------
# FUNCIONES
# ----------------------------
def parse_xml_snapshot(r):
    xml = ET.fromstring(r.text)
    ts = datetime.fromtimestamp(int(xml.findtext("ts")), tz=timezone.utc)
    values = {}
    for row in xml.findall("r"):
        name = row.get("n", "Unknown")
        try:
            values[name] = float(row.findtext("i"))
        except:
            values[name] = np.nan
    return ts.astimezone(TZ), values

def fetch_egauge_snapshot(base_url, user, password):
    try:
        url = base_url + "cgi-bin/egauge?inst&tot"
        r = requests.get(url, auth=(user, password), timeout=10)
        if r.status_code == 200:
            return parse_xml_snapshot(r)
    except:
        pass
    return None, {}

def detect_alarms(data):
    alarms = []
    now = datetime.now(TZ)
    for name, val in data.items():
        if np.isnan(val):
            status = "No reporta"
        elif val <= UMBRAL_POTENCIA:
            status = "LOW VALUE"
        else:
            status = "OK"
        alarms.append({"name": name, "value": val, "status": status,
                       "last_seen": now.strftime("%Y-%m-%d %H:%M:%S")})
    return alarms

def build_table(alarms, colors):
    return dbc.Table([
        html.Thead(html.Tr([html.Th("Inversor"), html.Th("Estado"), html.Th("Potencia (W)"), html.Th("Última Lectura")])),
        html.Tbody([
            html.Tr([
                html.Td(a["name"]),
                html.Td(a["status"],
                        className="blink" if a["status"] != "OK" else "",
                        style={"color": "#2ecc71" if a["status"] == "OK" else "#ffffff",
                               "fontWeight": "bold"}),
                html.Td(a["value"]),
                html.Td(a["last_seen"])
            ]) for a in alarms
        ])
    ], bordered=True, hover=True, responsive=True,
       style={"backgroundColor": colors["card"], "color": colors["text"], "borderRadius": "10px", "padding": "10px"})

def get_project_card(project, theme="light"):
    colors = THEME_COLORS[theme]
    ts, data = fetch_egauge_snapshot(project["base_url"], project["user"], project["password"])
    if not data:
        return html.Div(f"⚠️ No hay datos para {project['name']}", style={"color": colors["text"]})

    df = pd.DataFrame(list(data.items()), columns=["Canal", "Potencia (W)"])
    alarms = detect_alarms(data)

    bar_colors = ["#2ecc71" if a["status"] in ["OK","No reporta"] else "#e74c3c" for a in alarms]

    fig = go.Figure(go.Bar(
        x=df["Canal"],
        y=df["Potencia (W)"],
        marker=dict(color=bar_colors, line=dict(color='rgb(50,50,50)', width=1.5)),
        hovertemplate='<b>%{x}</b><br>Potencia: %{y} W<extra></extra>',
        name="Potencia"
    ))
    fig.update_layout(
        title=f"{project['name']} - Lectura {ts.strftime('%Y-%m-%d %H:%M:%S')}",
        xaxis_title="Canal",
        yaxis_title="Potencia (W)",
        plot_bgcolor=colors["card"],
        paper_bgcolor=colors["card"],
        font=dict(family="Arial", size=14, color=colors["text"]),
        transition=dict(duration=700, easing="cubic-in-out")
    )

    table = build_table(alarms, colors)

    export_button = dbc.Button(
        "📥 Exportar CSV",
        id={"type": "btn_export", "index": project["name"]},
        color="primary",
        className="mt-2 mb-3 btn-lg"
    )

    return dbc.Card([
        dbc.CardHeader(html.H4(project["name"], style={"color": colors["text"]})),
        dbc.CardBody([
            html.H5("Producción y Consumo en Tiempo Real", style={"color": colors["text"]}),
            dcc.Graph(id={"type": "graph_project", "index": project["name"]}, figure=fig, animate=True),
            export_button,
            dcc.Download(id={"type": "download_csv", "index": project["name"]}),
            html.H5("🚨 Estado Actual del Sistema", style={"color": colors["text"], "marginTop":"20px"}),
            html.Div(id={"type": "table_project", "index": project["name"]}, children=table)
        ])
    ], className="shadow p-3 mb-4", style={"borderRadius":"12px", "backgroundColor": colors["card"]})

# ----------------------------
# DASHBOARD
# ----------------------------
app = Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])

app.layout = html.Div([
    dbc.Container([
        dbc.Row([
            dbc.Col(html.H2("🌞 MONITOR INDICADOR DE ALERTAS", className="text-center mt-3 mb-2"), width=10),
            dbc.Col([
                dbc.Switch(id="theme-switch", className="mt-4"),
                html.Span(id="theme-label", className="ms-2 fw-bold")
            ], width=2, className="d-flex align-items-center justify-content-end")
        ], align="center"),
        dcc.Store(id="theme-store", data="light", storage_type="local"),
        dcc.Store(
            id="store-projects",
            data=[
                {"name": "Proyecto_1",
                 "base_url": "https://egauge82252.egaug.es/632E1/",
                 "user": "RAASSOLAR",
                 "password": "R@@SSOL@R",
                 "lat": 18.4861,
                 "lon": -69.9312}
            ],
            storage_type="local"
        ),
        dbc.Row([
            dbc.Col([
                html.H5("Agregar Proyecto"),
                dbc.Input(id="input_name", placeholder="Nombre del proyecto", className="mb-2"),
                dbc.Input(id="input_url", placeholder="URL base", className="mb-2"),
                dbc.Input(id="input_user", placeholder="Usuario", className="mb-2"),
                dbc.Input(id="input_pass", placeholder="Password", type="password", className="mb-2"),
                dbc.Input(id="input_lat", placeholder="Latitud", type="number", className="mb-2"),
                dbc.Input(id="input_lon", placeholder="Longitud", type="number", className="mb-2"),
                dbc.Button("Agregar", id="btn_add", color="success", className="w-100 btn-lg"),
                html.Div(id="add_msg", className="text-success mt-2")
            ], xs=12, sm=12, md=4, lg=3, xl=3),
            dbc.Col([
                dbc.Tabs(id="tabs_projects", active_tab="Proyecto_1", className="mt-2"),
                html.Div(id="map-container", className="mt-3")
            ], xs=12, sm=12, md=8, lg=9, xl=9)
        ], className="g-3"),
        dcc.Interval(id="interval-refresh", interval=REFRESH_SECONDS*1000, n_intervals=0)
    ], fluid=True)
], id="main-container", style={"transition": "background-color 0.5s ease, color 0.5s ease"})

# ----------------------------
# CALLBACKS
# ----------------------------
@app.callback(
    Output("store-projects", "data"),
    Output("add_msg", "children"),
    Input("btn_add", "n_clicks"),
    State("input_name", "value"),
    State("input_url", "value"),
    State("input_user", "value"),
    State("input_pass", "value"),
    State("input_lat", "value"),
    State("input_lon", "value"),
    State("store-projects", "data"),
    prevent_initial_call=True
)
def add_project(n, name, url, user, password, lat, lon, projects_data):
    if not name or not url:
        return dash.no_update, "Debe completar nombre y URL"
    new_projects = projects_data.copy()
    new_projects.append({"name": name, "base_url": url, "user": user, "password": password, "lat": lat, "lon": lon})
    return new_projects, f"✅ Proyecto {name} agregado"

@app.callback(
    Output("tabs_projects", "children"),
    Output("map-container", "children"),
    Input("store-projects", "data"),
    Input("interval-refresh", "n_intervals"),
    Input("theme-store", "data")
)
def update_tabs_and_map(projects_data, n, theme):
    colors = THEME_COLORS[theme]
    tabs = [dbc.Tab(label=p["name"], tab_id=p["name"], children=get_project_card(p, theme)) for p in projects_data]

    lats, lons, names, colors_map, sizes = [], [], [], [], []
    for p in projects_data:
        ts, data = fetch_egauge_snapshot(p["base_url"], p["user"], p["password"])
        alarms = detect_alarms(data)
        has_inverter_error = any(a["status"] != "OK" for a in alarms)
        lats.append(p.get("lat"))
        lons.append(p.get("lon"))
        names.append(p["name"])
        colors_map.append("red" if has_inverter_error else "green")
        sizes.append(25 if has_inverter_error else 15)

    map_fig = go.Figure(go.Scattermapbox(
        lat=lats, lon=lons, mode='markers+text',
        marker=go.scattermapbox.Marker(size=sizes, color=colors_map),
        text=names, textposition="top right"
    ))
    map_fig.update_layout(
        mapbox_style="open-street-map",
        mapbox_zoom=5,
        mapbox_center={"lat": np.mean(lats) if lats else 18.5,
                       "lon": np.mean(lons) if lons else -69.9},
        margin={"l":0,"r":0,"t":0,"b":0}, height=400,
        paper_bgcolor=colors["card"], font=dict(color=colors["text"])
    )

    return tabs, dcc.Graph(figure=map_fig, animate=True)

@app.callback(
    Output({"type": "table_project", "index": MATCH}, "children"),
    Output({"type": "graph_project", "index": MATCH}, "figure"),
    Input("interval-refresh", "n_intervals"),
    State("store-projects", "data"),
    State({"type": "graph_project", "index": MATCH}, "id"),
    State("theme-store", "data")
)
def refresh_table_graph(n, projects_data, graph_id, theme):
    project_name = graph_id["index"]
    colors = THEME_COLORS[theme]
    for p in projects_data:
        if p["name"] == project_name:
            ts, data = fetch_egauge_snapshot(p["base_url"], p["user"], p["password"])
            if not data:
                return dash.no_update, dash.no_update
            df = pd.DataFrame(list(data.items()), columns=["Canal", "Potencia (W)"])
            alarms = detect_alarms(data)
            fig = go.Figure(go.Bar(
                x=df["Canal"], y=df["Potencia (W)"],
                marker=dict(color=["#2ecc71" if a["status"] in ["OK","No reporta"] else "#e74c3c" for a in alarms],
                            line=dict(color='rgb(50,50,50)', width=1.5)),
                hovertemplate='<b>%{x}</b><br>Potencia: %{y} W<extra></extra>', name="Potencia"
            ))
            fig.update_layout(
                title=f"{project_name} - Lectura {ts.strftime('%Y-%m-%d %H:%M:%S')}",
                xaxis_title="Canal", yaxis_title="Potencia (W)",
                plot_bgcolor=colors["card"], paper_bgcolor=colors["card"],
                font=dict(family="Arial", size=14, color=colors["text"]),
                transition=dict(duration=700, easing="cubic-in-out")
            )
            return build_table(alarms, colors), fig
    return dash.no_update, dash.no_update

@app.callback(
    Output({"type": "download_csv", "index": ALL}, "data"),
    Input({"type": "btn_export", "index": ALL}, "n_clicks"),
    State("store-projects", "data"),
    prevent_initial_call=True
)
def export_csv(n_clicks_list, projects_data):
    ctx = dash.callback_context
    if not ctx.triggered:
        return [dash.no_update] * len(projects_data)
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    proj_name = eval(triggered_id)["index"]

    for p in projects_data:
        if p["name"] == proj_name:
            ts, data = fetch_egauge_snapshot(p["base_url"], p["user"], p["password"])
            if not data:
                return [dash.no_update] * len(projects_data)
            df = pd.DataFrame(list(data.items()), columns=["Canal", "Potencia (W)"])
            return [
                dcc.send_data_frame(df.to_csv, f"{proj_name}_{ts.strftime('%Y%m%d_%H%M%S')}.csv")
                if p["name"] == proj_name else dash.no_update
                for p in projects_data
            ]

@app.callback(Output("theme-switch","value"), Input("theme-store","data"))
def load_saved_theme(saved_theme): return saved_theme=="dark"

@app.callback(
    Output("theme-store","data"), Output("main-container","style"),
    Input("theme-switch","value")
)
def toggle_theme(is_dark):
    theme = "dark" if is_dark else "light"
    colors = THEME_COLORS[theme]
    style = {"backgroundColor": colors["bg"], "color": colors["text"], "transition": "all 0.5s ease"}
    return theme, style

@app.callback(
    Output("theme-label","children"), Output("theme-label","style"),
    Input("theme-switch","value")
)
def update_theme_label(is_dark):
    if is_dark: return "🌙 Modo oscuro", {"color":"#f0f0f0"}
    else: return "☀️ Modo claro", {"color":"#333333"}

app.clientside_callback(
    """
    function(n_intervals){
        var style = document.createElement('style');
        style.innerHTML = `
        @keyframes blink {0% { background-color: #e74c3c; } 50% { background-color: #ffffff; } 100% { background-color: #e74c3c; }}
        .blink { animation: blink 1s infinite; color: white !important; font-weight: bold; }
        `;
        document.head.appendChild(style);
        return '';
    }
    """,
    Output("interval-refresh", "children"),
    Input("interval-refresh", "n_intervals")
)

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=PORT, debug=False)

