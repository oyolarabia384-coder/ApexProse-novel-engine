import os
import subprocess
import sys
import time
import socket
import shutil


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
MIN_PYTHON = (3, 10)
MIN_NODE = (18, 0)
NODE_PATH = None
NPM_PATH = None


def run_async(cmd, cwd):
    return subprocess.Popen(cmd, cwd=cwd)


def run_sync(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True)


def venv_bin_path(venv_dir, name):
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    return os.path.join(venv_dir, bin_dir, name)


def ensure_python_version():
    if sys.version_info < MIN_PYTHON:
        print(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required.")
        sys.exit(1)


def parse_node_version(text):
    raw = text.strip().lstrip("v")
    parts = raw.split(".")
    if len(parts) < 2:
        return (0, 0)
    return (int(parts[0]), int(parts[1]))


def _find_executable(name):
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        for suffix in (".cmd", ".exe", ".bat"):
            found = shutil.which(f"{name}{suffix}")
            if found:
                return found
    return None


def ensure_node_version():
    global NODE_PATH, NPM_PATH
    node_path = _find_executable("node")
    if not node_path:
        print("Node.js not found. Please install Node.js 18+.")
        sys.exit(1)
    try:
        result = subprocess.run([node_path, "--version"], capture_output=True, text=True, check=True)
        node_version = parse_node_version(result.stdout)
    except subprocess.CalledProcessError:
        print("Failed to detect Node.js version.")
        sys.exit(1)
    if node_version < MIN_NODE:
        print("Node.js 18+ is required.")
        sys.exit(1)
    npm_path = _find_executable("npm")
    if not npm_path:
        print("npm not found. Please install Node.js with npm.")
        sys.exit(1)
    try:
        subprocess.run([npm_path, "--version"], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        print("Failed to detect npm version.")
        sys.exit(1)
    NODE_PATH = node_path
    NPM_PATH = npm_path


def ensure_port_available(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        print(f"Port {port} is already in use. Please free the port and retry.")
        return False
    finally:
        sock.close()


def ensure_backend_env():
    venv_dir = os.path.join(BACKEND_DIR, ".venv")
    if not os.path.exists(venv_dir):
        run_sync([sys.executable, "-m", "venv", ".venv"], BACKEND_DIR)
    pip_path = venv_bin_path(venv_dir, "pip")
    python_path = venv_bin_path(venv_dir, "python")
    run_sync([python_path, "-m", "pip", "install", "-r", "requirements.txt"], BACKEND_DIR)


def ensure_frontend_deps():
    npm_path = NPM_PATH or _find_executable("npm")
    if not npm_path:
        print("npm not found. Please install Node.js with npm.")
        sys.exit(1)
    run_sync([npm_path, "install"], FRONTEND_DIR)


def main():
    ensure_python_version()
    ensure_node_version()
    if not ensure_port_available(8000):
        return
    ensure_backend_env()
    ensure_frontend_deps()

    python_path = venv_bin_path(os.path.join(BACKEND_DIR, ".venv"), "python")
    backend_cmd = [python_path, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
    npm_path = NPM_PATH or _find_executable("npm")
    if not npm_path:
        print("npm not found. Please install Node.js with npm.")
        return
    frontend_cmd = [npm_path, "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

    backend_proc = run_async(backend_cmd, BACKEND_DIR)
    time.sleep(1)
    frontend_proc = run_async(frontend_cmd, FRONTEND_DIR)

    print("Backend and frontend started.")
    print("Backend: http://0.0.0.0:8000")
    print("Frontend: http://0.0.0.0:5173")
    print("Press Ctrl+C to stop.")

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        backend_proc.terminate()
        frontend_proc.terminate()


if __name__ == "__main__":
    main()
