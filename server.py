"""
trivia_server.py
================
Central server for a multiplayer trivia game.
Listens for TCP connections, manages question rounds, and returns results in real time.

Communication protocol (newline-terminated messages \n):
  JOIN <username>          - client connects
  ANSWER <index>           - client sends answer (0-3)
  QUESTION <json>          - server sends a question
  TIMER <seconds>          - server sends timer update
  RESULT <json>            - server sends round results
  SCORES <json>            - server sends scoreboard
  WAIT <message>           - server requests the client to wait
  GAMEOVER <json>          - server ends the game
"""

import socket
import threading
import json
import time
import random
import logging
import sys
import os
from typing import Dict, Optional

# ─────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 5555
MIN_PLAYERS = 1          # Can start with just one player
MAX_PLAYERS = 10
QUESTION_TIMEOUT = 15    # Seconds per question
NUM_ROUNDS = 10           # Number of rounds (questions are chosen randomly if more exist)
POINTS_PER_CORRECT = 10  # Points awarded for a correct answer

QUESTIONS_FILE = "questions.json"   # ← Change to another path if needed

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SERVER] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("server")

# ─────────────────────────────────────────────
# Load questions from JSON file
# ─────────────────────────────────────────────

def load_questions(path: str) -> list:
    """
    Loads questions from a JSON file.

    Required format per question:
    {
        "question": "Question text",
        "options":  ["Option 1", "Option 2", "Option 3", "Option 4"],
        "answer":   2        ← index of the correct answer (0-3)
    }

    Also supports:
        "answer": "Option 3"  ← text instead of index
    """
    if not os.path.exists(path):
        log.error(f"Questions file '{path}' not found!")
        log.error("Create a questions.json file next to the script and try again.")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            log.error(f"JSON error in '{path}': {e}")
            sys.exit(1)

    # Support two formats: direct list, or {"questions": [...]}
    if isinstance(raw, dict) and "questions" in raw:
        raw = raw["questions"]

    if not isinstance(raw, list) or len(raw) == 0:
        log.error("File is empty or not in the correct format.")
        sys.exit(1)

    questions = []
    for i, item in enumerate(raw):
        try:
            q    = item["question"]
            opts = item["options"]
            ans  = item["answer"]

            if not isinstance(opts, list) or len(opts) != 4:
                raise ValueError("Must have exactly 4 options")

            # Support answer as text
            if isinstance(ans, str):
                if ans in opts:
                    ans = opts.index(ans)
                else:
                    raise ValueError(f"Answer '{ans}' not found in options list")

            if not (0 <= ans <= 3):
                raise ValueError(f"Answer index {ans} out of range 0-3")

            questions.append({"question": q, "options": opts, "answer": ans})

        except (KeyError, ValueError, TypeError) as e:
            log.warning(f"Question #{i+1} skipped – {e}")

    if len(questions) == 0:
        log.error("No valid questions were loaded from the file.")
        sys.exit(1)

    log.info(f"Loaded {len(questions)} questions from '{path}'")
    return questions


# ─────────────────────────────────────────────
# Player class
# ─────────────────────────────────────────────
class Player:
    def __init__(self, conn: socket.socket, addr):
        self.conn = conn
        self.addr = addr
        self.name: str = ""
        self.score: int = 0
        self.current_answer: Optional[int] = None  # Answer for the current round
        self.answered: bool = False

    def send(self, msg_type: str, data) -> bool:
        """Sends a message to the client; returns False on failure."""
        try:
            if isinstance(data, (dict, list)):
                payload = json.dumps(data, ensure_ascii=False)
            else:
                payload = str(data)
            line = f"{msg_type} {payload}\n"
            self.conn.sendall(line.encode("utf-8"))
            return True
        except Exception as e:
            log.warning(f"Send error to {self.name}: {e}")
            return False


