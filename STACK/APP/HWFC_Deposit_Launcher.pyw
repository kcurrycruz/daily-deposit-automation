"""
HWFC Daily Deposit Automation Launcher
Honest Weight Food Co-op — Albany, NY
"""

import sys
import os

# ─────────────────────────────────────────────────────────────────
# WORKER MODE: when packaged as a frozen exe, there is no separate
# python.exe to call — sys.executable IS this exe. So instead of
# spawning python.exe to run pos_to_quickbooks_v2.py, the launcher
# spawns ANOTHER COPY OF ITSELF with a special flag. That copy
# detects the flag here, runs the deposit script's main() function
# directly, and exits — never reaching the GUI code below.
# When running as a raw .pyw (not frozen), this branch is skipped
# entirely and python.exe is used directly as before.
# ─────────────────────────────────────────────────────────────────
if "--run-worker" in sys.argv:
    if hasattr(sys, '_MEIPASS'):
        sys.path.insert(0, sys._MEIPASS)
    else:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pos_to_quickbooks_v2
    sys.argv = [a for a in sys.argv if a != "--run-worker"]
    pos_to_quickbooks_v2.main()
    sys.exit(0)

import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
from datetime import date, timedelta
from pathlib import Path

# When frozen (.exe), sys.executable IS this exe — relaunch itself
# with --run-worker instead of trying to find a separate python.exe.
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    APP_ROOT = Path(sys.executable).resolve().parent
    PYTHON_EXE = sys.executable
    SCRIPT_PATH = None
else:
    APP_DIR = Path(__file__).resolve().parent
    APP_ROOT = APP_DIR.parent
    PYTHON_EXE = sys.executable
    SCRIPT_PATH = str(APP_DIR / "pos_to_quickbooks_v2.py")

ICON_PATH = r"\\Sigma.hwfc.com\SHARED\Finance Forms Public\POS_Automation\hwfc_icon.ico"
QB_IMPORTS = APP_ROOT / "output" / "qb_imports"
LOG_DIR = APP_ROOT / "logs"

# Earthy HWFC palette
BG          = "#f5f0e8"
PANEL       = "#ede6d6"
DARK_GREEN  = "#3d5c35"
MID_GREEN   = "#5a7a4a"
LIGHT_GREEN = "#8aab72"
TERRACOTTA  = "#b5623e"
WARM_BROWN  = "#6b4e35"
GOLD        = "#c8961e"
TEXT_DARK   = "#2c2c1e"
TEXT_MID    = "#5a5440"
TEXT_LIGHT  = "#9a9278"
LOG_BG      = "#2a2a1a"
LOG_FG      = "#d4cbb0"


class HWFCApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HWFC Daily Deposit")
        self.root.geometry("680x660")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        if Path(ICON_PATH).exists():
            try: self.root.iconbitmap(ICON_PATH)
            except: pass
        self._build_ui()

    def _build_ui(self):
        # Header
        header = tk.Frame(self.root, bg=DARK_GREEN)
        header.pack(fill="x")
        tk.Frame(header, bg=LIGHT_GREEN, height=4).pack(fill="x")
        inner = tk.Frame(header, bg=DARK_GREEN, padx=28, pady=18)
        inner.pack(fill="x")

        logo_f = tk.Frame(inner, bg=DARK_GREEN)
        logo_f.pack(side="left")
        tk.Label(logo_f, text="🌿", font=("Segoe UI Emoji", 26),
                 bg=DARK_GREEN, fg=LIGHT_GREEN).pack(side="left", padx=(0, 10))
        title_f = tk.Frame(logo_f, bg=DARK_GREEN)
        title_f.pack(side="left")
        tk.Label(title_f, text="HONEST WEIGHT",
                 font=("Georgia", 15, "bold"), fg="#f0ead8", bg=DARK_GREEN).pack(anchor="w")
        tk.Label(title_f, text="Food Co-op  ·  Daily Deposit Automation",
                 font=("Georgia", 9, "italic"), fg=LIGHT_GREEN, bg=DARK_GREEN).pack(anchor="w")

        badge = tk.Frame(inner, bg=MID_GREEN, padx=14, pady=8)
        badge.pack(side="right")
        tk.Label(badge, text=date.today().strftime("%A, %b %d"),
                 font=("Georgia", 9, "italic"), fg="#f0ead8", bg=MID_GREEN).pack()

        tk.Frame(header, bg=TERRACOTTA, height=3).pack(fill="x")

        # Content
        content = tk.Frame(self.root, bg=BG, padx=28, pady=20)
        content.pack(fill="x")

        # Date section
        date_sec = tk.Frame(content, bg=PANEL, padx=18, pady=16)
        date_sec.pack(fill="x", pady=(0, 12))

        lbl_row = tk.Frame(date_sec, bg=PANEL)
        lbl_row.pack(fill="x", pady=(0, 10))
        tk.Label(lbl_row, text="DEPOSIT DATE", font=("Georgia", 8, "bold"),
                 fg=WARM_BROWN, bg=PANEL).pack(side="left")
        tk.Label(lbl_row, text="  ·  enter date or click a shortcut below",
                 font=("Georgia", 8, "italic"), fg=TEXT_LIGHT, bg=PANEL).pack(side="left")

        inp_row = tk.Frame(date_sec, bg=PANEL)
        inp_row.pack(fill="x")
        self.date_var = tk.StringVar()
        self.date_var.set((date.today() - timedelta(days=1)).strftime("%m/%d/%y"))
        ef = tk.Frame(inp_row, bg=DARK_GREEN, padx=2, pady=2)
        ef.pack(side="left")
        self.date_entry = tk.Entry(ef, textvariable=self.date_var,
                                   font=("Georgia", 14), width=10,
                                   bg="#faf7f0", fg=TEXT_DARK,
                                   insertbackground=DARK_GREEN, relief="flat", bd=8)
        self.date_entry.pack()
        self.date_entry.bind("<Return>", lambda e: self.run_script())
        tk.Label(inp_row, text="  MM / DD / YY", font=("Georgia", 9, "italic"),
                 fg=TEXT_LIGHT, bg=PANEL).pack(side="left")

        btn_row = tk.Frame(date_sec, bg=PANEL)
        btn_row.pack(fill="x", pady=(10, 0))
        for label, days in [("Yesterday", 1), ("2 Days Ago", 2), ("3 Days Ago", 3)]:
            d = date.today() - timedelta(days=days)
            def set_d(d=d):
                self.date_var.set(d.strftime("%m/%d/%y"))
            b = tk.Button(btn_row, text=label, font=("Georgia", 8),
                          bg="#e0d8c8", fg=TEXT_MID,
                          activebackground=LIGHT_GREEN, activeforeground="white",
                          relief="flat", bd=0, padx=12, pady=5,
                          cursor="hand2", command=set_d)
            b.pack(side="left", padx=(0, 6))

        # Run button
        self.run_btn = tk.Button(content,
                                  text="▶   RUN DEPOSIT AUTOMATION",
                                  font=("Georgia", 12, "bold"),
                                  bg=DARK_GREEN, fg="#f5f0e8",
                                  activebackground=MID_GREEN,
                                  activeforeground="white",
                                  relief="flat", bd=0, pady=14,
                                  cursor="hand2", command=self.run_script)
        self.run_btn.pack(fill="x", pady=(0, 4))
        self.run_btn.bind("<Enter>", lambda e: self.run_btn.config(bg=MID_GREEN))
        self.run_btn.bind("<Leave>", lambda e: self.run_btn.config(bg=DARK_GREEN))

        # Status bar
        st_row = tk.Frame(content, bg=PANEL, padx=14, pady=8)
        st_row.pack(fill="x", pady=(0, 12))
        self.status_dot = tk.Label(st_row, text="●", font=("Georgia", 10),
                                   fg=TEXT_LIGHT, bg=PANEL)
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_var = tk.StringVar(value="Ready to run")
        tk.Label(st_row, textvariable=self.status_var,
                 font=("Georgia", 9, "italic"), fg=TEXT_MID, bg=PANEL).pack(side="left")

        # Log section
        log_lbl = tk.Frame(self.root, bg=BG, padx=28)
        log_lbl.pack(fill="x")
        tk.Label(log_lbl, text="OUTPUT LOG", font=("Georgia", 8, "bold"),
                 fg=WARM_BROWN, bg=BG).pack(side="left")
        tk.Button(log_lbl, text="Clear", font=("Georgia", 8),
                  bg=BG, fg=TEXT_LIGHT, activebackground=PANEL,
                  relief="flat", bd=0, cursor="hand2",
                  command=self.clear_log).pack(side="right")

        log_cont = tk.Frame(self.root, bg=DARK_GREEN, padx=2, pady=2)
        log_cont.pack(fill="both", expand=True, padx=28, pady=(4, 0))
        self.log_box = scrolledtext.ScrolledText(
            log_cont, font=("Courier New", 9),
            bg=LOG_BG, fg=LOG_FG,
            insertbackground=LIGHT_GREEN,
            relief="flat", bd=0, wrap="word", height=12, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=2, pady=2)
        self.log_box.tag_config("match",   foreground="#8aab72", font=("Courier New", 9, "bold"))
        self.log_box.tag_config("mismatch",foreground="#c8614a", font=("Courier New", 9, "bold"))
        self.log_box.tag_config("info",    foreground="#d4cbb0")
        self.log_box.tag_config("warning", foreground="#c8961e")
        self.log_box.tag_config("header",  foreground="#a8c88a", font=("Courier New", 9, "bold"))
        self.log_box.tag_config("error",   foreground="#c8614a", font=("Courier New", 9, "bold"))
        self.log_box.tag_config("divider", foreground="#4a5c3a")

        # Bottom buttons
        bottom = tk.Frame(self.root, bg=BG, padx=28, pady=12)
        bottom.pack(fill="x")
        for text, cmd in [("📂  Open QB Imports", self.open_folder),
                           ("📋  Last Status File", self.view_status)]:
            tk.Button(bottom, text=text, font=("Georgia", 9),
                      bg=PANEL, fg=WARM_BROWN,
                      activebackground=LIGHT_GREEN, activeforeground="white",
                      relief="flat", bd=0, padx=14, pady=7,
                      cursor="hand2", command=cmd).pack(side="left", padx=(0, 8))

        # Footer
        tk.Frame(self.root, bg=DARK_GREEN, height=3).pack(fill="x", side="bottom")
        tk.Label(self.root, text="Honest Weight Food Co-op  ·  Albany, NY  ·  Est. 1976",
                 font=("Georgia", 8, "italic"), fg=TEXT_LIGHT, bg=BG).pack(side="bottom", pady=5)

    def log(self, text, tag="info"):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    def set_status(self, text, dot_color=TEXT_LIGHT):
        self.status_var.set(text)
        self.status_dot.config(fg=dot_color)

    def open_folder(self):
        try:
            if Path(QB_IMPORTS).exists():
                subprocess.Popen(["explorer", str(QB_IMPORTS)])
            else:
                messagebox.showinfo("Not Found", f"Folder not found:\n{QB_IMPORTS}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def view_status(self):
        try:
            f = LOG_DIR / "last_run_status.txt"
            if f.exists():
                subprocess.Popen(["notepad", str(f)])
            else:
                messagebox.showinfo("Not Found", "No status file yet. Run the script first.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def run_script(self):
        if not FROZEN and not Path(SCRIPT_PATH).exists():
            messagebox.showerror(
                "Script Not Found",
                f"Cannot find:\n{SCRIPT_PATH}"
            )
            return

        deposit_date = self.date_var.get().strip()
        if not deposit_date:
            messagebox.showwarning("No Date", "Please enter a deposit date.")
            return

        self.run_btn.config(state="disabled", text="⏳   RUNNING...", bg=WARM_BROWN)
        self.set_status(f"Running for {deposit_date}...", dot_color=GOLD)
        self.clear_log()
        self.log(f"  Deposit: {deposit_date}", "header")
        self.log("  " + "─" * 50, "divider")

        SHOW = ["SALES CHECK","DISCOUNTS CHECK","HASH SALES","COMPLETE","RESULT:",
                "Gross Sales","Store Coupons","Owner Apprec","Milk Btl","Script Net",
                "Excel Sales","Script Discounts","Excel Disc","Refunded Discounts",
                "Pass Thru","Hash Sales 6","Difference:","Auto-filled total",
                "TBA Purchases","FAILED","Sales accounts","Discount accounts",
                "Level 1  $"]

        def run():
            try:
                si, cf = None, 0
                if sys.platform == "win32":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 0
                    cf = subprocess.CREATE_NO_WINDOW

                # Frozen exe: relaunch self with --run-worker flag.
                # Raw .pyw: call python.exe directly on the script as before.
                if FROZEN:
                    cmd = [PYTHON_EXE, "--run-worker"]
                else:
                    cmd = [PYTHON_EXE, SCRIPT_PATH]

                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, bufsize=1,
                    encoding="utf-8", errors="replace",
                    startupinfo=si, creationflags=cf)
                proc.stdin.write(deposit_date + "\n")
                proc.stdin.flush()
                proc.stdin.close()

                # Buffer every raw line so we can show the whole log if the
                # script fails. The filtered view stays the same for success.
                all_lines = []

                for line in proc.stdout:
                    line = line.rstrip()
                    all_lines.append(line)
                    if not line.strip() or not any(k in line for k in SHOW):
                        continue
                    if "✓ MATCH" in line or "MATCH — OK" in line:
                        tag = "match"
                    elif "⚠ MISMATCH" in line or "MISMATCH" in line:
                        tag = "mismatch"
                    elif "FAILED" in line or "ERROR" in line:
                        tag = "error"
                    elif any(x in line for x in ["SALES CHECK","DISCOUNTS CHECK",
                                                   "HASH SALES","COMPLETE"]):
                        tag = "header"
                    else:
                        tag = "info"
                    # Strip timestamp and log level prefix (e.g. "2026-04-17 10:46:15,466  INFO  ")
                    clean = line
                    # Find last occurrence of INFO/WARNING/ERROR and take everything after
                    for p in ["ERROR", "WARNING", "INFO"]:
                        idx = clean.rfind(p)
                        if idx != -1:
                            clean = clean[idx + len(p):].strip()
                            break
                    # Skip lines that look like raw Python code
                    if (clean.startswith("log.") or
                            clean.startswith("Message:") or
                            "log.info" in clean or
                            "log.warning" in clean):
                        continue
                    self.root.after(0, self.log, "  " + clean, tag)

                proc.wait()
                if proc.returncode == 0:
                    self.root.after(0, self.on_success)
                else:
                    self.root.after(0, self.on_error, f"Exit code {proc.returncode}")
            except Exception as e:
                self.root.after(0, self.on_error, str(e))

        threading.Thread(target=run, daemon=True).start()

    def on_success(self):
        self.run_btn.config(state="normal", text="▶   RUN DEPOSIT AUTOMATION", bg=DARK_GREEN)
        self.run_btn.bind("<Enter>", lambda e: self.run_btn.config(bg=MID_GREEN))
        self.run_btn.bind("<Leave>", lambda e: self.run_btn.config(bg=DARK_GREEN))
        self.set_status("✓ Complete — import IIF into QuickBooks", dot_color=LIGHT_GREEN)
        self.log("  " + "─" * 50, "divider")
        self.log("  ✓ Done! Open QB Imports folder to import the IIF.", "match")

    def on_error(self, msg):
        self.run_btn.config(state="normal", text="▶   RUN DEPOSIT AUTOMATION", bg=DARK_GREEN)
        self.set_status("⚠ Error — see log for details", dot_color=TERRACOTTA)
        self.log(f"  Error: {msg}", "error")


if __name__ == "__main__":
    root = tk.Tk()
    app = HWFCApp(root)
    root.mainloop()
