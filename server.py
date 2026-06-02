"""
title: trivia project - server
description: Simple trivia server that sends questions to clients.
"""

import json
import os
import random
import socket
import threading
import time

import protocol


IP = "0.0.0.0"
PORT = 5555
QUESTIONS_FILE = "questions.json"
MIN_PLAYERS = 1
NUM_ROUNDS = 10
QUESTION_TIME = 15
POINTS = 10

MSG_JOIN = "JOIN"
MSG_WAIT = "WAIT"
MSG_QUESTION = "QUESTION"
MSG_TIMER = "TIMER"
MSG_RESULT = "RESULT"
MSG_SCORES = "SCORES"
MSG_GAMEOVER = "GAMEOVER"
MSG_ANSWER = "ANSWER"

NO_WINNER = "Tie"

players = []
round_active = False
players_lock = threading.Lock()


def load_questions():
    """
    Load the questions from questions.json.
    :return: list of valid questions
    """
    try:
        path = os.path.join(os.path.dirname(__file__), QUESTIONS_FILE)

        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

        questions = data["questions"]
        good_questions = []

        for question in questions:
            answer = question["answer"]

            if isinstance(answer, str):
                answer = question["options"].index(answer)

            good_questions.append({
                "question": question["question"],
                "options": question["options"],
                "answer": answer
            })

        random.shuffle(good_questions)
        return good_questions[:NUM_ROUNDS]
    except Exception as e:
        print("Error loading questions:", e)
        return []


def send_to_player(player, msg_type, data):
    """
    Send message to one player.
    :param player: player dictionary
    :param msg_type: message type
    :param data: message data
    :return: None
    """
    fields = [data]

    if msg_type == MSG_QUESTION:
        fields = [
            data["round"],
            data["total"],
            data["question"],
            protocol.build_list(data["options"]),
            data["time"]
        ]

    elif msg_type == MSG_RESULT:
        fields = [
            data["correct_index"],
            data["correct_text"],
            protocol.build_list(data["scorers"])
        ]

    elif msg_type == MSG_SCORES:
        fields = [protocol.build_scores(data)]

    elif msg_type == MSG_GAMEOVER:
        scores = {}
        for name, score in data["scores"]:
            scores[name] = score

        fields = [
            data["winner"],
            data["is_tie"],
            protocol.build_scores(scores)
        ]

    message = protocol.build_message(msg_type, fields)
    protocol.send_message(player["socket"], message)


def send_to_all(msg_type, data):
    """
    Send message to all connected players.
    :param msg_type: message type
    :param data: message data
    :return: None
    """
    with players_lock:
        players_copy = players.copy()

    for player in players_copy:
        try:
            send_to_player(player, msg_type, data)
        except Exception:
            remove_player(player)


def send_scores():
    """
    Send the score table to all players.
    :return: None
    """
    scores = {}

    with players_lock:
        for player in players:
            scores[player["name"]] = player["score"]

    send_to_all(MSG_SCORES, scores)


def remove_player(player):
    """
    Remove a disconnected player.
    :param player: player dictionary
    :return: None
    """
    with players_lock:
        if player in players:
            players.remove(player)

    try:
        player["socket"].close()
    except Exception:
        pass


def disconnect_all_players():
    """
    Disconnect all players after the game ends.
    :return: None
    """
    global round_active

    round_active = False

    with players_lock:
        players_copy = players.copy()
        players.clear()

    for player in players_copy:
        try:
            player["socket"].shutdown(socket.SHUT_RDWR)
            player["socket"].close()
        except Exception:
            pass


def handle_client(client_socket, client_address):
    """
    Handle one client.
    :param client_socket: socket of the client
    :param client_address: address of the client
    :return: None
    """
    global round_active

    print("New client connected:", client_address)

    message = protocol.receive_message(client_socket)
    if message is None:
        client_socket.close()
        return

    msg_type, fields = protocol.split_message(message)
    if msg_type != MSG_JOIN:
        client_socket.close()
        return

    player = {
        "socket": client_socket,
        "name": fields[0],
        "score": 0,
        "answer": None,
        "answered": False
    }

    with players_lock:
        players.append(player)

    send_to_player(player, MSG_WAIT, "Waiting for the game to start...")
    send_scores()

    try:
        while True:
            message = protocol.receive_message(client_socket)
            if message is None:
                break

            msg_type, fields = protocol.split_message(message)

            if msg_type == MSG_ANSWER and round_active and not player["answered"]:
                player["answer"] = int(fields[0])
                player["answered"] = True
                print(player["name"], "answered", fields[0])

    except (ConnectionResetError, ConnectionAbortedError, OSError):
        pass
    except Exception as e:
        print("Client error:", e)
    finally:
        print("Client disconnected:", player["name"])
        remove_player(player)
        send_scores()


