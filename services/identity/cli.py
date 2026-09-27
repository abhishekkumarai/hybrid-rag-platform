"""Account administration (IRA-33).

    python -m services.identity.cli create-admin admin@example.com
    python -m services.identity.cli create-user someone@example.com --name "Someone"

The password is prompted for (never passed on the command line, where it would land in shell
history); set RAG_NEW_PASSWORD to script it.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from services.common.config import load_config
from services.identity.passwords import hash_password
from services.identity.store import DuplicateEmailError, PostgresIdentityStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["create-admin", "create-user"])
    parser.add_argument("email")
    parser.add_argument("--name", default="")
    args = parser.parse_args(argv)

    password = os.environ.get("RAG_NEW_PASSWORD") or getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1

    store = PostgresIdentityStore(load_config().auth_postgres_url)
    try:
        user = store.create_user(
            args.email, hash_password(password), display_name=args.name, is_admin=args.command == "create-admin"
        )
    except DuplicateEmailError:
        print(f"An account for {args.email} already exists.", file=sys.stderr)
        return 1
    print(f"Created {'admin' if user.is_admin else 'user'} {user.email} ({user.id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
