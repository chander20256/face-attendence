# import webview
# import os

# # Get absolute path to UI folder
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# html_path = os.path.join(BASE_DIR, "ui", "index.html")

# # Create window
# webview.create_window(
#     "Face Attendance System",
#     html_path,
#     width=1200,
#     height=700,
#     resizable=True
# )

# # Start app
# webview.start()

import webview
import os
import sys
import subprocess
import time
from urllib import error, request

def load_local_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_local_env()
APP_PORT = int(os.getenv("APP_PORT", "5050"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_URL = f"http://127.0.0.1:{APP_PORT}"


def backend_is_ready():
    try:
        with request.urlopen(f"{APP_URL}/api/health", timeout=2) as response:
            return response.status == 200
    except error.URLError:
        return False


def start_server():
    """Start Flask server in background"""
    if backend_is_ready():
        print("Backend server already running")
        return

    try:
        # Hide console window on Windows
        if sys.platform == "win32":
            subprocess.Popen(
                [sys.executable, "server.py"],
                cwd=BASE_DIR,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                [sys.executable, "server.py"],
                cwd=BASE_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        for _ in range(20):
            if backend_is_ready():
                print("Backend server started")
                return
            time.sleep(0.25)

        print("Backend server did not become ready. Try running python server.py in a terminal to see the error.")
    except Exception as e:
        print(f"Could not start server: {e}")
        print("Make sure server.py exists in the same folder")

def main():
    start_server()
    
    # Create window
    webview.create_window(
        "Face Attendance System",
        APP_URL,
        width=1200,
        height=700,
        resizable=True,
        fullscreen=False
    )
    
    # Start application
    webview.start()

if __name__ == "__main__":
    main()
