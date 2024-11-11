import ssl
import aiohttp
import psutil
import time
import logging
import os
import signal
import asyncio
import socket
import json
import subprocess
import platform
import re
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from msal import ConfidentialClientApplication
from datetime import datetime
import csv
from logging.handlers import RotatingFileHandler

# Load environment variables
load_dotenv()

# Configuration
CENTRAL_SERVER_URL = os.getenv('CENTRAL_SERVER_URL', 'https://your-server-url.com/api')
INTERVAL = int(os.getenv('INTERVAL', 60))  # Adjusted interval to 60 seconds
MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
BACKOFF_FACTOR = float(os.getenv('BACKOFF_FACTOR', 1.5))
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'

# SharePoint Configuration
SHAREPOINT_SITE_ID = os.getenv('SHAREPOINT_SITE_ID')
SHAREPOINT_LIST_ID = os.getenv('SHAREPOINT_LIST_ID')
TENANT_ID = os.getenv('TENANT_ID')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

# Application-specific configurations (Process names)
APPLICATIONS = {
  'smartcare': 'SmartCareProcessName',  # Replace with actual process name
  'sql_server': 'sqlservr',
  'smartlink': 'SmartLinkProcessName',  # Replace with actual process name
  'etims': 'ETIMSProcessName',          # Replace with actual process name
  'tims': 'TIMSProcessName',            # Replace with actual process name
}

# Set up logging with rotation
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(
  'clinic_server_monitor.log',
  maxBytes=5*1024*1024,  # 5 MB
  backupCount=5
)
formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Get the computer name
computer_name = socket.gethostname()

# CSV file path
CSV_FILE_PATH = 'clinic_server_monitor.csv'

def write_to_csv(data: Dict[str, Any]) -> None:
  """Write collected data to a CSV file with rotation."""
  fieldnames = [
      "Title",
      "ComputerName",
      "CPUUsage",
      "MemoryUsage",
      "DiskUsage",
      "NetworkUpload",
      "NetworkDownload",
      "SmartCareStatus",
      "SQLServerStatus",
      "SmartLinkStatus",
      "ETIMSStatus",
      "TIMSStatus",
      "InternalIP",
      "ExternalIP",
      "StaticIPs",
      "Timestamp"
  ]
  
  file_exists = os.path.isfile(CSV_FILE_PATH)
  
  with open(CSV_FILE_PATH, mode='a', newline='') as file:
      writer = csv.DictWriter(file, fieldnames=fieldnames)
      
      if not file_exists:
          writer.writeheader()
      
      row = {
          "Title": f"Server Status - {data['general_info']['computer_name']}",
          "ComputerName": data['general_info']['computer_name'],
          "CPUUsage": data['general_info']['cpu_usage'],
          "MemoryUsage": data['general_info']['memory_usage'],
          "DiskUsage": data['general_info']['disk_usage'],
          "NetworkUpload": data['general_info']['network_data']['upload_speed_mbps'],
          "NetworkDownload": data['general_info']['network_data']['download_speed_mbps'],
          "SmartCareStatus": "Running" if data['application_info']['smartcare']['status'] else "Stopped",
          "SQLServerStatus": "Running" if data['application_info']['sql_server']['status'] else "Stopped",
          "SmartLinkStatus": "Running" if data['application_info']['smartlink']['status'] else "Stopped",
          "ETIMSStatus": "Running" if data['application_info']['etims']['status'] else "Stopped",
          "TIMSStatus": "Running" if data['application_info']['tims']['status'] else "Stopped",
          "InternalIP": data['general_info']['ip_addresses']['internal_ip'],
          "ExternalIP": data['general_info']['ip_addresses']['external_ip'],
          "StaticIPs": ', '.join(data['general_info']['ip_addresses']['static_ips']),
          "Timestamp": datetime.fromtimestamp(data['timestamp']).isoformat()
      }
      writer.writerow(row)

def check_process_running(process_name: str) -> bool:
  """Check if a process with the given name is running."""
  for proc in psutil.process_iter(['name']):
      try:
          if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
              return True
      except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
          continue
  return False

def get_ip_addresses() -> Dict[str, Any]:
  """Retrieve IP addresses of the machine, including static IP on Windows."""
  ip_info = {
      'internal_ip': None,
      'external_ip': None,
      'static_ips': []
  }
  
  try:
      # Internal IP
      s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      s.connect(("8.8.8.8", 80))
      ip_info['internal_ip'] = s.getsockname()[0]
      s.close()
  
      if platform.system() == "Windows":
          ip_info['static_ips'] = get_windows_static_ips()
  
      # External IP
      ip_info['external_ip'] = get_external_ip()
  except Exception as e:
      logging.error(f'Error retrieving IP addresses: {str(e)}')
      
  return ip_info

