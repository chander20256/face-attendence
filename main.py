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
import threading
import time

def start_server():
    """Start Flask server in background"""
    try:
        # Hide console window on Windows
        if sys.platform == "win32":
            subprocess.Popen(
                ["python", "server.py"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                ["python", "server.py"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        print("✅ Backend server started")
    except Exception as e:
        print(f"⚠️ Could not start server: {e}")
        print("Make sure server.py exists in the same folder")

def main():
    # Start Flask server in background
    threading.Thread(target=start_server, daemon=True).start()
    
    # Wait a bit for server to initialize
    time.sleep(2)
    
    # Get absolute path to UI folder
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    html_path = os.path.join(base_dir, "ui", "index.html")
    
    # Create window
    webview.create_window(
        "Face Attendance System",
        html_path,
        width=1200,
        height=700,
        resizable=True,
        fullscreen=False
    )
    
    # Start application
    webview.start()

if __name__ == "__main__":
    main()