import dash
from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from flask_caching import Cache
import plotly.graph_objects as go  
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
import traceback

# Initialize the Dash app with Bootstrap theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

# Initialize cache
cache = Cache(app.server, config={
  'CACHE_TYPE': 'filesystem',
  'CACHE_DIR': 'cache-directory'
})

# Constants
CSV_FILE = 'clinic_server_monitor.csv'
CPU_THRESHOLD = 90
MEMORY_THRESHOLD = 85
DISK_THRESHOLD = 85
REFRESH_INTERVAL = 60  # seconds

def log_error(error, context=""):
  with open('error_log.txt', 'a') as f:
      timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      f.write(f"[{timestamp}] {context}: {str(error)}\n")
      f.write(traceback.format_exc() + "\n")

@cache.memoize(timeout=REFRESH_INTERVAL)
def load_data():
  try:
      if os.path.exists(CSV_FILE):
          df = pd.read_csv(CSV_FILE, names=[
              'Title', 'ComputerName', 'CPUUsage', 'MemoryUsage', 
              'DiskUsage', 'NetworkUpload', 'NetworkDownload',
              'SmartCareStatus', 'SQLServerStatus', 'SmartLinkStatus',
              'ETIMSStatus', 'TIMSStatus', 'InternalIP', 'ExternalIP',
              'StaticIPs', 'Timestamp'
          ])
          
          df = df.rename(columns={
              'CPUUsage': 'CPU Usage (%)',
              'MemoryUsage': 'Memory Usage (%)',
              'DiskUsage': 'Disk Usage (%)',
              'NetworkUpload': 'Network Upload (Mbps)',
              'NetworkDownload': 'Network Download (Mbps)'
          })
          
          df['Timestamp'] = pd.to_datetime(df['Timestamp'])
          return df
      else:
          log_error(f"File not found: {CSV_FILE}", "Data Loading")
          return pd.DataFrame()
  except Exception as e:
      log_error(e, "Data Loading")
      return pd.DataFrame()

def create_summary_card(title, value, dark_mode=False):
  card_style = {
      'backgroundColor': '#121212' if dark_mode else 'white',
      'color': 'white' if dark_mode else 'black',
  }
  return dbc.Card(
      dbc.CardBody([
          html.H5(title, className="card-title"),
          html.H2(value, className="card-text"),
      ], style={'textAlign': 'center'}),
      color="light",
      outline=True,
      style=card_style
  )

def generate_overview(df, selected_computer, dark_mode=False):
  filtered_df = df[df['ComputerName'] == selected_computer]
  if not filtered_df.empty:
      latest = filtered_df.iloc[-1]
      metrics = {
          'CPU Usage': f"{latest['CPU Usage (%)']}%",
          'Memory Usage': f"{latest['Memory Usage (%)']}%",
          'Disk Usage': f"{latest['Disk Usage (%)']}%",
          'Net Upload': f"{latest['Network Upload (Mbps)']} Mbps",
          'Net Download': f"{latest['Network Download (Mbps)']} Mbps"
      }
  else:
      metrics = {k: "N/A" for k in ['CPU Usage', 'Memory Usage', 'Disk Usage', 'Net Upload', 'Net Download']}

  return dbc.Row([
      dbc.Col(create_summary_card(title, value, dark_mode), width=2 if 'Usage' in title else 3)
      for title, value in metrics.items()
  ], className="mb-4")

