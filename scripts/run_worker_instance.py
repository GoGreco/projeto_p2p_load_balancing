import argparse
import worker

parser = argparse.ArgumentParser()
parser.add_argument('--host', default='127.0.0.1')
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--heartbeat', type=int, default=1)
args = parser.parse_args()

worker.MASTER_HOST = args.host
worker.MASTER_PORT = args.port
worker.HEARTBEAT_INTERVAL = args.heartbeat

worker.connect_and_run()
