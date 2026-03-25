import webview
import os

# Get absolute path to UI folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
html_path = os.path.join(BASE_DIR, "ui", "index.html")

# Create window
webview.create_window(
    "Face Attendance System",
    html_path,
    width=1200,
    height=700,
    resizable=True
)

# Start app
webview.start()