import sys
import os
import threading
import webbrowser

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

os.chdir(resource_path("."))

from app import app, scheduler, setup_scheduler

PORT = 52140

def start_flask():
    scheduler.start()
    setup_scheduler()
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)

def main():
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    import time
    time.sleep(1)

    try:
        import webview
        webview.create_window(
            "SystemOptimizer Pro",
            f"http://127.0.0.1:{PORT}",
            width=1280,
            height=800,
            min_size=(900, 600),
            resizable=True,
            text_select=True,
        )
        webview.start()
    except ImportError:
        print("pywebview not found, opening in default browser...")
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
