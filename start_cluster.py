"""
start_cluster.py — inicia Master + Workers na MESMA máquina (para testes locais).

Para rodar em máquinas separadas, use os scripts individuais:
  • Máquina Master:  python master/master.py
  • Máquina Worker:  python worker/worker.py

Veja o README.md para instruções completas de configuração em rede.
"""
import subprocess
import sys
import time
import os

BASE   = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

processes: list[subprocess.Popen] = []


def spawn(script: str, env_extra: dict) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(env_extra)
    p = subprocess.Popen([PYTHON, script], env=env, text=True)
    processes.append(p)
    return p


def main() -> None:
    print("=" * 60)
    print("  Cluster LOCAL — 1 Master + 2 Workers (mesma máquina)")
    print("  Para rede real, rode cada processo separadamente.")
    print("=" * 60)

    master_script = os.path.join(BASE, "master", "master.py")
    worker_script = os.path.join(BASE, "worker", "worker.py")

    # Master escuta em 0.0.0.0:9000
    # MASTER_PUBLIC_IP = 127.0.0.1 pois tudo está na mesma máquina
    print("\n[1/2] Iniciando Master_A em 0.0.0.0:9000 ...")
    spawn(master_script, {
        "MASTER_UUID":        "Master_A",
        "MASTER_PORT":        "9000",
        "MASTER_PUBLIC_IP":   "127.0.0.1",   # IP anunciado aos Workers
        "MASTER_PEERS":       "",             # sem peers neste exemplo
        "OVERLOAD_THRESHOLD": "4",
        "TASK_GEN_INTERVAL":  "2",
    })
    time.sleep(1.5)  # aguarda o Master subir antes dos Workers

    print("[2/2] Iniciando Workers (conectando em 127.0.0.1:9000) ...")
    for i in range(1, 3):
        spawn(worker_script, {
            "WORKER_UUID": f"Worker_A{i}",
            "MASTER_HOST": "127.0.0.1",   # IP do Master nesta máquina
            "MASTER_PORT": "9000",
        })
        time.sleep(0.3)

    print("\nCluster iniciado! Pressione Ctrl+C para encerrar.\n")

    try:
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"[AVISO] Processo PID {p.pid} encerrou (código {p.returncode})")
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