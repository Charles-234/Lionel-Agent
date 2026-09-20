"""Lionel interfaces package: outside doors with no thinking inside.

Gate rule: external interfaces do not run the core directly without a check.
The Telegram adapter is the first live door, so it must confirm the owner
number exists before it passes any message into the core handler.
"""
