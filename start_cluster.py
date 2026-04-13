import subprocess
import sys
import time
import os
import signal

BASE = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

processes: list[subprocess.Popen] = []


def spawn(script: str, env_extra: dict) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(env_extra)
    p = subprocess.Popen(
        [PYTHON, script],
        env=env,
        text=True,
    )
    processes.append(p)
    return p

def main() -> None:
    print("=" * 60)
    print("  Iniciando cluster distribuído — 2 Masters + 5 Workers")
    print("=" * 60)

    master_script = os.path.join(BASE, "master", "master.py")
    worker_script = os.path.join(BASE, "worker", "worker.py")

    print("\n[1/3] Iniciando Master_A em :9000 ...")
    spawn(master_script, {
        "MASTER_UUID":        "Master_A",
        "MASTER_PORT":        "9000",
        "MASTER_PEERS":       "192.168.56.1:9001",
        "OVERLOAD_THRESHOLD": "4",
        "TASK_GEN_INTERVAL":  "2",
    })
    time.sleep(1)

    print("[2/3] Iniciando Master_B em :9001 ...")
    spawn(master_script, {
        "MASTER_UUID":        "Master_B",
        "MASTER_PORT":        "9001",
        "MASTER_PEERS":       "192.168.56.1:9000",
        "OVERLOAD_THRESHOLD": "4",
        "TASK_GEN_INTERVAL":  "3",
    })
    time.sleep(1)

    print("[3/3] Iniciando Workers ...")
    for i in range(1, 4):
        spawn(worker_script, {
            "WORKER_UUID": f"Worker_A{i}",
            "MASTER_HOST": "192.168.56.1",
            "MASTER_PORT": "9000",
        })
        time.sleep(0.3)
        
    for i in range(1, 3):
        spawn(worker_script, {
            "WORKER_UUID": f"Worker_B{i}",
            "MASTER_HOST": "192.168.56.1",
            "MASTER_PORT": "9001",
        })
        time.sleep(0.3)

    print("\nCluster iniciado! Pressione Ctrl+C para encerrar.\n")

    try:
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"Processo PID {p.pid} encerrou inesperadamente (código {p.returncode})")
    except KeyboardInterrupt:
        print("\n\nEncerrando cluster...")
        for p in processes:
            try:
                p.terminate()
            except Exception:
                pass
        time.sleep(1)
        for p in processes:
            try:
                p.kill()
            except Exception:
                pass
        print("Cluster encerrado.")


if __name__ == "__main__":
    main()