def get_windows_static_ips() -> List[str]:
  """Get static IP addresses on Windows if configured."""
  static_ips = []
  try:
      result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True, check=True)
      output = result.stdout

      adapters = output.split('\n\n')
      for adapter in adapters:
          if 'DHCP Enabled. . . . . . . . . . . : No' in adapter:
              matches = re.findall(r'IPv4 Address.*?: ([\d\.]+)', adapter)
              if matches:
                  static_ips.extend(matches)
      return static_ips
  except subprocess.CalledProcessError as e:
      logging.error(f'Error running ipconfig command: {str(e)}')
  except Exception as e:
      logging.error(f'Error getting Windows static IPs: {str(e)}')
  return static_ips

def get_external_ip() -> Optional[str]:
  """Get the external IP address."""
  try:
      # This method requires Internet access. Adjust as needed.
      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
          s.connect(("ifconfig.me", 80))
          request = "GET /ip HTTP/1.1\r\nHost: ifconfig.me\r\n\r\n"
          s.sendall(request.encode())
          response = s.recv(4096).decode()
          ip = re.search(r'(\d+\.\d+\.\d+\.\d+)', response)
          if ip:
              return ip.group(0)
  except Exception as e:
      logging.error(f'Error retrieving external IP address: {str(e)}')
  return 'External IP not available'

def calculate_speed(bytes_count: int, duration: float) -> float:
  """Calculate speed in Mbps from bytes and duration in seconds."""
  if duration > 0:
      return (bytes_count * 8) / (1_000_000 * duration)  # Convert bytes to megabits
  return 0.0

async def collect_system_info() -> Optional[Dict[str, Any]]:
  """Collect system and application-specific information."""
  try:
      # Record initial network stats
      net_io_start = psutil.net_io_counters()
      start_time = time.time()
      
      # Collect other system stats
      cpu_usage = psutil.cpu_percent(interval=1)
      memory = psutil.virtual_memory().percent
      disk = psutil.disk_usage('/').percent
      
      # Wait for a short duration to measure network speed
      await asyncio.sleep(1)  # Sleep for 1 second
      duration = time.time() - start_time
      
      # Record network stats after duration
      net_io_end = psutil.net_io_counters()
      
      bytes_sent = net_io_end.bytes_sent - net_io_start.bytes_sent
      bytes_recv = net_io_end.bytes_recv - net_io_start.bytes_recv
      
      # Calculate upload and download speeds
      upload_speed = calculate_speed(bytes_sent, duration)
      download_speed = calculate_speed(bytes_recv, duration)
      
      application_info = {}

      for app_name, process_name in APPLICATIONS.items():
          status = check_process_running(process_name)
          application_info[app_name] = {
              'status': status,
              'process_name': process_name,
          }
      
      system_info = {
          'general_info': {
              'computer_name': computer_name,
              'cpu_usage': cpu_usage,
              'memory_usage': memory,
              'disk_usage': disk,
              'network_data': {
                  'upload_speed_mbps': f"{upload_speed:.2f} Mbps",
                  'download_speed_mbps': f"{download_speed:.2f} Mbps",
              },
              'ip_addresses': get_ip_addresses(),
          },
          'application_info': application_info,
          'timestamp': time.time()
      }
      
      if DEBUG_MODE:
          logging.debug('DEBUG MODE: Logging system information.')
          logging.debug(f'System information collected: {json.dumps(system_info, indent=2)}')
      else:
          logging.info('System information collected successfully')
      
      return system_info
  except Exception as e:
      logging.exception('Error collecting system information')
      return None

async def send_data_to_server(data: Dict[str, Any]) -> None:
  """Send data to the central server with retry logic."""
  retries = 0
  while retries < MAX_RETRIES:
      try:
          ssl_context = ssl.create_default_context()
          async with aiohttp.ClientSession() as session:
              async with session.post(CENTRAL_SERVER_URL, json=data, ssl=ssl_context) as response:
                  if response.status == 200:
                      logging.info('Data sent to central server successfully')
                      return
                  else:
                      logging.warning(f'Failed to send data. Status code: {response.status}')
      except aiohttp.ClientError as e:
          retries += 1
          wait_time = BACKOFF_FACTOR ** retries
          logging.error(f'Error sending data to server: {str(e)}. Retry {retries}/{MAX_RETRIES} in {wait_time:.2f} seconds')
          await asyncio.sleep(wait_time)
      except Exception as e:
          logging.exception('Unexpected error during data transmission')
          return

  logging.critical('Max retries reached. Failed to send data')

