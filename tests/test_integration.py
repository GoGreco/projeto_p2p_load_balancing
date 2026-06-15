import subprocess
import time
import os
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PY = 'python3'

def wait_for_metric(url, metric, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=1)
            if r.status_code == 200 and metric in r.text:
                # parse value
                for line in r.text.splitlines():
                    if line.startswith(metric):
                        val = int(line.split()[-1])
                        return val
        except Exception:
            pass
        time.sleep(0.5)
    return None


def test_borrow_flow():
    # start master B
    p2 = 7002
    metrics_b = 9002
    env = os.environ.copy()
    env['PYTHONPATH'] = ROOT
    pb = subprocess.Popen([PY, os.path.join(ROOT, 'scripts', 'run_master_instance.py'), '--port', str(p2), '--server-id', 'MasterB', '--initial-tasks', '0', '--metrics-port', str(metrics_b)], env=env)
    # wait until worker registers on master B (local_workers >= 1)
    url_b = f'http://127.0.0.1:{metrics_b}/metrics'
    def wait_for_metric_local_quiet(url, metric, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with urllib.request.urlopen(url, timeout=1) as r:
                    text = r.read().decode('utf-8')
            except Exception:
                text = ''
            if metric in text:
                for line in text.splitlines():
                    if line.startswith(metric):
                        try:
                            return int(line.split()[-1])
                        except Exception:
                            return None
            time.sleep(0.5)
        return None

    val_b = wait_for_metric_local_quiet(url_b, 'p2p_local_workers', timeout=12)
    if not val_b or val_b < 1:
        # proceed anyway but it's likely to fail
        time.sleep(1)
    # start a worker connected to master B
    pw = subprocess.Popen([PY, os.path.join(ROOT, 'scripts', 'run_worker_instance.py'), '--port', str(p2)], env=env)
    time.sleep(0.5)
    # start master A overloaded and pointing to master B
    p1 = 7001
    metrics_a = 9001
    # set capacity small so initial tasks overload
    pa = subprocess.Popen([PY, os.path.join(ROOT, 'scripts', 'run_master_instance.py'), '--port', str(p1), '--server-id', 'MasterA', '--initial-tasks', '20', '--capacity', '1', '--neighbors', f'127.0.0.1:{p2}', '--metrics-port', str(metrics_a)], env=env)
    # wait for borrowed worker metric on master A
    url_a = f'http://127.0.0.1:{metrics_a}/metrics'
    # use urllib to avoid external dependency
    def fetch(url):
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                return r.read().decode('utf-8')
        except Exception:
            return ''

    def wait_for_metric_local(url, metric, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            text = fetch(url)
            if metric in text:
                for line in text.splitlines():
                    if line.startswith(metric):
                        try:
                            return int(line.split()[-1])
                        except Exception:
                            return None
            time.sleep(0.5)
        return None

    val = wait_for_metric_local(url_a, 'p2p_borrowed_workers', timeout=30)
    # cleanup
    pb.terminate()
    pw.terminate()
    pa.terminate()
    assert val is not None and val >= 1

if __name__ == '__main__':
    test_borrow_flow()
    print('ok')
