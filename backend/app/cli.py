"""Operator commands:  flask --app wsgi <command>   (run from the backend/ folder; see README)."""
from __future__ import annotations

import getpass
import json

import click
from flask import Flask
from sqlalchemy import delete
from datetime import timedelta

from .core.database import check_schema, write_intent
from .exceptions import AppError
from .extensions import db
from .models import ROLE_SYS_ADMIN



def _cli_message(exc) -> str:
    """The real reason behind a validation error: the web text 'Please correct the highlighted fields.' means
    nothing on a terminal, so add the field messages (without repeating the main message)."""
    details = [f"{e['field']}: {e['message']}" for e in (getattr(exc, "field_errors", None) or [])
               if e.get("message") and e.get("message") != exc.message]
    return f"{exc.message} {'; '.join(details)}" if details else exc.message

def register_cli(app: Flask) -> None:
    @app.cli.command("check-schema")
    def check_schema_cmd():
        """Verify every mapped table and column exists (use against Oracle after the DBA runs the DDL)."""
        from .models import Base

        check_schema(db.engine, Base.metadata, db.schema)
        click.echo("Schema OK")

    @app.cli.command("seed-demo")
    def seed_demo_cmd():
        """Seed the demo fixture if the database is empty (normally automatic on demo start)."""
        from .seed.demo_seeder import SeedRefused, seed_if_empty

        try:
            result = seed_if_empty()
        except SeedRefused as exc:
            raise click.ClickException(str(exc)) from None
        click.echo(json.dumps(result) if result else "Database already has data; nothing seeded.")

    @app.cli.command("create-user")
    @click.option("--username", required=True)
    @click.option("--display-name", default=None)
    @click.option("--role", required=True, help="Role code, e.g. SYS_ADMIN, EXECUTIVE, DEPT_HEAD, PROJECT_MGR.")
    @click.option("--department", "departments", multiple=True,
                  help="Department code (repeat for several). Required for department-scoped roles only.")
    def create_user_cmd(username, display_name, role, departments):
        """Create a user. The password is read from a hidden prompt, never from the command line.
        With AUTH_MODE=ldap no password is asked: the user signs in with their Windows password (e.g. U12345)."""
        from sqlalchemy import select

        from .models import Department
        from .services import context, user_service

        ldap_mode = context.settings().is_ldap
        password = note = None
        if ldap_mode:
            try:
                username = user_service.directory_username(username)
            except AppError as exc:
                raise click.ClickException(_cli_message(exc)) from None
            note = user_service.DIRECTORY_ACCOUNT_NOTE
        else:
            password = getpass.getpass("Password (min 8 characters): ")
            if password != getpass.getpass("Repeat password: "):
                raise click.ClickException("Passwords do not match.")
        try:
            with write_intent():
                from .seed.demo_seeder import seed_roles
                seed_roles()  # a new database: the nine roles exist before the first user
                department_ids = []
                for code in departments:
                    found = context.session().scalar(select(Department).where(Department.code == code.strip().upper()))
                    if found is None:
                        raise click.ClickException(f"Department {code} does not exist.")
                    department_ids.append(found.id)
                user = user_service.create_user(username, display_name or username, role.strip().upper(), password,
                                                department_ids=department_ids, note=note)
        except AppError as exc:
            raise click.ClickException(_cli_message(exc)) from None
        click.echo(f"Created {user.role_code} user {user.username} (id {user.id})"
                   + (": signs in with the Windows password" if ldap_mode else ""))

    @app.cli.command("seed-reference")
    @click.option("--actor", required=True, help="Username of the active SYS_ADMIN recorded as creating the lists.")
    def seed_reference_cmd(actor):
        """Add the starting lists (departments, categories, statuses, project types and workflows, spec fields) where
        missing. Works on Oracle too; never adds demo records."""
        from .seed.demo_seeder import seed_reference, seed_roles
        from .services import user_service

        with write_intent():
            seed_roles()
            account = user_service.find(actor)
            if account is None or account.role_code != ROLE_SYS_ADMIN or not account.active:
                raise click.ClickException(f"{actor} is not an active SYS_ADMIN user.")
            counts = seed_reference(account)
        click.echo("Added: " + ", ".join(f"{k} {v}" for k, v in counts.items()))

    @app.cli.command("take-snapshot")
    def take_snapshot_cmd():
        """Store today's KPI values for the month / quarter / year trends (schedule daily)."""
        from sqlalchemy import select

        from .models import AppUser
        from .services import context, snapshot_service

        with write_intent():
            admin = context.session().scalar(select(AppUser).where(AppUser.role_code == ROLE_SYS_ADMIN,
                                                                   AppUser.is_active == 1).order_by(AppUser.id))
            if admin is None:
                raise click.ClickException("No active SYS_ADMIN user.")
            n = snapshot_service.take(admin)
        click.echo(f"Stored {n} values for today")

    @app.cli.command("run-schedules")
    def run_schedules_cmd():
        """Generate the scheduled reports that are due (schedule this daily on the server). Files go to data/reports/."""
        from .services import schedule_service

        with write_intent():
            produced = schedule_service.run_due()
        for item in produced:
            click.echo(f"{item['schedule']}: {item['file']} (for {', '.join(item['recipients'])})")
        click.echo(f"{len(produced)} report(s) generated")

    @app.cli.command("set-break-glass-password")
    def set_break_glass_password_cmd():
        """Create the emergency local SYS_ADMIN (BREAK_GLASS_USERNAME in ldap.env) if missing and set its password from
        a hidden prompt. Used when the company directory is down. Keep the password sealed (DBA or IT)."""
        from .services import context, user_service

        name = context.settings().break_glass_username
        if not name:
            raise click.ClickException("BREAK_GLASS_USERNAME is not set. Put a name such as cpc.breakglass in "
                                       "ldap.env, then run this command again.")
        minimum = user_service.BREAK_GLASS_MIN_PASSWORD
        password = getpass.getpass(f"New password for {name} (min {minimum} characters): ")
        if len(password) < minimum:
            raise click.ClickException(f"The break-glass password must be at least {minimum} characters.")
        if password != getpass.getpass("Repeat password: "):
            raise click.ClickException("Passwords do not match.")
        try:
            with write_intent():
                user, created = user_service.set_break_glass_password(password)
        except AppError as exc:
            raise click.ClickException(_cli_message(exc)) from None
        click.echo(f"{'Created' if created else 'Updated'} the break-glass account {user.username}: password set.")
        if not (user.active and user.role_code == ROLE_SYS_ADMIN):
            click.echo(f"Warning: {user.username} is {'not active' if not user.active else user.role_code}, not an "
                       "active SYS_ADMIN. An administrator must change that in Settings > Users before it can be used.")
        if not context.settings().is_ldap:
            click.echo("Note: AUTH_MODE is local, so every account signs in with the app's own password.")

    @app.cli.command("check-ldap")
    @click.option("--username", default=None, help="Also look up this Windows username, e.g. U12345.")
    def check_ldap_cmd(username):
        """Test the company directory settings (ldap.env): server, certificate, service account, search base and,
        with --username, one user. Passwords are never shown."""
        import dataclasses

        from flask import current_app

        from .core.config import LDAP_ENV_FILE, ConfigError, ldap_settings_from_env
        from .security.directory import Directory
        from .services import context

        settings = context.settings()
        if not settings.is_ldap:
            try:
                settings = dataclasses.replace(settings, **ldap_settings_from_env())
            except ConfigError as exc:
                raise click.ClickException(str(exc)) from None
            click.echo("Note: AUTH_MODE is local, so sign-in does not use the directory yet. Checking the LDAP "
                       "settings anyway.")
            click.echo("")
        click.echo(f"{'Settings file:':<30} {LDAP_ENV_FILE} ({'found' if LDAP_ENV_FILE.is_file() else 'NOT FOUND'})")
        for label, value in (
            ("AUTH_MODE", settings.auth_mode),
            ("LDAP_SERVER", ", ".join(settings.ldap_servers)),
            ("LDAP_PORT", settings.ldap_port),
            ("LDAP_SECURITY", settings.ldap_security),
            ("LDAP_CA_FILE", settings.ldap_ca_file),
            ("LDAP_BASE_DN", settings.ldap_base_dn),
            ("LDAP_BIND_DN", settings.ldap_bind_dn),
            ("LDAP_BIND_PASSWORD", "(set, not shown)" if settings.ldap_bind_password else "(not set)"),
            ("LDAP_USERNAME_ATTRIBUTE", settings.ldap_username_attribute),
            ("LDAP_DISPLAY_NAME_ATTRIBUTE", settings.ldap_display_name_attribute),
            ("LDAP_USERNAME_PATTERN", settings.ldap_username_pattern),
            ("LDAP_TIMEOUT_SECONDS", settings.ldap_timeout_seconds),
            ("BREAK_GLASS_USERNAME", settings.break_glass_username or "(not set: no emergency account)"),
            ("SESSION_IDLE_MINUTES", settings.session_idle_minutes),
            ("SESSION_ABSOLUTE_HOURS", settings.session_absolute_hours),
        ):
            click.echo(f"{label + ':':<30} {value}")
        click.echo("")
        steps = Directory(settings, current_app.config.get("DIRECTORY_CONNECTION_FACTORY")).check(username)
        for step in steps:
            click.echo(f"{'OK  ' if step.ok else 'FAIL'}  {step.message}")
            if step.hint:
                click.echo(f"      What to check: {step.hint}")
        if not steps or not all(step.ok for step in steps):
            raise click.ClickException("The directory check failed (see FAIL above).")
        click.echo("")
        click.echo("All checks passed.")

    @app.cli.command("deactivate-user")
    @click.option("--username", required=True)
    @click.option("--actor", default=None, help="Username of the active ADMIN recorded as making the change.")
    def deactivate_user_cmd(username, actor):
        """Deactivate a user (users are never deleted). Their sessions stop working immediately."""
        from .services import user_service

        account = None
        if actor:
            account = user_service.find(actor)
            if account is None or account.role_code != ROLE_SYS_ADMIN or not account.active:
                raise click.ClickException(f"{actor} is not an active SYS_ADMIN user.")
        existing = user_service.find(username)
        if existing is not None and not existing.active:
            click.echo(f"{username} is already inactive; nothing changed.")
            return
        try:
            with write_intent():
                user_service.set_active(username, False, actor=account)
        except AppError as exc:
            raise click.ClickException(_cli_message(exc)) from None
        click.echo(f"Deactivated {username}")

    @app.cli.command("purge-sessions")
    def purge_sessions_cmd():
        """Delete expired login sessions."""
        from .models import AppSession
        from .services import context

        settings = context.settings()
        cutoff = context.now() - timedelta(minutes=settings.session_idle_minutes)
        absolute = context.now() - timedelta(hours=settings.session_absolute_hours)
        with write_intent():
            session = db.session()
            result = session.execute(
                delete(AppSession).where((AppSession.last_seen_at < cutoff) | (AppSession.created_at < absolute))
            )
            session.commit()
        click.echo(f"Removed {result.rowcount} expired session(s)")
