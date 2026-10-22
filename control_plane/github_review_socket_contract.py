"""Closed, transport-neutral GitHub review frames for the incumbent CEO socket.

Pure constants only; importing this module opens no Executive Runtime, network,
socket, credential, scheduler or database.
"""
FRAME_SCHEMA = "mastermind.github_review_socket_admission.v1"
RESPONSE_SCHEMA = "mastermind.github_review_socket_receipt.v1"
MAX_FRAME_BYTES = 8192
MAX_RESPONSE_BYTES = 8192
