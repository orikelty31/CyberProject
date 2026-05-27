"""
trivia_client.py
================
Graphical (Tkinter) client for a multiplayer trivia game.

Run:  python trivia_client.py
"""

import socket
import threading
import json
import tkinter as tk
from tkinter import messagebox, simpledialog


# ─────────────────────────────────────────────
# Connection settings
# ─────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 5555

# ─────────────────────────────────────────────
# Color theme and design
# ─────────────────────────────────────────────
THEME = {
    "bg_dark": "#0d0d1a",
    "bg_card": "#1a1a2e",
    "bg_panel": "#16213e",
    "accent": "#e94560",
    "accent2": "#0f3460",
    "text_main": "#eaeaea",
    "text_muted": "#888aaa",
    "btn_normal": "#1a1a2e",
    "btn_hover": "#e94560",
    "btn_correct": "#2ecc71",
    "btn_wrong": "#e74c3c",
    "btn_text": "#eaeaea",
    "timer_high": "#2ecc71",
    "timer_mid": "#f39c12",
    "timer_low": "#e74c3c",
}

FONT_TITLE = ("Georgia", 26, "bold")
FONT_ROUND = ("Courier New", 11, "bold")
FONT_Q = ("Georgia", 15)
FONT_BTN = ("Georgia", 13)
FONT_TIMER = ("Courier New", 36, "bold")
FONT_SCORE = ("Courier New", 11)
FONT_STATUS = ("Courier New", 12)


