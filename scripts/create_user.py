"""Create (or reset) a login account from the command line.

Use this to create the first administrator:
    python -m scripts.create_user --username alice --role ADMIN

The password is read securely from a prompt (or the NEW_USER_PASSWORD env var for automation).
There are no default accounts or passwords.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.session import SessionLocal
from app.models.auth import ROLES, User
from app.services import auth as auth_service
from app.services.auth import AuthError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=ROLES, default="VIEWER")
    parser.add_argument("--display-name")
    parser.add_argument("--reset", action="store_true", help="Reset the password of an existing user instead")
    args = parser.parse_args()

    password = os.environ.get("NEW_USER_PASSWORD")
    if not password:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1

    db = SessionLocal()
    try:
        if args.reset:
            user = db.query(User).filter(User.username == auth_service.normalize_username(args.username)).first()
            if not user:
                print("No such user.", file=sys.stderr)
                return 1
            auth_service.set_password(db, user, password)
            auth_service.audit(db, "password_reset_cli", username=user.username)
        else:
            user = auth_service.create_user(db, username=args.username, password=password, role=args.role,
                                            display_name=args.display_name)
            auth_service.audit(db, "user_created_cli", username=user.username, detail={"role": user.role})
        db.commit()
        print(f"OK: {user.username} ({user.role})")
        return 0
    except AuthError as exc:
        db.rollback()
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
