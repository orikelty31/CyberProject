"""
title: trivia project - client
description: Simple Tkinter GUI client for the trivia game.
"""

import socket
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog

import protocol


SERVER_IP = "127.0.0.1"
SERVER_PORT = 5555

WINDOW_TITLE = "Trivia Game"
WINDOW_SIZE = "700x550"
ANSWER_AMOUNT = 4
QUESTION_WRAP_LENGTH = 620

BG_COLOR = "#202124"
PANEL_COLOR = "#303134"
TEXT_COLOR = "white"
BUTTON_COLOR = "#3c4043"
SELECTED_COLOR = "#1565c0"
CORRECT_COLOR = "#2e7d32"
WRONG_COLOR = "#c62828"

TITLE_FONT = ("Arial", 24, "bold")
QUESTION_FONT = ("Arial", 15)
ANSWER_FONT = ("Arial", 13)
TIMER_FONT = ("Arial", 18, "bold")
TEXT_FONT = ("Arial", 12)

MSG_JOIN = "JOIN"
MSG_WAIT = "WAIT"
MSG_QUESTION = "QUESTION"
MSG_TIMER = "TIMER"
MSG_RESULT = "RESULT"
MSG_SCORES = "SCORES"
MSG_GAMEOVER = "GAMEOVER"
MSG_ANSWER = "ANSWER"

MESSAGE_FIELDS_AMOUNT = {
    MSG_WAIT: 1,
    MSG_QUESTION: 5,
    MSG_TIMER: 1,
    MSG_RESULT: 3,
    MSG_SCORES: 1,
    MSG_GAMEOVER: 3
}


client_socket = None
username = ""
answered = False
client_closed = False

root = None
question_label = None
timer_label = None
status_label = None
score_text = None
answer_buttons = []


def set_status(text):
    """
    Change the status text.
    :param text: text to show
    :return: None
    """
    status_label.config(text=text)


def connect_to_server():
    """
    Ask for username and connect to the server.
    :return: True if connected, False otherwise
    """
    global client_socket, username

    username = simpledialog.askstring("Join Game", "Enter your name:", parent=root)
    if username is None or username.strip() == "":
        return False

    username = username.strip()

    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((SERVER_IP, SERVER_PORT))
        message = protocol.build_message(MSG_JOIN, [username])
        protocol.send_message(client_socket, message)
        set_status("Connected as " + username)
        return True
    except Exception as e:
        messagebox.showerror("Connection Error", str(e))
        return False


def start_listening():
    """
    Start a thread that listens to the server.
    :return: None
    """
    thread = threading.Thread(target=listen_to_server, daemon=True)
    thread.start()


def listen_to_server():
    """
    Receive messages from the server.
    This runs in a separate thread.
    :return: None
    """
    while not client_closed:
        try:
            message = protocol.receive_message(client_socket)
            if message is None:
                break

            msg_type, fields = protocol.split_message(message)
            root.after(0, handle_server_message, msg_type, fields)

        except Exception:
            break

    if not client_closed:
        root.after(0, server_disconnected)


def handle_server_message(msg_type, fields):
    """
    Handle one message from the server.
    :param msg_type: message type
    :param data: message data
    :return: None
    """
    try:
        if msg_type in MESSAGE_FIELDS_AMOUNT:
            if len(fields) < MESSAGE_FIELDS_AMOUNT[msg_type]:
                set_status("Bad message from server: " + msg_type)
                return

        if msg_type == MSG_WAIT:
            set_status(fields[0])

        elif msg_type == MSG_QUESTION:
            data = {
                "round": int(fields[0]),
                "total": int(fields[1]),
                "question": fields[2],
                "options": protocol.split_list(fields[3]),
                "time": int(fields[4])
            }
            show_question(data)

        elif msg_type == MSG_TIMER:
            timer_label.config(text="Time: " + fields[0])

        elif msg_type == MSG_RESULT:
            data = {
                "correct_index": int(fields[0]),
                "correct_text": fields[1],
                "scorers": protocol.split_list(fields[2])
            }
            show_result(data)

        elif msg_type == MSG_SCORES:
            data = protocol.split_scores(fields[0])
            show_scores(data)

        elif msg_type == MSG_GAMEOVER:
            scores = protocol.split_scores(fields[2])
            data = {
                "winner": fields[0],
                "is_tie": fields[1],
                "scores": list(scores.items())
            }
            show_game_over(data)
    except Exception as e:
        set_status("Message error: " + str(e))


def show_question(data):
    """
    Show a question on the screen.
    :param data: question data from server
    :return: None
    """
    global answered

    answered = False

    title = "Round " + str(data["round"]) + " of " + str(data["total"])
    question_label.config(text=title + "\n\n" + data["question"])
    timer_label.config(text="Time: " + str(data["time"]))
    set_status("Choose an answer")

    options = data["options"]

    for i in range(ANSWER_AMOUNT):
        answer_buttons[i].config(
            text=str(i+1) + ". " + options[i],
            bg=BUTTON_COLOR,
            state="normal"
        )


