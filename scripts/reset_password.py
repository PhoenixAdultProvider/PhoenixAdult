from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import phoenixadult.config  # noqa: E402, F401 — loads .env so STATE_DB_PATH resolves
from phoenixadult.utils.auth import user_store  # noqa: E402


def _prompt() -> str:
    first = getpass.getpass('New password: ')
    if len(first) < 8:
        raise SystemExit('Password must be at least 8 characters.')
    if first != getpass.getpass('Confirm password: '):
        raise SystemExit('Passwords do not match.')
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description='Reset a PhoenixAdult account password.')
    parser.add_argument('username')
    parser.add_argument('--create-admin', action='store_true', help='create the user as an admin when it does not exist')
    args = parser.parse_args()

    existing = next((u for u in user_store.list_users() if u['username'].casefold() == args.username.casefold()), None)
    if existing is None and not args.create_admin:
        raise SystemExit(f'No such user: {args.username} (pass --create-admin to create one)')

    password = _prompt()
    if existing is None:
        user_store.create_user(args.username, password, is_admin=True)
        print(f'Created Admin Account: {args.username}')
    else:
        user_store.set_password(int(existing['id']), password, None)
        print(f'Password Updated: {args.username} — All Sessions Signed Out')
    print('Restart the server to clear any login backoff.')


if __name__ == '__main__':
    main()
