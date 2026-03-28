import sys
import os
import threading
import time
import socket
import webbrowser

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

os.chdir(resource_path("."))

from app import app, scheduler, setup_scheduler

PORT = 52140
_flask_ready = threading.Event()


def start_flask():
    scheduler.start()
    setup_scheduler()
    _flask_ready.set()
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


def _wait_for_server(timeout=15):
    """Poll until Flask is actually accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", PORT), timeout=0.5)
            s.close()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def _wait_and_navigate(window):
    _flask_ready.wait(timeout=15)
    _wait_for_server(timeout=10)
    time.sleep(0.4)
    window.load_url(f"http://127.0.0.1:{PORT}/app?mode=desktop")


def main():
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    try:
        import webview

        splash_path = resource_path("splash.html")
        if os.path.exists(splash_path):
            with open(splash_path, "r", encoding="utf-8") as f:
                splash_html = f.read()
        else:
            splash_html = (
                "<html><body style='background:#0a0f1e;display:flex;"
                "align-items:center;justify-content:center;height:100vh;'>"
                "<h2 style='color:#06b6d4;font-family:sans-serif;'>"
                "Loading MTT Infinite Optimizer...</h2></body></html>"
            )

        window = webview.create_window(
            "MTT Windows Infinite Optimizer",
            html=splash_html,
            width=1280,
            height=800,
            min_size=(900, 600),
            resizable=True,
            text_select=True,
            background_color="#0a0f1e",
        )

        nav_thread = threading.Thread(
            target=_wait_and_navigate, args=(window,), daemon=True
        )
        nav_thread.start()

        webview.start()

    except ImportError:
        print("pywebview not found, opening in default browser...")
        _flask_ready.wait(timeout=15)
        _wait_for_server(timeout=10)
        webbrowser.open(f"http://127.0.0.1:{PORT}/app?mode=desktop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
