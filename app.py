"""Start SlideSmith:  python app.py   (then open http://127.0.0.1:8000)

    python app.py --lan   also lets phones/tablets on the same Wi-Fi open it (shows the address to use)
"""
import os
import socket
import sys
import threading
import webbrowser

import uvicorn


def lan_ip() -> str:
    """This PC's best address on the local network (home/office ranges first; no traffic is sent)."""
    from server.features import lan_ips
    ips = lan_ips()
    return ips[0] if ips else "127.0.0.1"


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else int(os.getenv("PORT", "8000"))
    os.environ["PORT"] = str(port)
    lan = "--lan" in sys.argv or os.getenv("SLIDESMITH_LAN") == "1"
    os.environ["SLIDESMITH_LAN"] = "1" if lan else "0"
    if lan:
        print(f"\n  Phone access is ON. On your phone (same Wi-Fi) open:  http://{lan_ip()}:{port}\n"
              f"  If Windows asks, click 'Allow access' for Python on private networks.\n")
    if os.getenv("NO_BROWSER") != "1" and "--no-browser" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run("server.main:app", host="0.0.0.0" if lan else "127.0.0.1", port=port, reload=False)