def wait_for_players():
    """
    Wait until enough players are connected.
    :return: None
    """
    print("Waiting for players...")
    while True:
        with players_lock:
            amount = len(players)

        if amount >= MIN_PLAYERS:
            return

        time.sleep(1)


def has_players():
    """
    Check if there is at least one connected player.
    :return: True or False
    """
    with players_lock:
        return len(players) > 0


def reset_answers():
    """
    Reset all answers before a new round.
    :return: None
    """
    with players_lock:
        for player in players:
            player["answer"] = None
            player["answered"] = False


def all_players_answered():
    """
    Check if all connected players answered.
    :return: True or False
    """
    with players_lock:
        if len(players) == 0:
            return False

        for player in players:
            if not player["answered"]:
                return False

    return True


def run_round(question, round_number, total_rounds):
    """
    Run one trivia round.
    :param question: question dictionary
    :param round_number: current round number
    :param total_rounds: total number of rounds
    :return: True if the round finished, False if all players left
    """
    global round_active

    if not has_players():
        return False

    reset_answers()

    data = {
        "round": round_number,
        "total": total_rounds,
        "question": question["question"],
        "options": question["options"],
        "time": QUESTION_TIME
    }

    send_to_all(MSG_QUESTION, data)
    round_active = True

    for seconds_left in range(QUESTION_TIME, 0, -1):
        if not has_players():
            round_active = False
            return False

        send_to_all(MSG_TIMER, seconds_left)
        time.sleep(1)

        if not has_players():
            round_active = False
            return False

        if all_players_answered():
            break

    round_active = False

    if not has_players():
        return False

    check_answers(question)
    return True


def check_answers(question):
    """
    Check the answers and send the result.
    :param question: question dictionary
    :return: None
    """
    correct_index = question["answer"]
    correct_text = question["options"][correct_index]
    scorers = []

    with players_lock:
        for player in players:
            if player["answer"] == correct_index:
                player["score"] += POINTS
                scorers.append(player["name"])

    result = {
        "correct_index": correct_index,
        "correct_text": correct_text,
        "scorers": scorers
    }

    send_to_all(MSG_RESULT, result)
    send_scores()


def end_game():
    """
    Send game over message to all players.
    :return: None
    """
    with players_lock:
        scores = []
        for player in players:
            scores.append([player["name"], player["score"]])

    scores.sort(key=lambda item: item[1], reverse=True)

    if len(scores) == 0:
        winner = "None"
        is_tie = "False"
    else:
        highest_score = scores[0][1]
        winners = []

        for name, score in scores:
            if score == highest_score:
                winners.append(name)

        if len(winners) > 1:
            winner = ", ".join(winners)
            is_tie = "True"
        else:
            winner = winners[0]
            is_tie = "False"

    send_to_all(MSG_GAMEOVER, {
        "winner": winner,
        "is_tie": is_tie,
        "scores": scores
    })


def game_loop():
    """
    Main game loop.
    :return: None
    """
    while True:
        try:
            questions = load_questions()
            if len(questions) == 0:
                print("No questions found")
                return

            wait_for_players()
            send_to_all(MSG_WAIT, "Game starts in 3 seconds...")
            time.sleep(3)

            if not has_players():
                print("All players left before game started")
                disconnect_all_players()
                continue

            game_stopped = False
            for i in range(len(questions)):
                print("Round", i + 1)
                round_finished = run_round(questions[i], i + 1, len(questions))
                if not round_finished:
                    print("All players left. Stopping current game")
                    game_stopped = True
                    break

                time.sleep(3)

                if not has_players():
                    print("All players left. Stopping current game")
                    game_stopped = True
                    break

            if game_stopped:
                disconnect_all_players()
                continue

            end_game()
            time.sleep(2)
            disconnect_all_players()
            print("Game ended.")

        except Exception as e:
            print("Game error:", e)
            disconnect_all_players()


def main():
    """
    Start the server.
    :return: None
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((IP, PORT))
        server_socket.listen()

        print("Server is listening on", IP, PORT)

        threading.Thread(target=game_loop, daemon=True).start()

        while True:
            try:
                client_socket, client_address = server_socket.accept()
                threading.Thread(
                    target=handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                ).start()
            except Exception as e:
                print("Accept error:", e)

    except Exception as e:
        print("Server error:", e)
    finally:
        server_socket.close()


if __name__ == "__main__":
    main()