# ─────────────────────────────────────────────
# Client class
# ─────────────────────────────────────────────
# noinspection PyBroadException
class TriviaClient:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.sock: socket.socket | None = None
        self.username = ""
        self.answered = False
        self.timer_val = 0
        self._timer_job = None

        root.title("🎯 Trivia Network Game")
        root.configure(bg=THEME["bg_dark"])
        root.resizable(False, False)
        root.geometry("1920x1080")

        self._build_ui()
        self._ask_connect()

    # ─── Build UI ────────────────────────────

    def _build_ui(self):
        """Builds all GUI components."""
        # Header
        hdr = tk.Frame(self.root, bg=THEME["bg_dark"])
        hdr.pack(fill="x", padx=20, pady=(18, 0))

        tk.Label(
            hdr, text="🎯 TRIVIA NETWORK", font=FONT_TITLE,
            bg=THEME["bg_dark"], fg=THEME["accent"]
        ).pack(side="left")

        self.lbl_round = tk.Label(
            hdr, text="", font=FONT_ROUND,
            bg=THEME["bg_dark"], fg=THEME["text_muted"]
        )
        self.lbl_round.pack(side="right", padx=8)

        # Divider
        tk.Frame(self.root, bg=THEME["accent"], height=2).pack(
            fill="x", padx=20, pady=10
        )

        # Question area
        q_frame = tk.Frame(self.root, bg=THEME["bg_card"], bd=0)
        q_frame.pack(fill="x", padx=20, pady=(0, 12))

        self.lbl_question = tk.Label(
            q_frame,
            text="Waiting for server...",
            font=FONT_Q,
            bg=THEME["bg_card"],
            fg=THEME["text_main"],
            wraplength=680,
            justify="center",
            pady=18,
            padx=14,
        )
        self.lbl_question.pack(fill="x")

        # Answer buttons
        btn_outer = tk.Frame(self.root, bg=THEME["bg_dark"])
        btn_outer.pack(fill="x", padx=20, pady=(0, 12))

        self.answer_buttons: list[tk.Button] = []
        for i in range(4):
            row = i // 2
            col = i % 2
            btn = tk.Button(
                btn_outer,
                text="",
                font=FONT_BTN,
                bg=THEME["btn_normal"],
                fg=THEME["btn_text"],
                activebackground=THEME["btn_hover"],
                activeforeground="#fff",
                relief="flat",
                bd=0,
                cursor="hand2",
                height=2,
                wraplength=330,
                command=lambda idx=i: self._send_answer(idx),
            )
            btn.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            self._add_hover(btn, i)
            self.answer_buttons.append(btn)

        btn_outer.columnconfigure(0, weight=1)
        btn_outer.columnconfigure(1, weight=1)

        # Timer + scoreboard
        bottom = tk.Frame(self.root, bg=THEME["bg_dark"])
        bottom.pack(fill="x", padx=20, pady=(0, 10))

        # Timer
        timer_frame = tk.Frame(bottom, bg=THEME["bg_panel"], padx=20, pady=10)
        timer_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(
            timer_frame, text="⏱ TIME", font=FONT_ROUND,
            bg=THEME["bg_panel"], fg=THEME["text_muted"]
        ).pack()

        self.lbl_timer = tk.Label(
            timer_frame, text="--",
            font=FONT_TIMER,
            bg=THEME["bg_panel"],
            fg=THEME["timer_high"],
        )
        self.lbl_timer.pack()

        # Scoreboard
        score_frame = tk.Frame(bottom, bg=THEME["bg_panel"], padx=14, pady=10)
        score_frame.pack(side="right", fill="both", expand=True)

        tk.Label(
            score_frame, text="🏆 SCOREBOARD", font=FONT_ROUND,
            bg=THEME["bg_panel"], fg=THEME["text_muted"]
        ).pack(anchor="w")

        self.score_text = tk.Text(
            score_frame,
            font=FONT_SCORE,
            bg=THEME["bg_panel"],
            fg=THEME["text_main"],
            relief="flat",
            height=5,
            width=30,
            state="disabled",
        )
        self.score_text.pack(fill="both", expand=True)

        # Status bar
        self.lbl_status = tk.Label(
            self.root,
            text="Not connected",
            font=FONT_STATUS,
            bg=THEME["bg_dark"],
            fg=THEME["text_muted"],
            anchor="w",
        )
        self.lbl_status.pack(fill="x", padx=22, pady=(0, 12))

    def _add_hover(self, btn: tk.Button, idx: int):
        btn.bind("<Enter>", lambda e: btn.config(bg=THEME["btn_hover"]) if btn["state"] != "disabled" else None)
        btn.bind("<Leave>", lambda e: btn.config(bg=THEME["btn_normal"]) if btn["state"] != "disabled" else None)

    # ─── Connection ──────────────────────────

    def _ask_connect(self):
        """Asks for a username and connects to the server."""
        name = simpledialog.askstring(
            "Join Game", "Enter your username:",
            parent=self.root
        )
        if not name:
            self.root.destroy()
            return
        self.username = name.strip() or "Guest"
        self._connect()

    def _connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            self._send_raw(f"JOIN {self.username}")
            self._set_status(f"Connected as {self.username}")
            # Listener thread
            t = threading.Thread(target=self._listen_loop, daemon=True)
            t.start()
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect to server:\n{e}")
            self.root.destroy()

    # ─── Server listener ─────────────────────

    def _listen_loop(self):
        """Runs in a separate thread; receives messages and passes them to the GUI."""
        buf = ""
        try:
            while True:
                chunk = self.sock.recv(4096).decode("utf-8")
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self.root.after(0, self._handle_server_msg, line)
        except Exception:
            pass
        self.root.after(0, self._on_disconnect)

    def _handle_server_msg(self, line: str):
        """Parses a server message and updates the GUI."""
        parts = line.split(" ", 1)
        msg_type = parts[0]
        payload = parts[1] if len(parts) > 1 else ""

        if msg_type == "WAIT":
            self._set_status(payload)

        elif msg_type == "QUESTION":
            data = json.loads(payload)
            self._show_question(data)

        elif msg_type == "TIMER":
            secs = int(payload)
            self._update_timer(secs)

        elif msg_type == "RESULT":
            data = json.loads(payload)
            self._show_result(data)

        elif msg_type == "SCORES":
            data = json.loads(payload)
            self._update_scores(data)

        elif msg_type == "GAMEOVER":
            data = json.loads(payload)
            self._show_gameover(data)

    # ─── GUI updates ─────────────────────────

    def _show_question(self, data: dict):
        """Displays a new question."""
        self.answered = False
        rnd = data.get("round", 1)
        total = data.get("total", 1)
        self.lbl_round.config(text=f"Round {rnd}/{total}")
        self.lbl_question.config(text=data["question"], fg=THEME["text_main"])
        options = data["options"]
        for i, btn in enumerate(self.answer_buttons):
            btn.config(
                text=f"{chr(65 + i)}.  {options[i]}",
                bg=THEME["btn_normal"],
                state="normal",
            )
        self._update_timer(data.get("timeout", 15))
        self._set_status("Choose an answer!")

    def _update_timer(self, secs: int):
        self.timer_val = secs
        color = (
            THEME["timer_high"] if secs > 8
            else THEME["timer_mid"] if secs > 4
            else THEME["timer_low"]
        )
        self.lbl_timer.config(text=str(secs), fg=color)

    def _show_result(self, data: dict):
        """Displays round results – highlights correct/wrong answer."""
        correct_idx = data["correct_index"]
        correct_text = data["correct_text"]
        scorers = data.get("scorers", [])

        for i, btn in enumerate(self.answer_buttons):
            if i == correct_idx:
                btn.config(bg=THEME["btn_correct"], state="disabled")
            else:
                btn.config(bg=THEME["btn_wrong"], state="disabled")

        if self.username in scorers:
            self._set_status(f"✅ Correct! +10 points   |   Answer: {correct_text}")
        else:
            self._set_status(f"❌ Wrong.   |   Answer: {correct_text}")

    def _update_scores(self, scores: dict):
        """Updates the scoreboard."""
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        lines = []
        for rank, (name, score) in enumerate(sorted_scores, 1):
            marker = "★ " if name == self.username else "  "
            lines.append(f"{rank}. {marker}{name:<14} {score:>4} pts")
        text = "\n".join(lines) if lines else "No players"
        self.score_text.config(state="normal")
        self.score_text.delete("1.0", "end")
        self.score_text.insert("end", text)
        self.score_text.config(state="disabled")

    def _show_gameover(self, data: dict):
        """Displays the game-over screen."""
        winner = data.get("winner", "?")
        sorted_scores = data.get("scores", [])
        lines = ["🏁 Game Over!\n"]
        for rank, (name, score) in enumerate(sorted_scores, 1):
            lines.append(f"{rank}. {name} – {score} points")
        if winner == self.username:
            lines.insert(1, "🎉 Congratulations – you won!")
        else:
            lines.insert(1, f"🏆 Winner: {winner}")
        messagebox.showinfo("Game Over", "\n".join(lines))
        self.lbl_question.config(text="Game over. Thanks for playing!")
        self._set_status("Game over")

    def _on_disconnect(self):
        self._set_status("❗ Disconnected from server")
        messagebox.showwarning("Disconnected", "The connection to the server was lost.")

    def _set_status(self, msg: str):
        self.lbl_status.config(text=msg)

    # ─── Sending ─────────────────────────────

    def _send_answer(self, idx: int):
        if self.answered:
            return
        self.answered = True
        # Highlight the selected button
        for i, btn in enumerate(self.answer_buttons):
            if i == idx:
                btn.config(bg=THEME["accent"])
            btn.config(state="disabled")
        self._send_raw(f"ANSWER {idx}")
        self._set_status("⏳ Waiting for round to end...")

    def _send_raw(self, msg: str):
        try:
            if self.sock:
                self.sock.sendall((msg + "\n").encode("utf-8"))
        except Exception as e:
            print(f"Send error: {e}")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = TriviaClient(root)
    root.mainloop()
