"""Create/upgrade the database schema by running the Alembic migrations."""
import subprocess
import sys

if __name__ == "__main__":
    sys.exit(subprocess.call(["alembic", "upgrade", "head"]))
