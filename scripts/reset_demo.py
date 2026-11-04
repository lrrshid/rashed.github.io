"""Reset the local DEMO database (brief section 8, "Persistence and test clock").

Clears the demo SQLite file (plus its -wal / -shm companions) after an explicit typed confirmation and,
optionally, reseeds it straight away. There is deliberately no button for this in the dashboard.

Safety rules:
  * Refuses (exit 2) under the Oracle profile, or any profile other than "demo", or when the configured
    database is not a SQLite file. --yes never overrides this.
  * Refuses (exit 2) when the configured path exists but is not a SQLite database file, or does not end in
    .db / .sqlite / .sqlite3, so a mistyped DEMO_DB_PATH can never delete an unrelated file.
  * Refuses (exit 3) while the app (or anything else) has the file open: "Stop the app first".
  * Only the configured database file and its own -wal / -shm files are ever removed.

Usage (from the project root, with the project virtual environment):
  .venv\\Scripts\\python.exe scripts\\reset_demo.py              # asks you to type RESET DEMO
  .venv\\Scripts\\python.exe scripts\\reset_demo.py --reseed     # reset, then migrate + seed immediately
  .venv\\Scripts\\python.exe scripts\\reset_demo.py --yes --reseed   # no prompt (automation)

Settings are read exactly as the app reads them (environment variables, then the project .env file),
so DEMO_DB_PATH selects the file. Without --reseed the baseline is seeded on the next app start, unless
DEMO_SKIP_SEED=true (then the database stays empty until seed-demo or seed-pagination is run).

Exit codes: 0 done, 1 cancelled (confirmation not given), 2 refused (profile / not a demo SQLite file /
configuration error), 3 database file in use.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import ConfigError, Settings, load_settings, sqlite_path  # noqa: E402

CONFIRMATION = "RESET DEMO"
SQLITE_HEADER = b"SQLite format 3\x00"
ALLOWED_SUFFIXES = (".db", ".sqlite", ".sqlite3")
COMPANION_SUFFIXES = ("-wal", "-shm")

EXIT_OK, EXIT_CANCELLED, EXIT_REFUSED, EXIT_IN_USE = 0, 1, 2, 3


class Refused(Exception):
    def __init__(self, message: str, code: int = EXIT_REFUSED):
        super().__init__(message)
        self.code = code


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="reset_demo.py",
        description="Clear (and optionally reseed) the local demo SQLite database. Refuses under Oracle.",
    )
    parser.add_argument("--profile", choices=("demo", "oracle", "test"), default=None,
                        help="profile to load (default: APP_PROFILE, else demo). Only 'demo' is accepted.")
    parser.add_argument("--yes", action="store_true",
                        help=f"skip the '{CONFIRMATION}' prompt (for automation). Still refuses under Oracle.")
    parser.add_argument("--reseed", action="store_true",
                        help="create the app straight away so the schema is migrated and the baseline seeded")
    return parser.parse_args(argv)


def _requested_profiles(args: argparse.Namespace) -> list[str]:
    return [p.strip().lower() for p in (args.profile, os.environ.get("APP_PROFILE")) if p and p.strip()]


def resolve_target(settings: Settings) -> Path:
    """Return the absolute demo database path, or raise Refused if this is not a demo SQLite database."""
    if settings.profile == "oracle" or settings.data_mode == "oracle":
        raise Refused("Refusing to run: the Oracle profile is active. This command only resets the local demo database.")
    if settings.profile != "demo":
        raise Refused(f"Refusing to run: profile {settings.profile!r} is not the demo profile.")
    path = sqlite_path(settings)
    if path is None:
        raise Refused("Refusing to run: the configured database is not a SQLite file.")
    path = path.resolve()
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise Refused(f"Refusing to run: {path} does not look like a demo database file "
                      f"(expected one of {', '.join(ALLOWED_SUFFIXES)}).")
    if path.exists():
        if not path.is_file():
            raise Refused(f"Refusing to run: {path} is not a file.")
        with path.open("rb") as handle:
            header = handle.read(len(SQLITE_HEADER))
        if header and header != SQLITE_HEADER:
            raise Refused(f"Refusing to run: {path} is not a SQLite database file; nothing was deleted.")
    return path


def delete_database(path: Path) -> list[Path]:
    """Remove the database and its -wal/-shm files. Renames first so nothing is deleted if any file is
    still held open (Windows refuses to rename an open file). Returns the files removed."""
    candidates = [path] + [path.with_name(path.name + s) for s in COMPANION_SUFFIXES]
    present = [p for p in candidates if p.exists()]
    moved: list[tuple[Path, Path]] = []
    try:
        for original in present:
            parked = original.with_name(original.name + ".resetting")
            if parked.exists():
                parked.unlink()
            os.replace(original, parked)
            moved.append((original, parked))
    except PermissionError as exc:
        for original, parked in reversed(moved):
            try:
                os.replace(parked, original)
            except OSError:
                pass
        raise Refused(f"Stop the app first: {exc.filename or path} is in use.", EXIT_IN_USE) from None
    try:
        for _original, parked in moved:
            parked.unlink()
    except PermissionError as exc:
        raise Refused(f"Stop the app first: could not delete {exc.filename}.", EXIT_IN_USE) from None
    return [original for original, _ in moved]


def reseed(settings: Settings) -> dict:
    """Create the app (migrates + seeds the empty file) and return fleet totals from the metrics service."""
    from sqlalchemy import func, select

    from app import create_app
    from app.extensions import db
    from app.models import Defect
    from app.services import metrics_service

    app = create_app(settings)
    try:
        with app.app_context():
            totals = metrics_service.fleet_metrics()
            totals["totalDefects"] = int(db.session().scalar(select(func.count()).select_from(Defect)) or 0)
    finally:
        db.dispose()
    return totals


def main(argv: Sequence[str] | None = None, input_fn: Callable[[str], str] = input) -> int:
    args = _parse_args(argv)
    try:
        if "oracle" in _requested_profiles(args):
            raise Refused("Refusing to run: the Oracle profile is active. "
                          "This command only resets the local demo database.")
        try:
            settings = load_settings(args.profile)
        except ConfigError as exc:
            raise Refused(f"Refusing to run: configuration error: {exc}") from None
        target = resolve_target(settings)

        print(f"Demo database: {target}")
        if not args.yes:
            print(f"This permanently deletes all demo data in that file. Type {CONFIRMATION} to continue.")
            try:
                answer = input_fn("> ")
            except (EOFError, KeyboardInterrupt):
                answer = ""
            if (answer or "").strip() != CONFIRMATION:
                print("Cancelled. Nothing was changed.")
                return EXIT_CANCELLED

        removed = delete_database(target)
        if removed:
            print("Removed: " + ", ".join(p.name for p in removed))
        else:
            print("No database file existed; nothing to remove.")

        if args.reseed:
            totals = reseed(settings)
            if settings.auto_seed:
                print("Reseeded demo database. Totals: "
                      f"stations={totals['activeStations']} ships={totals['activeShips']} "
                      f"defects={totals['totalDefects']} outstanding={totals['outstanding']} "
                      f"critical={totals['criticalOutstanding']} overdue={totals['overdue']}")
            else:
                print("Recreated an empty, migrated database. Not seeded because DEMO_SKIP_SEED=true "
                      "(run 'flask --app wsgi seed-demo' or 'seed-pagination' to add data).")
        elif settings.auto_seed:
            print("Done. The demo data will be reseeded the next time the app starts.")
        else:
            print("Done. DEMO_SKIP_SEED=true, so the app will NOT reseed on its next start; the database stays "
                  "empty until you run seed-demo or seed-pagination.")
        return EXIT_OK
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