def generate_table(df, selected_computer, dark_mode=False):
  filtered_df = df[df['ComputerName'] == selected_computer]
  if filtered_df.empty:
      return html.Div("No data available.")

  # Specify the columns to keep
  columns_to_keep = [
      'SmartCareStatus', 'SQLServerStatus', 'SmartLinkStatus',
      'ETIMSStatus', 'TIMSStatus', 'InternalIP', 'ExternalIP', 'StaticIPs', 'Timestamp'
  ]

  style_header = {
      'backgroundColor': '#2C2C2C' if dark_mode else 'rgb(230, 230, 230)',
      'color': 'white' if dark_mode else 'black',
      'fontWeight': 'bold'
  }
  
  style_cell = {
      'backgroundColor': '#121212' if dark_mode else 'white',
      'color': 'white' if dark_mode else 'black',
      'textAlign': 'left'
  }

  return dash_table.DataTable(
      id='data-table',
      columns=[{"name": i, "id": i} for i in columns_to_keep],
      data=filtered_df[columns_to_keep].to_dict('records'),
      page_size=10,
      style_cell=style_cell,
      style_header=style_header,
      style_data_conditional=[
          {
              'if': {'filter_query': '{SmartCareStatus} = "Stopped"', 'column_id': 'SmartCareStatus'},
              'color': 'red'
          },
          {
              'if': {'filter_query': '{SmartCareStatus} = "Running"', 'column_id': 'SmartCareStatus'},
              'color': 'green'
          },
      ],
  )

def generate_figures(df, selected_computer, dark_mode=False):
  template = "plotly_dark" if dark_mode else "plotly_white"
  filtered_df = df[df['ComputerName'] == selected_computer]
  
  if filtered_df.empty:
      return [create_empty_figure("No data available", template) for _ in range(5)]
  
  figures = []
  for metric, title in [
      ('CPU Usage (%)', 'CPU Usage Over Time'),
      ('Memory Usage (%)', 'Memory Usage Over Time'),
      ('Disk Usage (%)', 'Disk Usage Over Time'),
      ('Network Upload (Mbps)', 'Network Upload Speed Over Time'),
      ('Network Download (Mbps)', 'Network Download Speed Over Time')
  ]:
      fig = go.Figure()
      fig.add_trace(go.Scatter(
          x=filtered_df['Timestamp'],
          y=filtered_df[metric],
          mode='lines+markers',
          name=metric,
          hovertemplate=f"{metric}: %{{y:.1f}}<br>Time: %{{x}}<extra></extra>"
      ))
      
      fig.update_layout(
          title=title,
          template=template,
          hovermode='x unified',
          showlegend=True,
          legend=dict(
              yanchor="top",
              y=0.99,
              xanchor="left",
              x=0.01
          )
      )
      figures.append(fig)
  
  return figures

def create_empty_figure(message, template):
  fig = px.line(title=message, template=template)
  fig.add_annotation(text=message, xref="paper", yref="paper", showarrow=False)
  return fig

def generate_alerts(df, selected_computer):
  alerts = []
  filtered_df = df[df['ComputerName'] == selected_computer]
  
  if not filtered_df.empty:
      last_cpu = filtered_df["CPU Usage (%)"].iloc[-1]
      last_memory = filtered_df["Memory Usage (%)"].iloc[-1]
      last_disk = filtered_df["Disk Usage (%)"].iloc[-1]
      last_static_ips = filtered_df["StaticIPs"].iloc[-1]
      if last_cpu > CPU_THRESHOLD:
          alerts.append(dbc.Alert(
              f"High CPU usage detected: {last_cpu}%",
              color="danger",
              dismissable=True
          ))

      if last_memory > MEMORY_THRESHOLD:
          alerts.append(dbc.Alert(
              f"High Memory usage detected: {last_memory}%",
              color="warning",
              dismissable=True
          ))
          
      if last_disk > DISK_THRESHOLD:
          alerts.append(dbc.Alert(
              f"High Disk usage detected: {last_disk}%",
              color="danger",
              dismissable=True
          ))
      # Check if the current static IP is the same as the previous one
      if not filtered_df["StaticIPs"].equals(filtered_df["StaticIPs"].shift()):
          alerts.append(dbc.Alert(
              f"Static IP has changed: {last_static_ips}",
              color="info",
              dismissable=True
            ))
  
  return alerts

