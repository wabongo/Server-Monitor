import dash
from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import plotly.express as px
import os

# Initialize the Dash app with Bootstrap theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server  # For deployment purposes if needed

# Path to your CSV file
CSV_FILE = 'clinic_server_monitor.csv'

# Function to load data from the CSV file
def load_data():
    if os.path.exists(CSV_FILE):
        # Add header names explicitly
        df = pd.read_csv(CSV_FILE, names=[
            'Title',
            'ComputerName', 'CPUUsage', 'MemoryUsage', 
            'DiskUsage', 'NetworkUpload', 'NetworkDownload',
            'SmartCareStatus', 'SQLServerStatus', 'SmartLinkStatus',
            'ETIMSStatus', 'TIMSStatus', 'InternalIP', 'ExternalIP',
            'StaticIPs', 'Timestamp'
        ])
        # Rename columns to match dashboard expectations
        df = df.rename(columns={
            'CPUUsage': 'CPU Usage (%)',
            'MemoryUsage': 'Memory Usage (%)',
            'DiskUsage': 'Disk Usage (%)',
            'NetworkUpload': 'Network Upload (Mbps)',
            'NetworkDownload': 'Network Download (Mbps)'
        })
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame()

# Function to create summary cards
def create_summary_card(title, value):
  return dbc.Card(
      dbc.CardBody(
          [
              html.H5(title, className="card-title"),
              html.H2(value, className="card-text"),
          ],
          style={'textAlign': 'center'}
      ),
      color="light",
      outline=True,
  )

# Function to generate the overview section
def generate_overview(df):
  if not df.empty:
      latest = df.iloc[-1]
      cpu_usage = f"{latest['CPU Usage (%)']}%"
      memory_usage = f"{latest['Memory Usage (%)']}%"
      disk_usage = f"{latest['Disk Usage (%)']}%"
      network_upload = f"{latest['Network Upload (Mbps)']} Mbps"
      network_download = f"{latest['Network Download (Mbps)']} Mbps"
  else:
      cpu_usage = memory_usage = disk_usage = network_upload = network_download = "N/A"

  overview = dbc.Row([
      dbc.Col(create_summary_card("CPU Usage", cpu_usage), width=2),
      dbc.Col(create_summary_card("Memory Usage", memory_usage), width=2),
      dbc.Col(create_summary_card("Disk Usage", disk_usage), width=2),
      dbc.Col(create_summary_card("Net Upload", network_upload), width=3),
      dbc.Col(create_summary_card("Net Download", network_download), width=3),
  ], className="mb-4")
  return overview

# Function to generate the detailed metrics table
def generate_table(df):
  if not df.empty:
      table = dash_table.DataTable(
          id='data-table',
          columns=[{"name": i, "id": i} for i in df.columns],
          data=df.to_dict('records'),
          page_size=10,
          style_cell={'textAlign': 'left'},
          style_header={
              'backgroundColor': 'rgb(230, 230, 230)',
              'fontWeight': 'bold'
          },
          style_data_conditional=[
              {
                  'if': {'filter_query': '{SmartCare Status} = "Stopped"', 'column_id': 'SmartCare Status'},
                  'color': 'red'
              },
              {
                  'if': {'filter_query': '{SmartCare Status} = "Running"', 'column_id': 'SmartCare Status'},
                  'color': 'green'
              },
              # Add similar conditions for other status columns
          ],
      )
  else:
      table = html.Div("No data available.")
  return table

