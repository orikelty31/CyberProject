"""
title: server/client project - server
author: Ori Kelty
date: 04.06.2026
description: This is the server code for the trivia game.
The server handles client connections, reads questions from questions.json,
sends questions, receives answers, calculates scores, handles ties,
and starts a new game after the previous game ends.
"""

import json
import logging
import os
import random
import socket
import threading
import time

import protocol


log = logging.getLogger("server")

IP = "0.0.0.0"
PORT = 5555
QUESTIONS_FILE = "questions.json"
MIN_PLAYERS = 2
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
        log.info("Loaded %s questions from %s", len(good_questions), path)
        return good_questions[:NUM_ROUNDS]
    except Exception as e:
        log.error("Error loading questions: %s", e)
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
    log.info("Sent %s to %s", msg_type, player["name"])


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
            log.warning("Failed sending %s to %s", msg_type, player["name"])
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

    log.info("Sending scores: %s", scores)
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
            log.info("Removed player: %s", player["name"])

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
            log.info("Disconnected player after game: %s", player["name"])
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
    log.info("New client connected: %s", client_address)

    message = protocol.receive_message(client_socket)
    if message is None:
        log.warning("Client connected but did not send JOIN")
        client_socket.close()
        return

    msg_type, fields = protocol.split_message(message)
    if msg_type != MSG_JOIN:
        log.warning("Client sent bad first message: %s", msg_type)
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

    log.info("Player joined: %s", player["name"])
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
                log.info("Player %s answered %s", player["name"], fields[0])

    except (ConnectionResetError, ConnectionAbortedError, OSError):
        log.info("Player disconnected suddenly: %s", player["name"])
        pass
    except Exception as e:
        log.error("Client error for %s: %s", player["name"], e)
        print("Client error:", e)
    finally:
        print("Client disconnected:", player["name"])
        log.info("Client disconnected: %s", player["name"])
        remove_player(player)
        send_scores()


def wait_for_players():
    """
    Wait until enough players are connected.
    :return: None
    """
    print("Waiting for players...")
    log.info("Waiting for players")
    while True:
        with players_lock:
            amount = len(players)

        if amount >= MIN_PLAYERS:
            log.info("Enough players connected: %s", amount)
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
    log.info("Reset all player answers")


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
        log.info("Round cannot start because there are no players")
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
    log.info("Started round %s/%s: %s", round_number, total_rounds, question["question"])

    for seconds_left in range(QUESTION_TIME, 0, -1):
        if not has_players():
            round_active = False
            log.info("Stopping round because all players left")
            return False

        send_to_all(MSG_TIMER, seconds_left)
        time.sleep(1)

        if not has_players():
            round_active = False
            log.info("Stopping round because all players left")
            return False

        if all_players_answered():
            log.info("All players answered in round %s", round_number)
            break

    round_active = False

    if not has_players():
        log.info("Skipping answer check because all players left")
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

    log.info("Correct answer is %s. Scorers: %s", correct_text, scorers)
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
    log.info("Final scores: %s", scores)

    winner, is_tie = get_winner_data(scores)

    if is_tie == "True":
        log.info("Game ended with tie between: %s", winner)
    else:
        log.info("Game winner: %s", winner)

    send_to_all(MSG_GAMEOVER, {
        "winner": winner,
        "is_tie": is_tie,
        "scores": scores
    })


def get_winner_data(scores):
    """
    Get winner and tie status from sorted scores.
    :param scores: list of [name, score]
    :return: tuple (winner, is_tie)
    """
    scores.sort(key=lambda item: item[1], reverse=True)

    if len(scores) == 0:
        return "None", "False"

    highest_score = scores[0][1]
    winners = []

    for name, score in scores:
        if score == highest_score:
            winners.append(name)

    if len(winners) > 1:
        return ", ".join(winners), "True"

    return winners[0], "False"


def game_loop():
    """
    Main game loop.
    :return: None
    """
    while True:
        try:
            questions = load_questions()
            if len(questions) == 0:
                log.error("No questions found")
                print("No questions found")
                return

            wait_for_players()
            send_to_all(MSG_WAIT, "Game starts in 3 seconds...")
            log.info("Game starts in 3 seconds")
            time.sleep(3)

            if not has_players():
                log.info("All players left before game started")
                print("All players left before game started")
                disconnect_all_players()
                continue

            game_stopped = False
            for i in range(len(questions)):
                print("Round", i + 1)
                log.info("Starting round %s", i + 1)
                round_finished = run_round(questions[i], i + 1, len(questions))
                if not round_finished:
                    log.info("All players left. Stopping current game")
                    print("All players left. Stopping current game")
                    game_stopped = True
                    break

                time.sleep(3)

                if not has_players():
                    log.info("All players left. Stopping current game")
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
            log.info("Game ended")

        except Exception as e:
            log.error("Game error: %s", e)
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
        log.info("Server is listening on %s:%s", IP, PORT)

        threading.Thread(target=game_loop, daemon=True).start()
        log.info("Game loop thread started")

        while True:
            try:
                client_socket, client_address = server_socket.accept()
                threading.Thread(
                    target=handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                ).start()
            except Exception as e:
                log.error("Accept error: %s", e)
                print("Accept error:", e)

    except Exception as e:
        log.error("Server error: %s", e)
        print("Server error:", e)
    finally:
        server_socket.close()
        log.info("Server socket closed")


def run_assert_tests():
    """
    Run simple assert tests for the server logic.
    :return: None
    """
    assert PORT > 0, "PORT must be positive"
    assert MIN_PLAYERS >= 1, "MIN_PLAYERS must be at least 1"
    assert QUESTION_TIME > 0, "QUESTION_TIME must be positive"
    assert POINTS > 0, "POINTS must be positive"

    questions = load_questions()
    assert len(questions) > 0, "questions.json must contain questions"

    first_question = questions[0]
    assert "question" in first_question, "question field missing"
    assert "options" in first_question, "options field missing"
    assert "answer" in first_question, "answer field missing"
    assert len(first_question["options"]) == 4, "question must have 4 options"
    assert 0 <= first_question["answer"] <= 3, "answer index must be 0-3"

    winner, is_tie = get_winner_data([["Ori", 20], ["Noam", 10], ["Dana", 0]])
    assert winner == "Ori", "winner check failed"
    assert is_tie == "False", "winner tie flag failed"

    winner, is_tie = get_winner_data([["Ori", 20], ["Noam", 20], ["Dana", 10]])
    assert winner == "Ori, Noam", "tie winner check failed"
    assert is_tie == "True", "tie flag check failed"

    log.info("Server assert tests passed")


if __name__ == "__main__":
    logging.basicConfig(
        filename="server.log",
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filemode="w",
    )
    protocol.run_assert_tests()
    run_assert_tests()
    main()
