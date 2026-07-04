"""
CXR-AIM Network Launcher
========================
Same provisioning + orchestration as start_platform.py, but binds BOTH services to
0.0.0.0 so other devices on the same LAN / Wi-Fi (your friends) can open the dashboard
from their own browser.

  * Backend  : already binds 0.0.0.0:8000 (backend/run.py).
  * Frontend : launched with `next dev -H 0.0.0.0 -p 3000` so it listens on the network.

The browser figures out the backend address automatically: frontend/src/config.ts points
the API/WebSocket at `window.location.hostname:8000`, so when a friend visits
http://<your-LAN-IP>:3000 their browser talks to http://<your-LAN-IP>:8000 — no rebuild,
no .env editing needed.

Run it exactly like the normal launcher:
    python start_network.py
"""

import os
import sys
import time
import signal
import socket

# Reuse all the styling, provisioning and process-management helpers from the standard
# launcher so the two stay in lockstep (importing does NOT run its main()).
import start_platform as sp

FRONTEND_PORT = 3000
BACKEND_PORT = 8000


def get_lan_ip() -> str:
    """Best-effort detection of this machine's primary LAN IP (the address friends use).
    Opens a throwaway UDP socket toward a public IP so the OS picks the outbound interface;
    no packets are actually sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    sp._enable_terminal()
    sp.UNICODE = sp._supports_unicode()

    signal.signal(signal.SIGINT, sp.clean_exit)
    signal.signal(signal.SIGTERM, sp.clean_exit)

    sp.print_banner()

    lan_ip = get_lan_ip()
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"  {sp.GRAY}Python {py_ver}  ·  {sys.platform}  ·  {os.getcwd()}{sp.RESET}")
    print(f"  {sp.GRAY}LAN address detected:{sp.RESET} {sp.CYAN}{sp.BOLD}{lan_ip}{sp.RESET}"
          f"  {sp.GRAY}(share this with your friends){sp.RESET}\n")

    try:
        print(f"{sp.BOLD}{sp.TEAL}▌ PROVISIONING{sp.RESET}")
        python_exe = sp.provision_backend()
        sp.provision_frontend()

        print(f"\n{sp.BOLD}{sp.TEAL}▌ LAUNCHING SERVICES (NETWORK MODE){sp.RESET}")

        # Backend — run.py already binds 0.0.0.0:8000, reachable across the LAN as-is.
        backend_dir = os.path.join(os.getcwd(), "backend")
        backend_ready = sp.start_service(
            "backend", "backend", sp.BLUE,
            [python_exe, os.path.join(backend_dir, "run.py")],
            cwd=backend_dir, shell=False,
            ready_patterns=("Application startup complete", "Uvicorn running"),
        )
        sp.wait_ready(f"FastAPI backend  (0.0.0.0:{BACKEND_PORT})", backend_ready, timeout=40)

        # Frontend — force Next.js dev to listen on every interface, not just localhost.
        frontend_dir = os.path.join(os.getcwd(), "frontend")
        frontend_ready = sp.start_service(
            "frontend", "frontend", sp.CYAN,
            f"npm run dev -- -H 0.0.0.0 -p {FRONTEND_PORT}",
            cwd=frontend_dir, shell=(os.name == "nt"),
            ready_patterns=("Ready in", "Local:", "Network:", "started server"),
        )
        sp.wait_ready(f"Next.js frontend (0.0.0.0:{FRONTEND_PORT})", frontend_ready, timeout=60)

        print()
        sp.panel([
            f"{sp.GREEN}{sp.BOLD}● PLATFORM ONLINE · NETWORK MODE{sp.RESET}",
            "",
            f"{sp.BOLD}On this PC{sp.RESET}",
            f"  Dashboard {sp.DIM}→{sp.RESET}  {sp.CYAN}http://localhost:{FRONTEND_PORT}{sp.RESET}",
            "",
            f"{sp.BOLD}On your friends' devices (same Wi-Fi/LAN){sp.RESET}",
            f"  Dashboard {sp.DIM}→{sp.RESET}  {sp.CYAN}{sp.BOLD}http://{lan_ip}:{FRONTEND_PORT}{sp.RESET}",
            f"  API Docs  {sp.DIM}→{sp.RESET}  {sp.CYAN}http://{lan_ip}:{BACKEND_PORT}/docs{sp.RESET}",
            "",
            f"{sp.GRAY}First time? Allow ports {FRONTEND_PORT} & {BACKEND_PORT} through Windows{sp.RESET}",
            f"{sp.GRAY}Firewall (run once in an ADMIN PowerShell):{sp.RESET}",
            f"{sp.DIM}  netsh advfirewall firewall add rule name=\"CXR-AIM\" dir=in \\{sp.RESET}",
            f"{sp.DIM}    action=allow protocol=TCP localport={FRONTEND_PORT},{BACKEND_PORT}{sp.RESET}",
            "",
            f"{sp.GRAY}Press Ctrl+C to shut down all services.{sp.RESET}",
        ])
        print(f"\n{sp.GRAY}▌ LIVE LOGS{sp.RESET}")

        while True:
            time.sleep(1)
            for p in sp.processes:
                if p.poll() is not None:
                    print(f"\n{sp.RED}A service exited unexpectedly (code {p.returncode}). "
                          f"Stopping platform…{sp.RESET}")
                    sp.clean_exit()
    except KeyboardInterrupt:
        sp.clean_exit()
    except Exception as e:
        print(f"\n{sp.RED}{sp.BOLD}Startup failed:{sp.RESET} {e}")
        sp.clean_exit()


if __name__ == "__main__":
    main()
