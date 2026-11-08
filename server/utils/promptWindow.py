import sys
import subprocess

def request_approval_dialog(title: str, message: str) -> bool:
    """
    Displays a GUI pop-up (Yes/No) without launching a terminal window.
    Bypasses GTK/D-Bus module warnings and is 100% thread-safe.

    Each call runs in its own child process, so dialogs for different PCs can
    be shown concurrently. This is intentional: a pending approval for one PC
    must not block start requests for other PCs.
    """
    # Self-contained Python command running Tkinter. The title and message are
    # passed as argv so user-controlled values are never embedded in the script.
    tk_script = (
        "import sys, tkinter as tk; "
        "from tkinter import messagebox; "
        "root = tk.Tk(); root.withdraw(); "  # Hide the parent window
        "root.attributes('-topmost', True); " # Bring dialog to front
        "res = messagebox.askyesno(sys.argv[1], sys.argv[2]); "
        "sys.exit(0 if res else 1)"
    )

    try:
        # Run Tkinter in an isolated child process
        result = subprocess.run(
            [sys.executable, "-c", tk_script, title, message],
            stderr=subprocess.DEVNULL  # Silences any low-level display warnings
        )
        # Exit code 0 means 'Yes', 1 means 'No'
        return result.returncode == 0
    except Exception as e:
        print(f"Failed to show approval popup: {e}")
        return False
