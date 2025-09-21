import os
from terminal_backend import TerminalBackend

tb = TerminalBackend()

def repl():
    while True:
        try:
            prompt = tb.cmd_pwd(None) + " $ "
            s = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        out = tb.execute(s)
        if out:
            print(out)

if __name__ == "__main__":
    repl()
