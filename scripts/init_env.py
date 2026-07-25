#!/usr/bin/env python3
"""Materialize the `*.env.example` templates under parallel/services into real
`*.env` files with random secrets, so a fresh clone never runs on checked-in
placeholder credentials. Existing `*.env` files are left untouched.

Placeholders look like GENERATE:<name>. The same <name> always resolves to the
same generated value across every file in one run (e.g. the RabbitMQ password
must match between the rabbitmq service's own env file and the api/worker env
files that connect to it); different <name>s get independent values.
"""
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER_RE = re.compile(r"GENERATE:(\w+)")


def main() -> None:
    generated: dict[str, str] = {}
    examples = sorted(ROOT.glob("parallel/services/**/*.env.example"))
    if not examples:
        print("No *.env.example files found.")
        return

    for example in examples:
        target = example.with_suffix("")  # drop the trailing .example
        if target.exists():
            print(f"skip {target.relative_to(ROOT)} (already exists)")
            continue

        def substitute(match: re.Match) -> str:
            name = match.group(1)
            if name not in generated:
                generated[name] = secrets.token_urlsafe(24)
            return generated[name]

        target.write_text(PLACEHOLDER_RE.sub(substitute, example.read_text()))
        print(f"created {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