def create_performance_indicators(df, selected_computer):
  filtered_df = df[df['ComputerName'] == selected_computer]
  if filtered_df.empty:
      return []
  
  cpu_avg = filtered_df['CPU Usage (%)'].mean()
  memory_avg = filtered_df['Memory Usage (%)'].mean()
  disk_avg = filtered_df['Disk Usage (%)'].mean()
  
  return [
      dbc.Alert([
          html.H4(f"{metric:.1f}%", className="alert-heading"),
          html.P(f"Average {name}")
      ], color=color)
      for metric, name, color in [
          (cpu_avg, "CPU Usage", "info"),
          (memory_avg, "Memory Usage", "warning"),
          (disk_avg, "Disk Usage", "primary")
      ]
  ]

def create_status_indicators(latest_data):
  services = [
      ('SmartCareStatus', 'SmartCare'),
      ('SQLServerStatus', 'SQL Server'),
      ('SmartLinkStatus', 'SmartLink'),
      ('ETIMSStatus', 'ETIMS'),
      ('TIMSStatus', 'TIMS')
  ]
  
  return dbc.Row([
      dbc.Col(
          dbc.Button([
              html.I(className=f"fas fa-circle {'text-success' if latest_data[status] == 'Running' else 'text-danger'}"),
              f" {name}"
          ], color="light", className="mb-2", size="sm"),
          width=4
      )
      for status, name in services
  ])

app.layout = dbc.Container([
  # Navigation Bar
  dbc.Navbar([
      dbc.Container([
          html.A(
              dbc.Row([
                  dbc.Col(html.I(className="fas fa-server mr-2")),
                  dbc.Col(dbc.NavbarBrand("Server Monitor", className="ml-2")),
              ], align="center"),
              href="#",
          ),
          dbc.NavbarToggler(id="navbar-toggler"),
          dbc.Collapse([
              dbc.Nav([
                  dbc.NavItem(dbc.NavLink("Dashboard", href="#")),
                  dbc.NavItem(dbc.NavLink("Settings", href="#")),
                  dbc.DropdownMenu(
                      [
                          dbc.DropdownMenuItem("Export CSV", id="btn-export-csv"),
                          dbc.DropdownMenuItem("Export Excel", id="btn-export-excel"),
                      ],
                      nav=True,
                      label="Export",
                  ),
                  dbc.NavItem(
                      dbc.Button("Toggle Theme", id="dark-mode-toggle", color="light", size="sm")
                  ),
              ])
          ], id="navbar-collapse", navbar=True),
      ])
  ], color="dark", dark=True, className="mb-4"),

  # Main Content
  dbc.Row([
      # Sidebar
      dbc.Col([
          dbc.Card([
              dbc.CardBody([
                  html.H5("Server Selection", className="mb-3"),
                  dcc.Dropdown(
                      id='computer-dropdown',
                      options=[],
                      clearable=False,
                      className="mb-3"
                  ),
                  html.H6("Quick Filters", className="mt-4"),
                  dbc.Checklist(
                      options=[
                          {"label": "High CPU Usage", "value": "cpu"},
                          {"label": "High Memory Usage", "value": "memory"},
                          {"label": "Service Issues", "value": "services"}
                      ],
                      id="status-filters",
                      switch=True,
                  ),
              ])
          ], className="mb-4"),
          
          html.Div(id="performance-indicators")
      ], width=12, lg=3),

      # Main Dashboard Area
      dbc.Col([
          # Alert Section
          html.Div(id="alerts", className="mb-4"),
          
          # Overview Cards
          html.Div(id="summary-cards", className="mb-4"),
          
          # Graphs Section
          dbc.Tabs([
              dbc.Tab([
                  dbc.Row([
                      dbc.Col(dcc.Graph(id='cpu-graph'), width=12, lg=6),
                      dbc.Col(dcc.Graph(id='memory-graph'), width=12, lg=6),
                  ]),
                  dbc.Row([
                      dbc.Col(dcc.Graph(id='disk-graph'), width=12),
                  ])
              ], label="System Metrics"),
              
              dbc.Tab([
                  dbc.Row([
                      dbc.Col(dcc.Graph(id='upload-graph'), width=12, lg=6),
                      dbc.Col(dcc.Graph(id='download-graph'), width=12, lg=6),
                  ])
              ], label="Network Metrics"),
              
              dbc.Tab([
                  html.Div(id="data-table-container")
              ], label="Detailed Data"),
          ]),
      ], width=12, lg=9),
  ]),

  dcc.Store(id='dark-mode-store', data=False),
  dcc.Interval(id='interval-component', interval=REFRESH_INTERVAL * 1000, n_intervals=0),
  dcc.Download(id="download-dataframe-csv"),
  dcc.Download(id="download-dataframe-excel"),
], fluid=True, id='main-container')