# Function to generate the graphs
def generate_figures(df):
  if not df.empty:
      cpu_fig = px.line(df, x='Timestamp', y='CPU Usage (%)', title='CPU Usage Over Time')
      memory_fig = px.line(df, x='Timestamp', y='Memory Usage (%)', title='Memory Usage Over Time')
      disk_fig = px.line(df, x='Timestamp', y='Disk Usage (%)', title='Disk Usage Over Time')
      upload_fig = px.line(df, x='Timestamp', y='Network Upload (Mbps)', title='Network Upload Speed Over Time')
      download_fig = px.line(df, x='Timestamp', y='Network Download (Mbps)', title='Network Download Speed Over Time')
  else:
      # Create empty figures with annotations
      cpu_fig = px.line(title='CPU Usage Over Time')
      cpu_fig.add_annotation(text="No data available", xref="paper", yref="paper", showarrow=False)

      memory_fig = px.line(title='Memory Usage Over Time')
      memory_fig.add_annotation(text="No data available", xref="paper", yref="paper", showarrow=False)

      disk_fig = px.line(title='Disk Usage Over Time')
      disk_fig.add_annotation(text="No data available", xref="paper", yref="paper", showarrow=False)

      upload_fig = px.line(title='Network Upload Speed Over Time')
      upload_fig.add_annotation(text="No data available", xref="paper", yref="paper", showarrow=False)

      download_fig = px.line(title='Network Download Speed Over Time')
      download_fig.add_annotation(text="No data available", xref="paper", yref="paper", showarrow=False)

  return cpu_fig, memory_fig, disk_fig, upload_fig, download_fig

# Function to generate alerts based on thresholds
def generate_alerts(df):
  alerts = []
  CPU_THRESHOLD = 90
  MEMORY_THRESHOLD = 85

  if not df.empty:
      last_cpu = df["CPU Usage (%)"].iloc[-1]
      last_memory = df["Memory Usage (%)"].iloc[-1]

      if last_cpu > CPU_THRESHOLD:
          alerts.append(dbc.Alert(f"High CPU usage detected: {last_cpu}%", color="danger", dismissable=True))

      if last_memory > MEMORY_THRESHOLD:
          alerts.append(dbc.Alert(f"High Memory usage detected: {last_memory}%", color="warning", dismissable=True))
  return alerts

# Load data for initial page load
df = load_data()
overview = generate_overview(df)
table = generate_table(df)
cpu_fig, memory_fig, disk_fig, upload_fig, download_fig = generate_figures(df)
alerts = generate_alerts(df)

# Define app layout
app.layout = dbc.Container([
  html.H1("Server Status Dashboard", className="my-4"),

  # Overview Section
  html.Div(id='summary-cards', children=overview),

  # Alerts Section
  html.Div(id='alerts', children=alerts),

  # Detailed Metrics Table
  html.H2("Detailed Metrics", className="my-4"),
  table,

  # Graphs and Charts
  html.H2("Usage Trends Over Time", className="my-4"),
  dbc.Row([
      dbc.Col(dcc.Graph(id='cpu-graph', figure=cpu_fig), width=6),
      dbc.Col(dcc.Graph(id='memory-graph', figure=memory_fig), width=6)
  ]),
  dbc.Row([
      dbc.Col(dcc.Graph(id='disk-graph', figure=disk_fig), width=6),
      dbc.Col(dcc.Graph(id='upload-graph', figure=upload_fig), width=6)
  ]),
  dbc.Row([
      dbc.Col(dcc.Graph(id='download-graph', figure=download_fig), width=6)
  ]),

  # Interval component for updating data
  dcc.Interval(
      id='interval-component',
      interval=60*1000,  # Update every 1 minute
      n_intervals=0
  )
], fluid=True)

# Callback to update components periodically
@app.callback(
  [
      Output('cpu-graph', 'figure'),
      Output('memory-graph', 'figure'),
      Output('disk-graph', 'figure'),
      Output('upload-graph', 'figure'),
      Output('download-graph', 'figure'),
      Output('summary-cards', 'children'),
      Output('alerts', 'children'),
      Output('data-table', 'data')
  ],
  [Input('interval-component', 'n_intervals')]
)
def update_metrics(n_intervals):
  df = load_data()
  # Update components with new data
  overview = generate_overview(df)
  alerts = generate_alerts(df)
  cpu_fig, memory_fig, disk_fig, upload_fig, download_fig = generate_figures(df)

  if not df.empty:
      data = df.to_dict('records')
  else:
      data = []

  return cpu_fig, memory_fig, disk_fig, upload_fig, download_fig, overview, alerts, data

# Run the app
if __name__ == '__main__':
  app.run_server(debug=True)