async def send_data_to_sharepoint(data: Dict[str, Any]) -> None:
  """Send data to SharePoint list."""
  try:
      # Initialize the MSAL app
      app = ConfidentialClientApplication(
          CLIENT_ID,
          authority=f"https://login.microsoftonline.com/{TENANT_ID}",
          client_credential=CLIENT_SECRET,
      )

      # Acquire a token
      result = app.acquire_token_silent(["https://graph.microsoft.com/.default"], account=None)
      if not result:
          result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

      if "access_token" in result:
          # Prepare the data for SharePoint list
          list_item = {
              "fields": {
                  "Title": f"Server Status - {data['general_info']['computer_name']}",
                  "ComputerName": data['general_info']['computer_name'],
                  "CPUUsage": data['general_info']['cpu_usage'],
                  "MemoryUsage": data['general_info']['memory_usage'],
                  "DiskUsage": data['general_info']['disk_usage'],
                  "NetworkUpload": data['general_info']['network_data']['upload_speed_mbps'],
                  "NetworkDownload": data['general_info']['network_data']['download_speed_mbps'],
                  "SmartCareStatus": "Running" if data['application_info']['smartcare']['status'] else "Stopped",
                  "SQLServerStatus": "Running" if data['application_info']['sql_server']['status'] else "Stopped",
                  "SmartLinkStatus": "Running" if data['application_info']['smartlink']['status'] else "Stopped",
                  "ETIMSStatus": "Running" if data['application_info']['etims']['status'] else "Stopped",
                  "TIMSStatus": "Running" if data['application_info']['tims']['status'] else "Stopped",
                  "InternalIP": data['general_info']['ip_addresses']['internal_ip'],
                  "ExternalIP": data['general_info']['ip_addresses']['external_ip'],
                  "StaticIPs": ', '.join(data['general_info']['ip_addresses']['static_ips']),
                  "Timestamp": datetime.fromtimestamp(data['timestamp']).isoformat(),
              }
          }

          # Send data to SharePoint
          graph_endpoint = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_SITE_ID}/lists/{SHAREPOINT_LIST_ID}/items"
          headers = {
              "Authorization": f"Bearer {result['access_token']}",
              "Content-Type": "application/json"
          }

          async with aiohttp.ClientSession() as session:
              async with session.post(graph_endpoint, json=list_item, headers=headers) as response:
                  if response.status == 201:
                      logging.info("Data sent to SharePoint successfully")
                  elif response.status == 429:
                      # Handle throttling
                      retry_after = int(response.headers.get('Retry-After', '1'))
                      logging.warning(f"Throttled by SharePoint API. Retrying after {retry_after} seconds.")
                      await asyncio.sleep(retry_after)
                      await send_data_to_sharepoint(data)
                  else:
                      error_text = await response.text()
                      logging.error(f"Failed to send data to SharePoint. Status code: {response.status}. Error: {error_text}")
      else:
          logging.error(f"Failed to acquire token: {result.get('error')}")
  except Exception as e:
      logging.exception("Error sending data to SharePoint")

async def main_loop() -> None:
  """Main execution loop."""
  while True:
      try:
          system_info = await collect_system_info()
          if system_info:
              # Write system info to CSV
              write_to_csv(system_info)
              
              # Send data concurrently
              await asyncio.gather(
                  send_data_to_server(system_info),
                  send_data_to_sharepoint(system_info)
              )
          else:
              logging.error('System information is None')
          await asyncio.sleep(INTERVAL)
      except Exception as e:
          logging.exception('Unexpected error in main loop')
          await asyncio.sleep(INTERVAL)

def signal_handler(signum: int, frame: Any) -> None:
  """Handle termination signals."""
  logging.info('Received signal to terminate. Shutting down gracefully...')
  for task in asyncio.all_tasks():
      task.cancel()
  asyncio.get_event_loop().stop()

def cleanup_old_csv_files(retention_days: int = 30) -> None:
  """Delete CSV files older than retention period."""
  try:
      now = datetime.now()
      file_modified_time = datetime.fromtimestamp(os.path.getmtime(CSV_FILE_PATH))
      if (now - file_modified_time).days > retention_days:
          os.remove(CSV_FILE_PATH)
          logging.info(f'Old CSV file {CSV_FILE_PATH} deleted due to retention policy.')
  except Exception as e:
      logging.error(f'Error during CSV file cleanup: {str(e)}')

if __name__ == '__main__':
  if DEBUG_MODE:
      logging.warning('Running in DEBUG MODE. Sensitive information may be logged.')
  else:
      logging.getLogger().setLevel(logging.INFO)
  
  # Register signal handlers
  signal.signal(signal.SIGINT, signal_handler)
  signal.signal(signal.SIGTERM, signal_handler)

  # Clean up old CSV files
  cleanup_old_csv_files()

  # Run the main loop
  try:
      asyncio.run(main_loop())
  except asyncio.CancelledError:
      pass
  except Exception as e:
      logging.exception('An error occurred while running the main loop')
  finally:
      logging.info('Clinic server monitor shut down')