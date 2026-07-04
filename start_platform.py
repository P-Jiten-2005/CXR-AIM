"""
CXR-AIM Platform Launcher
Provisions the environment, installs dependencies, and orchestrates the
FastAPI backend + Next.js frontend with a clean, unified console.
"""

import os
import re
import sys
import time
import signal
import threading
import subprocess
from datetime import datetime

# ---------------------------------------------------------------------------
#  Terminal styling
# ---------------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
TEAL = "\033[38;5;43m"
GRAY = "\033[90m"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _supports_unicode() -> bool:
    enc = (sys.stdout.encoding or "").lower()
    return "utf" in enc


def _enable_terminal():
    """Enable ANSI escape sequences and UTF-8 output on Windows consoles."""
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _visible_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


UNICODE = True  # finalized in main()

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SPINNER_ASCII = "|/-\\"


def ts() -> str:
    return f"{GRAY}{datetime.now().strftime('%H:%M:%S')}{RESET}"


# ---------------------------------------------------------------------------
#  Banner & panels
# ---------------------------------------------------------------------------

def print_banner():
    art = r"""
   ██████╗██╗  ██╗██████╗        █████╗ ██╗███╗   ███╗
  ██╔════╝╚██╗██╔╝██╔══██╗      ██╔══██╗██║████╗ ████║
  ██║      ╚███╔╝ ██████╔╝█████╗███████║██║██╔████╔██║
  ██║      ██╔██╗ ██╔══██╗╚════╝██╔══██║██║██║╚██╔╝██║
  ╚██████╗██╔╝ ██╗██║  ██║      ██║  ██║██║██║ ╚═╝ ██║
   ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝      ╚═╝  ╚═╝╚═╝╚═╝     ╚═╝
"""
    ascii_art = r"""
   _____  __   __  _____            _    ___  __  __
  / ____| \ \ / / |  __ \    /\    | |  |_ _||  \/  |
 | |       \ V /  | |__) |  /  \   | |   | | | |\/| |
 | |        > <   |  _  /  / /\ \  | |   | | | |  | |
 | |____   / . \  | | \ \ / ____ \ | |  _| |_| |  | |
  \_____| /_/ \_\ |_|  \_/_/    \_\|_| |_____|_|  |_|
"""
    print(f"{TEAL}{BOLD}{art if UNICODE else ascii_art}{RESET}")
    sub = "AI Marksmanship Analysis Platform"
    print(f"{GRAY}        {sub}{RESET}")
    print(f"{GRAY}        {'─' * len(sub)}{RESET}\n")


def panel(lines, border_color=TEAL):
    inner = max(_visible_len(l) for l in lines)
    if UNICODE:
        tl, tr, bl, br, h, v = "╭", "╮", "╰", "╯", "─", "│"
    else:
        tl, tr, bl, br, h, v = "+", "+", "+", "+", "-", "|"
    bar = h * (inner + 4)
    print(f"{border_color}{tl}{bar}{tr}{RESET}")
    for l in lines:
        pad = " " * (inner - _visible_len(l))
        print(f"{border_color}{v}{RESET}  {l}{pad}  {border_color}{v}{RESET}")
    print(f"{border_color}{bl}{bar}{br}{RESET}")


# ---------------------------------------------------------------------------
#  Step runner with spinner
# ---------------------------------------------------------------------------

