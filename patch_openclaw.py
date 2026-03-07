"""Patch openclaw to fix TimeoutError import for newer cmdop versions."""

import importlib.util
import sys

def patch():
    spec = importlib.util.find_spec("openclaw")
    if spec is None or spec.origin is None:
        print("openclaw is not installed, skipping patch.")
        return

    init_path = spec.origin

    with open(init_path, "r", encoding="utf-8") as f:
        content = f.read()

    old = "from cmdop.exceptions import (\n    CMDOPError,\n    ConnectionError,\n    AuthenticationError,\n    TimeoutError,\n)"
    new = "from cmdop.exceptions import (\n    CMDOPError,\n    ConnectionError,\n    AuthenticationError,\n    ConnectionTimeoutError as TimeoutError,\n)"

    if old not in content:
        if "ConnectionTimeoutError as TimeoutError" in content:
            print("openclaw is already patched.")
        else:
            print("openclaw has unexpected content, skipping patch.")
        return

    content = content.replace(old, new)

    with open(init_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Patched {init_path}")

if __name__ == "__main__":
    patch()
