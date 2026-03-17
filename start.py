import os
import subprocess
import sys
import time


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")


def run(cmd, cwd):
    return subprocess.Popen(cmd, cwd=cwd, shell=True)


def ensure_backend_env():
    venv_dir = os.path.join(BACKEND_DIR, ".venv")
    if not os.path.exists(venv_dir):
        run("python -m venv .venv", BACKEND_DIR).wait()
    pip_path = os.path.join(venv_dir, "Scripts", "pip")
    run(f"{pip_path} install -r requirements.txt", BACKEND_DIR).wait()


def ensure_frontend_deps():
    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    if not os.path.exists(node_modules):
        run("npm install", FRONTEND_DIR).wait()


def main():
    ensure_backend_env()
    ensure_frontend_deps()

    backend_cmd = os.path.join(BACKEND_DIR, ".venv", "Scripts", "python") + " -m uvicorn app:app --port 8000"
    frontend_cmd = "npm run dev -- --host 127.0.0.1"

    backend_proc = run(backend_cmd, BACKEND_DIR)
    time.sleep(1)
    frontend_proc = run(frontend_cmd, FRONTEND_DIR)

    print("Backend and frontend started.")
    print("Backend: http://localhost:8000")
    print("Frontend: http://localhost:5173")
    print("Press Ctrl+C to stop.")

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        backend_proc.terminate()
        frontend_proc.terminate()


if __name__ == "__main__":
    main()