# ─────────────────────────────────────────────
# Server class
# ─────────────────────────────────────────────
class TriviaServer:
    def __init__(self):
        self.players: Dict[str, Player] = {}   # name -> Player
        self.lock = threading.Lock()
        self.game_started = False
        self.round_active = False
        all_questions = load_questions(QUESTIONS_FILE)
        rounds = min(NUM_ROUNDS, len(all_questions))
        self.questions = random.sample(all_questions, rounds)
        log.info(f"Game will include {rounds} rounds")
        self.current_round = 0

    # ─── Connection management ───────────────

    def start(self):
        """Listens for incoming connections."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((HOST, PORT))
        server_sock.listen(MAX_PLAYERS)
        log.info(f"Server listening on {HOST}:{PORT}")

        # Thread that manages the game flow
        game_thread = threading.Thread(target=self._game_loop, daemon=True)
        game_thread.start()

        while True:
            try:
                conn, addr = server_sock.accept()
                t = threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True,
                )
                t.start()
            except Exception as e:
                log.error(f"Error accepting connection: {e}")

    def _handle_client(self, conn: socket.socket, addr):
        """Handles a single client – runs in a separate thread."""
        player = Player(conn, addr)
        log.info(f"New connection from {addr}")

        try:
            buf = ""
            # Receive username (JOIN <name>)
            while True:
                chunk = conn.recv(1024).decode("utf-8")
                if not chunk:
                    return
                buf += chunk
                if "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line.startswith("JOIN "):
                        name = line[5:].strip()
                        player.name = name
                        break

            with self.lock:
                if player.name in self.players:
                    player.name += f"_{random.randint(100, 999)}"
                self.players[player.name] = player

            log.info(f"Player '{player.name}' joined")
            player.send("WAIT", "Waiting for the game to start...")
            self._broadcast_scores()

            # Message receive loop
            while True:
                chunk = conn.recv(1024).decode("utf-8")
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._process_message(player, line)

        except Exception as e:
            log.warning(f"Player '{player.name}' disconnected: {e}")
        finally:
            self._remove_player(player)

    def _remove_player(self, player: Player):
        with self.lock:
            self.players.pop(player.name, None)
        try:
            player.conn.close()
        except Exception:
            pass
        log.info(f"Player '{player.name}' removed")
        self._broadcast_scores()

    # ─── Message processing ──────────────────

    def _process_message(self, player: Player, line: str):
        """Parses a message received from a client."""
        if line.startswith("ANSWER "):
            if not self.round_active or player.answered:
                return
            try:
                idx = int(line[7:].strip())
                if 0 <= idx <= 3:
                    player.current_answer = idx
                    player.answered = True
                    log.info(f"'{player.name}' answered: {idx}")
            except ValueError:
                pass

    # ─── Game loop ───────────────────────────

    def _game_loop(self):
        """Manages all game rounds – runs in a separate thread."""
        # Wait until at least one player joins
        log.info("Waiting for players...")
        while True:
            time.sleep(1)
            with self.lock:
                count = len(self.players)
            if count >= MIN_PLAYERS:
                break

        log.info("Game is starting!")
        self._broadcast("WAIT", "Game starts in 3 seconds...")
        time.sleep(3)

        for round_num in range(1, len(self.questions) + 1):
            self.current_round = round_num
            self._run_round(round_num, self.questions[round_num - 1])
            time.sleep(3)  # Pause between rounds

        # End game
        self._end_game()

    def _run_round(self, round_num: int, question: dict):
        """Manages a single round."""
        log.info(f"--- Round {round_num} ---")

        # Reset answers
        with self.lock:
            for p in self.players.values():
                p.current_answer = None
                p.answered = False

        # Send question
        q_data = {
            "round": round_num,
            "total": len(self.questions),
            "question": question["question"],
            "options": question["options"],
            "timeout": QUESTION_TIMEOUT,
        }
        self._broadcast("QUESTION", q_data)

        # Timer – sends updates every second
        self.round_active = True
        for remaining in range(QUESTION_TIMEOUT, 0, -1):
            time.sleep(1)
            self._broadcast("TIMER", remaining - 1)
            # If everyone answered – no need to keep waiting
            with self.lock:
                all_answered = all(p.answered for p in self.players.values())
            if all_answered:
                log.info("All players answered before time ran out")
                break

        self.round_active = False

        # Calculate scores
        correct_idx = question["answer"]
        correct_text = question["options"][correct_idx]
        with self.lock:
            scorers = []
            for p in self.players.values():
                if p.current_answer == correct_idx:
                    p.score += POINTS_PER_CORRECT
                    scorers.append(p.name)

        log.info(f"Correct answer: {correct_text}. Correct players: {scorers}")

        # Send results
        result_data = {
            "correct_index": correct_idx,
            "correct_text": correct_text,
            "scorers": scorers,
        }
        self._broadcast("RESULT", result_data)
        self._broadcast_scores()

    def _end_game(self):
        """Ends the game and sends the final rankings."""
        with self.lock:
            scores = {p.name: p.score for p in self.players.values()}
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner = sorted_scores[0][0] if sorted_scores else "None"
        log.info(f"Game over. Winner: {winner}")
        self._broadcast("GAMEOVER", {"winner": winner, "scores": sorted_scores})

    # ─── Broadcasts ──────────────────────────

    def _broadcast(self, msg_type: str, data):
        """Sends a message to all connected players."""
        with self.lock:
            players = list(self.players.values())
        for p in players:
            p.send(msg_type, data)

    def _broadcast_scores(self):
        """Sends an updated scoreboard to everyone."""
        with self.lock:
            scores = {p.name: p.score for p in self.players.values()}
        self._broadcast("SCORES", scores)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    server = TriviaServer()
    server.start()