def send_answer(index):
    """
    Send the selected answer to the server.
    :param index: answer index
    :return: None
    """
    global answered

    if answered:
        return

    answered = True

    for button in answer_buttons:
        button.config(state="disabled")

    answer_buttons[index].config(bg=SELECTED_COLOR)
    set_status("Waiting for result...")

    try:
        message = protocol.build_message(MSG_ANSWER, [index])
        protocol.send_message(client_socket, message)
    except Exception as e:
        set_status("Send error: " + str(e))


def show_result(data):
    """
    Show the correct answer after a round.
    :param data: result data from server
    :return: None
    """
    correct_index = data["correct_index"]

    for i in range(ANSWER_AMOUNT):
        if i == correct_index:
            answer_buttons[i].config(bg=CORRECT_COLOR)
        else:
            answer_buttons[i].config(bg=WRONG_COLOR)

    if username in data["scorers"]:
        set_status("Correct! Answer: " + data["correct_text"])
    else:
        set_status("Wrong. Answer: " + data["correct_text"])


def show_scores(scores):
    """
    Show the score table.
    :param scores: dictionary of name -> score
    :return: None
    """
    score_text.config(state="normal")
    score_text.delete("1.0", "end")

    for name, score in scores.items():
        score_text.insert("end", name + " - " + str(score) + "\n")

    score_text.config(state="disabled")


def show_game_over(data):
    """
    Show final result.
    :param data: game over data
    :return: None
    """
    if data["is_tie"] == "True":
        text = "Tie between: " + data["winner"] + "\n\n"
    else:
        text = "Winner: " + data["winner"] + "\n\n"

    for name, score in data["scores"]:
        text += name + " - " + str(score) + "\n"

    messagebox.showinfo("Game Over", text)
    set_status("Game over")
    close_client()


def server_disconnected():
    """
    Called when the server connection closes.
    :return: None
    """
    set_status("Disconnected from server")


def close_client():
    """
    Close the socket when the user closes the GUI window.
    :return: None
    """
    global client_closed

    client_closed = True

    try:
        if client_socket is not None:
            client_socket.shutdown(socket.SHUT_RDWR)
            client_socket.close()
    except Exception:
        pass

    root.destroy()


def build_gui():
    """
    Build all GUI widgets.
    :return: None
    """
    global question_label, timer_label, status_label, score_text, answer_buttons

    root.title(WINDOW_TITLE)
    root.geometry(WINDOW_SIZE)
    root.configure(bg=BG_COLOR)
    root.protocol("WM_DELETE_WINDOW", close_client)

    title_label = tk.Label(
        root,
        text=WINDOW_TITLE,
        font=TITLE_FONT,
        bg=BG_COLOR,
        fg=TEXT_COLOR
    )
    title_label.pack(pady=15)

    question_label = tk.Label(
        root,
        text="Waiting for server...",
        font=QUESTION_FONT,
        bg=PANEL_COLOR,
        fg=TEXT_COLOR,
        wraplength=QUESTION_WRAP_LENGTH,
        height=5
    )
    question_label.pack(fill="x", padx=20, pady=10)

    answers_frame = tk.Frame(root, bg=BG_COLOR)
    answers_frame.pack(fill="x", padx=20)

    answer_buttons = []
    for i in range(ANSWER_AMOUNT):
        button = tk.Button(
            answers_frame,
            text="",
            font=ANSWER_FONT,
            bg=BUTTON_COLOR,
            fg=TEXT_COLOR,
            height=2,
            command=lambda index=i: send_answer(index)
        )
        button.grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="nsew")
        answer_buttons.append(button)

    answers_frame.columnconfigure(0, weight=1)
    answers_frame.columnconfigure(1, weight=1)

    timer_label = tk.Label(
        root,
        text="Time: --",
        font=TIMER_FONT,
        bg=BG_COLOR,
        fg=TEXT_COLOR
    )
    timer_label.pack(pady=10)

    score_text = tk.Text(
        root,
        height=6,
        font=TEXT_FONT,
        bg=PANEL_COLOR,
        fg=TEXT_COLOR,
        state="disabled"
    )
    score_text.pack(fill="x", padx=20, pady=10)

    status_label = tk.Label(
        root,
        text="Not connected",
        font=TEXT_FONT,
        bg=BG_COLOR,
        fg=TEXT_COLOR
    )
    status_label.pack(pady=5)


def main():
    """
    Start the GUI client.
    :return: None
    """
    global root

    try:
        root = tk.Tk()
        build_gui()

        if connect_to_server():
            start_listening()
            root.mainloop()
        else:
            root.destroy()
    except Exception as e:
        messagebox.showerror("Client Error", str(e))


if __name__ == "__main__":
    main()
