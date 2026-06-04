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

from urllib.parse import quote, unquote


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
    except Exception as e:
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
            return None

        separator = receive_exact(sock, 1)
        if separator != SEPARATOR:
            return None

        message_length = int(length_text.decode())
        message_bytes = receive_exact(sock, message_length)
        if message_bytes is None:
            return None

        return message_bytes.decode()
    except Exception as e:
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
        return command

    return command + FIELD_SEPARATOR + FIELD_SEPARATOR.join(encoded_fields)


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

    return LIST_SEPARATOR.join(pairs)


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

    return LIST_SEPARATOR.join(encoded_items)


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

    return decoded_items
