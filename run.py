#!/usr/bin/env python3
"""One-command local setup and run for the Capstone Intelligent Vehicle Loan Advisor.

    python run.py                 # set up, install, build, run, open the browser
    python run.py --dev           # Next.js dev server (hot reload) instead of a production build
    python run.py --test          # also run backend tests and the frontend type-check
    python run.py --skip-install  # reuse existing .venv and node_modules
    python run.py --no-browser    # do not open a browser window
    python run.py --reset-db      # delete the local SQLite demo database first (re-seeds current policies)
    python run.py --no-streamlit  # only the Next.js dashboard

What it does:
1. Checks Python (3.12+) and Node.js (20.9+) and that the ports are free.
2. Creates .env from .env.example with random local secrets (an existing .env is never overwritten).
3. Backend: creates backend/.venv, installs dependencies, checks the saved model and vector index (rebuilds
   them if missing), and applies migrations and seed data (SQLite).
4. Frontend: npm ci, then a production build.
5. Starts the API, the Next.js dashboard and the Streamlit app, waits until healthy, then opens the browser.
Press Ctrl+C to stop everything."""

import argparse
import os
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
STREAMLIT = ROOT / "streamlit_app"
WINDOWS = platform.system() == "Windows"
VENV_PYTHON = BACKEND / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
MIN_PYTHON = (3, 12)
MIN_NODE = (20, 9)


