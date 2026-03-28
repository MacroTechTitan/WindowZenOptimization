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
    """Block until Flask is actually accepting TCP connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", PORT), timeout=0.3)
            s.close()
            return True
        except OSError:
            time.sleep(0.15)
    return False


def main():
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # Block here until Flask is fully ready — window is created only once,
    # pointing straight at the Flask /loading route.  No load_url() call
    # means no mid-session navigation and therefore no white flash.
    _flask_ready.wait(timeout=15)
    _wait_for_server(timeout=10)

    try:
        import webview

        webview.create_window(
            "MTT Windows Infinite Optimizer",
            url=f"http://127.0.0.1:{PORT}/loading",
            width=1280,
            height=800,
            min_size=(900, 600),
            resizable=True,
            text_select=True,
            background_color="#0a0f1e",
        )

        webview.start()

    except ImportError:
        print("pywebview not found, opening in default browser...")
        webbrowser.open(f"http://127.0.0.1:{PORT}/app?mode=desktop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
