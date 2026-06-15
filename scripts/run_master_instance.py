import argparse
import threading
import time
import master

parser = argparse.ArgumentParser()
parser.add_argument('--host', default='127.0.0.1')
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--server-id', default='Master')
parser.add_argument('--neighbors', default='')
parser.add_argument('--initial-tasks', type=int, default=0)
parser.add_argument('--capacity', type=int, default=100)
parser.add_argument('--metrics-port', type=int, default=8000)
parser.add_argument('--dashboard-host', default='nuted-ia.dev')
parser.add_argument('--dashboard-port', type=int, default=443)
parser.add_argument('--dashboard-tls', action='store_true', default=True)
parser.add_argument('--dashboard-sni', default='nuted-ia.dev')
parser.add_argument('--dashboard-interval', type=int, default=5)
args = parser.parse_args()

# Configure master module globals
master.SERVER_UUID = args.server_id
master.CAPACITY = args.capacity
master.METRICS_PORT = args.metrics_port
master.TCP_SOCKET_HOST = args.dashboard_host
master.TCP_SOCKET_PORT = args.dashboard_port
master.TCP_SOCKET_TLS = args.dashboard_tls
master.TCP_SOCKET_SNI = args.dashboard_sni
master.FARM_REPORT_INTERVAL = args.dashboard_interval
# Parse neighbors as comma-separated addresses; assign dummy ids
if args.neighbors:
    master.NEIGHBORS = [(f"nb{i+1}", addr) for i, addr in enumerate(args.neighbors.split(','))]
else:
    master.NEIGHBORS = []

# Start components
threading.Thread(target=master.start_server, args=(args.host, args.port), daemon=True).start()
threading.Thread(target=master.monitor_load_loop, args=(args.host, args.port), daemon=True).start()
threading.Thread(target=master.outbox_worker_loop, daemon=True).start()
threading.Thread(target=master.start_metrics_server, args=(args.metrics_port,), daemon=True).start()
# Start dashboard reporter
threading.Thread(target=master.dashboard_reporter_loop, daemon=True).start()

# Populate initial tasks
if args.initial_tasks:
    master.populate_initial_tasks(args.initial_tasks)

# Keep alive
while True:
    time.sleep(1)