def run_cmd(cmd, cwd=None, shell=False):
    """Run a command, capturing combined output. Returns (returncode, output)."""
    res = subprocess.run(
        cmd, cwd=cwd, shell=shell,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    return res.returncode, res.stdout or ""


def step(label, func):
    """Animate a spinner while `func` (returns (rc, output)) runs; report the result."""
    result = {}
    done = threading.Event()

    def worker():
        try:
            result["value"] = func()
        except Exception as e:
            result["value"] = (1, str(e))
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()

    frames = SPINNER_FRAMES if UNICODE else SPINNER_ASCII
    i = 0
    start = time.time()
    while not done.is_set():
        sys.stdout.write(f"\r  {CYAN}{frames[i % len(frames)]}{RESET} {label}{DIM} …{RESET}   ")
        sys.stdout.flush()
        i += 1
        time.sleep(0.08)

    rc, output = result.get("value", (1, ""))
    elapsed = time.time() - start
    mark = f"{GREEN}✓{RESET}" if rc == 0 else f"{RED}✗{RESET}"
    if not UNICODE:
        mark = f"{GREEN}OK{RESET}" if rc == 0 else f"{RED}!!{RESET}"
    sys.stdout.write(f"\r  {mark} {label}{GRAY}  ({elapsed:.1f}s){RESET}{' ' * 12}\n")
    sys.stdout.flush()

    if rc != 0:
        tail = "\n".join(output.strip().splitlines()[-12:])
        if tail:
            print(f"{DIM}{tail}{RESET}")
    return rc


# ---------------------------------------------------------------------------
#  Subprocess management
# ---------------------------------------------------------------------------

processes = []


def log_reader(process, tag, color, ready_event=None, ready_patterns=()):
    """Stream a child process's output with a clean colored prefix."""
    try:
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            line = line.rstrip()
            if not line:
                continue
            print(f"{ts()} {color}{tag:<9}{RESET}{GRAY}│{RESET} {line}", flush=True)
            if ready_event and not ready_event.is_set():
                if any(p in line for p in ready_patterns):
                    ready_event.set()
    except Exception as e:
        print(f"{ts()} {RED}{tag:<9}{RESET}{GRAY}│{RESET} log stream closed: {e}", flush=True)


def start_service(name, tag, color, cmd, cwd, shell, ready_patterns):
    proc = subprocess.Popen(
        cmd, cwd=cwd, shell=shell,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    processes.append(proc)
    ready = threading.Event()
    threading.Thread(
        target=log_reader, args=(proc, tag, color, ready, ready_patterns), daemon=True
    ).start()
    return ready


# ---------------------------------------------------------------------------
#  Provisioning
# ---------------------------------------------------------------------------

def provision_backend():
    backend_dir = os.path.join(os.getcwd(), "backend")
    venv_dir = os.path.join(backend_dir, "venv")
    if os.name == "nt":
        python_exe = os.path.join(venv_dir, "Scripts", "python.exe")
        pip_exe = os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        python_exe = os.path.join(venv_dir, "bin", "python")
        pip_exe = os.path.join(venv_dir, "bin", "pip")

    if not os.path.exists(venv_dir):
        step("Creating Python virtual environment",
             lambda: run_cmd([sys.executable, "-m", "venv", "venv"], cwd=backend_dir))
        step("Upgrading pip",
             lambda: run_cmd([python_exe, "-m", "pip", "install", "--upgrade", "-q", "pip"], cwd=backend_dir))
    else:
        print(f"  {GREEN}✓{RESET} Python virtual environment {GRAY}(cached){RESET}")

    root_req = os.path.join(os.getcwd(), "requirements.txt")
    step("Verifying backend dependencies",
         lambda: run_cmd([pip_exe, "install", "-q", "-r", root_req]))
    return python_exe


def provision_frontend():
    frontend_dir = os.path.join(os.getcwd(), "frontend")
    node_modules = os.path.join(frontend_dir, "node_modules")
    shell_arg = os.name == "nt"
    if not os.path.exists(node_modules):
        step("Installing frontend packages (npm)",
             lambda: run_cmd("npm install --no-fund --no-audit", cwd=frontend_dir, shell=shell_arg))
    else:
        print(f"  {GREEN}✓{RESET} Frontend packages {GRAY}(cached){RESET}")


# ---------------------------------------------------------------------------
#  Lifecycle
# ---------------------------------------------------------------------------

def wait_ready(label, event, timeout=60):
    frames = SPINNER_FRAMES if UNICODE else SPINNER_ASCII
    i = 0
    start = time.time()
    while not event.is_set() and (time.time() - start) < timeout:
        sys.stdout.write(f"\r  {CYAN}{frames[i % len(frames)]}{RESET} {label}{DIM} …{RESET}   ")
        sys.stdout.flush()
        i += 1
        time.sleep(0.1)
    ok = event.is_set()
    mark = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}…{RESET}"
    state = "" if ok else f"{YELLOW}(still starting){RESET}"
    sys.stdout.write(f"\r  {mark} {label} {state}{' ' * 16}\n")
    sys.stdout.flush()
    return ok


def clean_exit(*_):
    print(f"\n{YELLOW}⏻ Shutting down CXR-AIM platform…{RESET}")
    for p in processes:
        try:
            if os.name == "nt":
                subprocess.run(f"taskkill /F /T /PID {p.pid}",
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                p.terminate()
                p.wait(timeout=3)
            print(f"  {GREEN}✓{RESET} Stopped process {GRAY}PID {p.pid}{RESET}")
        except Exception as e:
            print(f"  {RED}✗{RESET} Error stopping PID {p.pid}: {e}")
    print(f"{TEAL}Platform stopped. Goodbye.{RESET}")
    sys.exit(0)


def main():
    global UNICODE
    _enable_terminal()
    UNICODE = _supports_unicode()

    signal.signal(signal.SIGINT, clean_exit)
    signal.signal(signal.SIGTERM, clean_exit)

    print_banner()

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"  {GRAY}Python {py_ver}  ·  {sys.platform}  ·  {os.getcwd()}{RESET}\n")

    try:
        print(f"{BOLD}{TEAL}▌ PROVISIONING{RESET}")
        python_exe = provision_backend()
        provision_frontend()

        print(f"\n{BOLD}{TEAL}▌ LAUNCHING SERVICES{RESET}")
        backend_dir = os.path.join(os.getcwd(), "backend")
        backend_ready = start_service(
            "backend", "backend", BLUE,
            [python_exe, os.path.join(backend_dir, "run.py")],
            cwd=backend_dir, shell=False,
            ready_patterns=("Application startup complete", "Uvicorn running"),
        )
        wait_ready("FastAPI backend  (port 8000)", backend_ready, timeout=40)

        frontend_dir = os.path.join(os.getcwd(), "frontend")
        frontend_ready = start_service(
            "frontend", "frontend", CYAN,
            "npm run dev", cwd=frontend_dir, shell=(os.name == "nt"),
            ready_patterns=("Ready in", "Local:", "started server"),
        )
        wait_ready("Next.js frontend (port 3000)", frontend_ready, timeout=60)

        print()
        panel([
            f"{GREEN}{BOLD}● PLATFORM ONLINE{RESET}",
            "",
            f"Dashboard   {DIM}→{RESET}  {CYAN}{BOLD}http://localhost:3000{RESET}",
            f"API Docs    {DIM}→{RESET}  {CYAN}http://localhost:8000/docs{RESET}",
            f"Health      {DIM}→{RESET}  {CYAN}http://localhost:8000/health{RESET}",
            "",
            f"{GRAY}Press Ctrl+C to shut down all services.{RESET}",
        ])
        print(f"\n{GRAY}▌ LIVE LOGS{RESET}")

        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"\n{RED}A service exited unexpectedly (code {p.returncode}). Stopping platform…{RESET}")
                    clean_exit()
    except KeyboardInterrupt:
        clean_exit()
    except Exception as e:
        print(f"\n{RED}{BOLD}Startup failed:{RESET} {e}")
        clean_exit()


if __name__ == "__main__":
    main()
