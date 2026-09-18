"""
Lionel Agent - Interactive CLI.

Type /help for commands. Any text that doesn't start with "/" goes to chat.
Type /quit to exit.
"""
import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")

from commands.registry import parse_and_dispatch
from agent.chat import chat


def main():
    print("Lionel Agent CLI")
    print("Type /help for commands. Free text goes to chat. /quit to exit.")
    print()

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text in ("/quit", "/exit", "quit", "exit"):
            break

        if text.startswith("/"):
            result = parse_and_dispatch(text)
            if result is not None:
                print(result.text)
                if result.is_error:
                    print("[ERROR]")
        else:
            print("(thinking...)")
            resp = chat(user_id=0, user_message=text, include_skills=True)
            print()
            print(resp.text)
            print()
            print(f"[{resp.provider}/{resp.model} | {resp.tokens_used} tokens | "
                  f"{len(resp.skills_used)} skills used]")
            if resp.skills_used:
                print(f"[skills: {', '.join(resp.skills_used)}]")
            if resp.error:
                print(f"[error: {resp.error}]")


if __name__ == "__main__":
    main()