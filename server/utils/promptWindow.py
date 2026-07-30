import sys
import subprocess
import threading

# Lock to ensure only one thread shows a prompt at a given time
dialog_lock = threading.Lock()

def request_approval_dialog(title: str, message: str) -> bool:
    """
    Displays a GUI pop-up (Yes/No) without launching a terminal window.
    Bypasses GTK/D-Bus module warnings and is 100% thread-safe.
    """
    # Self-contained Python command running Tkinter
    tk_script = (
        "import sys, tkinter as tk; "
        "from tkinter import messagebox; "
        "root = tk.Tk(); root.withdraw(); "  # Hide the parent window
        "root.attributes('-topmost', True); " # Bring dialog to front
        f"res = messagebox.askyesno('{title}', '''{message}'''); "
        "sys.exit(0 if res else 1)"
    )

    with dialog_lock:
        try:
            # Run Tkinter in an isolated child process
            result = subprocess.run(
                [sys.executable, "-c", tk_script],
                stderr=subprocess.DEVNULL  # Silences any low-level display warnings
            )
            # Exit code 0 means 'Yes', 1 means 'No'
            return result.returncode == 0
        except Exception as e:
            print(f"Failed to show approval popup: {e}")
            return False
