"""
title: server/client project - protocol
author: Ori Kelty
date: 4.12.2025
description: This is the protocol code for the trivia game.
The protocol sends and receives text messages between the client and server
using the format [8 digits length]:[message].

Every message is sent like this:
[8 digits length]:[message]

Example:
00000023:ANSWER|2
"""

import logging
from urllib.parse import quote, unquote


log = logging.getLogger("protocol")


LENGTH_SIZE = 8
SEPARATOR = b":"
FIELD_SEPARATOR = "|"
LIST_SEPARATOR = ";"
PAIR_SEPARATOR = ":"


def send_message(sock, message):
    """
    Send one text message.
    :param sock: socket to send on
    :param message: message string
    :return: None
    """
    try:
        message_bytes = message.encode()
        length = str(len(message_bytes)).zfill(LENGTH_SIZE)
        full_message = length.encode() + SEPARATOR + message_bytes
        sock.sendall(full_message)
        log.info("Sent message: %s", message)
    except Exception as e:
        log.error("Error sending message: %s", e)
        print("Error sending message:", e)


def receive_message(sock):
    """
    Receive one text message.
    :param sock: socket to receive from
    :return: message string, or None if connection is closed
    """
    try:
        length_text = receive_exact(sock, LENGTH_SIZE)
        if length_text is None:
            log.info("Connection closed while receiving message length")
            return None

        separator = receive_exact(sock, 1)
        if separator != SEPARATOR:
            log.warning("Bad protocol separator received")
            return None

        message_length = int(length_text.decode())
        message_bytes = receive_exact(sock, message_length)
        if message_bytes is None:
            log.info("Connection closed while receiving message body")
            return None

        message = message_bytes.decode()
        log.info("Received message: %s", message)
        return message
    except Exception as e:
        log.error("Error receiving message: %s", e)
        print("Error receiving message:", e)
        return None


def receive_exact(sock, size):
    """
    Receive exactly size bytes from the socket.
    :param sock: socket to receive from
    :param size: number of bytes to receive
    :return: bytes, or None if connection is closed
    """
    data = b""

    while len(data) < size:
        try:
            part = sock.recv(size - len(data))
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            log.info("Socket disconnected while receiving exact data")
            return None

        if not part:
            return None
        data += part

    return data


def build_message(command, fields=None):
    """
    Build a protocol message from command and fields.
    :param command: command name
    :param fields: list of fields
    :return: encoded message string
    """
    if fields is None:
        fields = []

    encoded_fields = []
    for field in fields:
        encoded_fields.append(quote(str(field), safe=""))

    if len(encoded_fields) == 0:
        log.debug("Built message: %s", command)
        return command

    message = command + FIELD_SEPARATOR + FIELD_SEPARATOR.join(encoded_fields)
    log.debug("Built message: %s", message)
    return message


def split_message(message):
    """
    Split a protocol message into command and fields.
    :param message: message string
    :return: tuple (command, fields)
    """
    parts = message.split(FIELD_SEPARATOR)
    command = parts[0]
    fields = []

    for field in parts[1:]:
        fields.append(unquote(field))

    log.debug("Split message command=%s fields=%s", command, fields)
    return command, fields


def build_scores(scores):
    """
    Convert scores dictionary to text.
    :param scores: dictionary of name -> score
    :return: encoded scores text
    """
    pairs = []

    for name, score in scores.items():
        pairs.append(quote(str(name), safe="") + PAIR_SEPARATOR + str(score))

    scores_text = LIST_SEPARATOR.join(pairs)
    log.debug("Built scores text: %s", scores_text)
    return scores_text


def split_scores(scores_text):
    """
    Convert scores text back to dictionary.
    :param scores_text: encoded scores text
    :return: dictionary of name -> score
    """
    scores = {}

    if scores_text == "":
        return scores

    pairs = scores_text.split(LIST_SEPARATOR)
    for pair in pairs:
        name, score = pair.split(PAIR_SEPARATOR, 1)
        scores[unquote(name)] = int(score)

    log.debug("Split scores: %s", scores)
    return scores


def build_list(items):
    """
    Convert list to text.
    :param items: list of values
    :return: encoded list text
    """
    encoded_items = []

    for item in items:
        encoded_items.append(quote(str(item), safe=""))

    list_text = LIST_SEPARATOR.join(encoded_items)
    log.debug("Built list text: %s", list_text)
    return list_text


def split_list(list_text):
    """
    Convert text back to list.
    :param list_text: encoded list text
    :return: list of values
    """
    if list_text == "":
        return []

    items = list_text.split(LIST_SEPARATOR)
    decoded_items = []

    for item in items:
        decoded_items.append(unquote(item))

    log.debug("Split list: %s", decoded_items)
    return decoded_items


def run_assert_tests():
    """
    Run simple assert tests for the protocol functions.
    :return: None
    """
    message = build_message("ANSWER", [2])
    assert message == "ANSWER|2", "build_message failed"

    command, fields = split_message("ANSWER|2")
    assert command == "ANSWER", "split_message command failed"
    assert fields == ["2"], "split_message fields failed"

    options = ["4", "6", "8", "10"]
    options_text = build_list(options)
    assert split_list(options_text) == options, "list protocol failed"

    scores = {"Ori": 10, "Noam": 20}
    scores_text = build_scores(scores)
    assert split_scores(scores_text) == scores, "scores protocol failed"

    special_message = build_message("WAIT", ["hello|with;symbols"])
    command, fields = split_message(special_message)
    assert command == "WAIT", "special message command failed"
    assert fields == ["hello|with;symbols"], "special message fields failed"

    log.info("Protocol assert tests passed")


if __name__ == "__main__":
    logging.basicConfig(
        filename="protocol.log",
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filemode="w",
    )
    run_assert_tests()
    print("Protocol assert tests passed")