# Callbacks
@app.callback(
  Output("download-dataframe-csv", "data"),
  Input("btn-export-csv", "n_clicks"),
  State('computer-dropdown', 'value'),
  prevent_initial_call=True
)
def export_csv(n_clicks, selected_computer):
  if n_clicks is None:
      raise PreventUpdate
  df = load_data()
  filtered_df = df[df['ComputerName'] == selected_computer]
  return dcc.send_data_frame(filtered_df.to_csv, f"server_metrics_{selected_computer}.csv")

@app.callback(
  Output("performance-indicators", "children"),
  [Input('interval-component', 'n_intervals'),
   Input('computer-dropdown', 'value')]
)
def update_performance_indicators(n_intervals, selected_computer):
  df = load_data()
  return create_performance_indicators(df, selected_computer)

@app.callback(
  Output("navbar-collapse", "is_open"),
  [Input("navbar-toggler", "n_clicks")],
  [State("navbar-collapse", "is_open")],
)
def toggle_navbar_collapse(n, is_open):
  if n:
      return not is_open
  return is_open

@app.callback(
  [Output('computer-dropdown', 'options'),
   Output('computer-dropdown', 'value')],
  Input('interval-component', 'n_intervals')
)
def update_dropdown(n):
  df = load_data()
  options = [{'label': name, 'value': name} for name in df['ComputerName'].unique()]
  value = options[0]['value'] if options else None
  return options, value

@app.callback(
  [Output('main-container', 'style'),
   Output('dark-mode-store', 'data')],
  Input('dark-mode-toggle', 'n_clicks'),
  State('dark-mode-store', 'data')
)
def toggle_dark_mode(n_clicks, dark_mode):
  if n_clicks is None:
      return {}, False
  
  dark_mode = not dark_mode if dark_mode is not None else True
  style = {
      'backgroundColor': '#121212' if dark_mode else 'white',
      'color': 'white' if dark_mode else 'black',
      'minHeight': '100vh',
      'transition': 'all 0.3s ease-in-out'
  }
  
  return style, dark_mode

@app.callback(
  [Output('cpu-graph', 'figure'),
   Output('memory-graph', 'figure'),
   Output('disk-graph', 'figure'),
   Output('upload-graph', 'figure'),
   Output('download-graph', 'figure'),
   Output('summary-cards', 'children'),
   Output('alerts', 'children'),
   Output('data-table-container', 'children')],
  [Input('interval-component', 'n_intervals'),
   Input('computer-dropdown', 'value'),
   Input('dark-mode-store', 'data')]
)
def update_metrics(n_intervals, selected_computer, dark_mode):
  try:
      df = load_data()
      if df.empty or not selected_computer:
          raise ValueError("No data available")
      
      figures = generate_figures(df, selected_computer, dark_mode)
      overview = generate_overview(df, selected_computer, dark_mode)
      alerts = generate_alerts(df, selected_computer)
      table = generate_table(df, selected_computer, dark_mode)
      
      return *figures, overview, alerts, table
  
  except Exception as e:
      log_error(e, "Metrics Update")
      empty_figs = [create_empty_figure("Error loading data", "plotly_dark" if dark_mode else "plotly_white")] * 5
      return *empty_figs, html.Div("Error loading data"), [
          dbc.Alert("Error updating metrics", color="danger")
      ], html.Div("Error loading table")

if __name__ == '__main__':
  app.run_server(debug=True)