def step(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def fail(message: str) -> None:
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("   $", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        fail(f"command failed with exit code {result.returncode}: {' '.join(cmd)}")


def check_prerequisites(ports: list[int]) -> str:
    step("Checking prerequisites")
    if sys.version_info < MIN_PYTHON:
        fail(f"Python {'.'.join(map(str, MIN_PYTHON))}+ is required (found {platform.python_version()})")
    npm = shutil.which("npm")
    node = shutil.which("node")
    if not npm or not node:
        fail("Node.js and npm are required: https://nodejs.org/")
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    if tuple(int(p) for p in version.split(".")[:2]) < MIN_NODE:
        fail(f"Node.js {'.'.join(map(str, MIN_NODE))}+ is required (found {version})")
    for port in ports:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                fail(f"port {port} is already in use; stop the other process or pass a different port")
    print(f"   Python {platform.python_version()}, Node.js {version}, ports {ports} free")
    return npm


def ensure_env_file() -> dict[str, str]:
    step("Preparing .env")
    env_file, example = ROOT / ".env", ROOT / ".env.example"
    if not env_file.exists():
        generated = {"DEV_BFF_SHARED_SECRET": secrets.token_hex(24),
                     "POSTGRES_OWNER_PASSWORD": secrets.token_hex(16),
                     "POSTGRES_APP_PASSWORD": secrets.token_hex(16)}
        lines = []
        for line in example.read_text("utf-8").splitlines():
            key = line.split("=", 1)[0].strip()
            lines.append(f"{key}={generated[key]}" if key in generated and "=" in line else line)
        env_file.write_text("\n".join(lines) + "\n", "utf-8")
        print("   created .env with random local secrets (add GEMINI_API_KEY to enable AI features)")
    else:
        print("   using existing .env")
    values: dict[str, str] = {}
    for line in env_file.read_text("utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            if value.strip():
                values[key.strip()] = value.strip()
    return values


def setup_backend(skip_install: bool, settings: dict[str, str], test: bool, reset_db: bool) -> None:
    step("Backend: virtual environment and dependencies")
    if not VENV_PYTHON.exists():
        run([sys.executable, "-m", "venv", ".venv"], BACKEND)
    if not skip_install:
        run([str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], BACKEND)
        # The hashed lockfiles are generated for Linux containers; Windows resolves from the pinned inputs.
        requirements = "requirements-dev.in" if WINDOWS else "requirements-dev.lock"
        run([str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "-r", requirements], BACKEND)
        run([str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "-r", str(STREAMLIT / "requirements.txt")],
            BACKEND)
    step("Backend: eligibility model and vector index")
    if not (ROOT / "models" / "eligibility_model.joblib").exists():
        if not (ROOT / "data" / "raw" / "loan_applications.csv").exists():
            run([str(VENV_PYTHON), str(ROOT / "data" / "generate_loans.py")], ROOT)
        run([str(VENV_PYTHON), "-m", "app.ml.train"], BACKEND)
    if not (ROOT / "vectorstore" / "local" / "manifest.json").exists():
        run([str(VENV_PYTHON), "-m", "app.rag.ingest"], BACKEND, backend_env(settings))
    print("   model and vector index present")
    if reset_db:
        for suffix in ("", "-wal", "-shm"):
            (BACKEND / "data" / f"vla.db{suffix}").unlink(missing_ok=True)
        print("   removed the local SQLite demo database")
    step("Backend: database migrations and seed data")
    run([str(VENV_PYTHON), "-m", "app.ops.migrate"], BACKEND, backend_env(settings))
    if test:
        step("Backend: tests")
        run([str(VENV_PYTHON), "-m", "pytest", "-q"], BACKEND)


def setup_frontend(npm: str, skip_install: bool, dev: bool, test: bool) -> None:
    if not skip_install or not (FRONTEND / "node_modules").exists():
        step("Frontend: dependencies")
        run([npm, "ci", "--no-audit", "--no-fund"], FRONTEND)
    if test:
        step("Frontend: type-check")
        run([npm, "run", "typecheck"], FRONTEND)
    if dev:
        return
    step("Frontend: production build")
    run([npm, "run", "build"], FRONTEND, {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"})
    # output: "standalone" needs the static assets copied next to its server.
    standalone = FRONTEND / ".next" / "standalone"
    shutil.copytree(FRONTEND / ".next" / "static", standalone / ".next" / "static", dirs_exist_ok=True)
    if (FRONTEND / "public").exists():
        shutil.copytree(FRONTEND / "public", standalone / "public", dirs_exist_ok=True)


def backend_env(settings: dict[str, str]) -> dict[str, str]:
    return {**os.environ, **settings, "PYTHONUNBUFFERED": "1"}


def frontend_env(settings: dict[str, str], backend_port: int, frontend_port: int) -> dict[str, str]:
    return {**os.environ, **settings, "BACKEND_URL": f"http://127.0.0.1:{backend_port}",
            "PORT": str(frontend_port), "HOSTNAME": "127.0.0.1", "NEXT_TELEMETRY_DISABLED": "1",
            # Plain http on localhost: browsers would drop Secure cookies.
            "INSECURE_COOKIES": "true",
            "APP_BASE_URL": settings.get("APP_BASE_URL", f"http://localhost:{frontend_port}")}


def start(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0
    return subprocess.Popen(cmd, cwd=cwd, env=env, creationflags=flags, start_new_session=not WINDOWS)


def wait_for(url: str, name: str, procs: list[subprocess.Popen[bytes]], timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if any(p.poll() is not None for p in procs):
            fail(f"{name} exited during startup; see the output above")
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status < 500:
                    print(f"   {name} is up: {url}")
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1)
    fail(f"{name} did not become ready within {timeout_s}s ({url})")


def stop(procs: list[subprocess.Popen[bytes]]) -> None:
    for p in procs:
        if p.poll() is None:
            if WINDOWS:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(p.pid, signal.SIGTERM)
    for p in procs:
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dev", action="store_true", help="run the Next.js dev server instead of a production build")
    parser.add_argument("--test", action="store_true", help="run backend tests and the frontend type-check")
    parser.add_argument("--skip-install", action="store_true", help="reuse installed dependencies")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--reset-db", action="store_true", help="delete the local SQLite demo database first")
    parser.add_argument("--no-streamlit", action="store_true", help="do not start the Streamlit app")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--streamlit-port", type=int, default=8501)
    args = parser.parse_args()

    ports = [args.backend_port, args.frontend_port] + ([] if args.no_streamlit else [args.streamlit_port])
    npm = check_prerequisites(ports)
    settings = ensure_env_file()
    setup_backend(args.skip_install, settings, args.test, args.reset_db)
    setup_frontend(npm, args.skip_install, args.dev, args.test)

    step("Starting the application")
    api_cmd = [str(VENV_PYTHON), "-m", "uvicorn", "app.main:create_app", "--factory",
               "--host", "127.0.0.1", "--port", str(args.backend_port)]
    web_cmd = ([npm, "run", "dev", "--", "-p", str(args.frontend_port)] if args.dev
               else ["node", str(Path(".next") / "standalone" / "server.js")])
    procs = [start(api_cmd, BACKEND, backend_env(settings))]
    try:
        wait_for(f"http://127.0.0.1:{args.backend_port}/healthz", "API", procs)
        procs.append(start(web_cmd, FRONTEND, frontend_env(settings, args.backend_port, args.frontend_port)))
        url = f"http://localhost:{args.frontend_port}"
        wait_for(f"{url}/login", "Web app", procs)
        streamlit_url = f"http://localhost:{args.streamlit_port}"
        if not args.no_streamlit:
            streamlit_cmd = [str(VENV_PYTHON), "-m", "streamlit", "run", "app.py", "--server.port",
                             str(args.streamlit_port), "--server.address", "127.0.0.1"]
            procs.append(start(streamlit_cmd, STREAMLIT, {**backend_env(settings),
                                                          "API_URL": f"http://127.0.0.1:{args.backend_port}"}))
            wait_for(f"http://127.0.0.1:{args.streamlit_port}/_stcore/health", "Streamlit app", procs)
        print(f"\n   Capstone dashboard (Next.js): {url}")
        if not args.no_streamlit:
            print(f"   Capstone advisor (Streamlit): {streamlit_url}")
        print(f"   API docs: http://127.0.0.1:{args.backend_port}/docs")
        print("   Sign in with a demo identity, e.g. Alice (applicant) or Priya (policy admin). Ctrl+C to stop.\n")
        if not args.no_browser:
            webbrowser.open(url)
            if not args.no_streamlit:
                webbrowser.open(streamlit_url)
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("\nA process exited; shutting down.")
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop(procs)


if __name__ == "__main__":
    main()
