"""Adding many people at once from an Excel file (Settings > Users; owner request, 24 Nov 2026).

The administrator downloads the template (template()), fills one row per person: the username (the U number with
directory sign-in), the full name, the role, the groups (group-scoped roles only) and the password, and uploads it.
check() reads the file and checks every row by the same rules as adding a person by hand (user_service.create_user):
nothing is written. import_file() runs the same check and, only when no row has a problem, adds every row in ONE
transaction (all or nothing), each audited as "Added from an Excel file (row N)".

Passwords: hashed on the way in like any other; the file itself is never kept, and no answer ever contains one. With
directory sign-in (AUTH_MODE=ldap) people sign in with their Windows password, so a password in the file is ignored
(a warning says so); on the demo an empty password gives the demo password; on Oracle a password is required.
Problems and warnings are codes with values (the page words them in English or Arabic).
"""
from __future__ import annotations

import re

from sqlalchemy import func, select

from ..core import xlsx
from ..core.xlsx_read import UnreadableFile, read_rows
from ..exceptions import Conflict, ValidationFailed
from ..models import AppRole, AppUser, Department
from ..security.auth import require_admin
from ..security.directory import normalise_username
from ..security.mock_credentials import MOCK_PASSWORD
from . import context, user_service

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
TEMPLATE_ROWS = 300
AUDIT_NOTE = "Added from an Excel file (row {row})"
MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# key, English heading, Arabic heading, column width
COLUMNS = (
    ("username", "Username (U number)", "اسم المستخدم (رقم U)", 24),
    ("displayName", "Full name", "الاسم الكامل", 32),
    ("role", "Role", "الدور", 28),
    ("groups", "Groups (roles tied to groups only)", "المجاميع (للأدوار المقيّدة بمجاميع فقط)", 38),
    ("password", "Password", "كلمة المرور", 22),
)
_SEPARATORS = re.compile(r"[,،;؛\n]+")


def _norm(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def _heading_key(text: str) -> str | None:
    """Which column a heading cell names (English or Arabic, any letter case, the words in brackets optional)."""
    t = _norm(text)
    if not t:
        return None
    if t.startswith(("username", "user name", "u number", "اسم المستخدم", "رقم u")):
        return "username"
    if t.startswith(("full name", "display name", "name", "الاسم")):
        return "displayName"
    if t.startswith(("role", "الدور")):
        return "role"
    if t.startswith(("group", "المجاميع", "المجموعة", "مجموعة")):
        return "groups"
    if t.startswith(("password", "كلمة المرور", "كلمة السر")):
        return "password"
    return None


def _lookups():
    session = context.session()
    roles = list(session.scalars(select(AppRole).order_by(AppRole.id)))
    groups = list(session.scalars(select(Department).order_by(Department.code)))
    role_by = {}
    for r in roles:
        for name in (r.code, r.name_en, r.name_ar):
            role_by.setdefault(_norm(name), r)
    group_by = {}
    for g in groups:
        for name in (g.code, g.name_en, g.name_ar):
            group_by.setdefault(_norm(name), g)
    return roles, groups, role_by, group_by


def _plan(data: bytes, filename: str) -> tuple[dict, list[dict]]:
    """(the answer for the page, the rows to add with their passwords). Raises ValidationFailed for an unreadable
    file or one without the heading row."""
    if not data:
        raise ValidationFailed.field("file", "The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ValidationFailed.field("file", f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    try:
        rows = read_rows(data, filename, max_rows=MAX_ROWS + 20)
    except UnreadableFile as exc:
        raise ValidationFailed.field("file", str(exc)) from None
    header_at, columns = None, {}
    for index, (_number, cells) in enumerate(rows[:20]):
        found = {}
        for col, text in enumerate(cells):
            key = _heading_key(text)
            if key and key not in found:
                found[key] = col
        if "username" in found and "role" in found:
            header_at, columns = index, found
            break
    if header_at is None:
        raise ValidationFailed.field("file", "The heading row (Username, Full name, Role, Groups, Password) was not "
                                             "found. Use the template from Settings > Users.")
    body = rows[header_at + 1:]
    if len(body) > MAX_ROWS:
        raise ValidationFailed.field("file", f"At most {MAX_ROWS} people in one file.")

    settings = context.settings()
    ldap = settings.is_ldap
    demo_password = settings.profile in ("demo", "test")
    local_demo = settings.profile in ("demo", "test") and settings.local_env
    _roles, _groups, role_by, group_by = _lookups()
    existing = {u.lower() for u in context.session().scalars(select(func.lower(AppUser.username)))}
    seen: dict[str, int] = {}
    answer_rows, to_add = [], []

    def cell(cells: list[str], key: str) -> str:
        col = columns.get(key)
        return (cells[col] if col is not None and col < len(cells) else "").strip()

    for number, cells in body:
        raw_name, display, role_text = cell(cells, "username"), cell(cells, "displayName"), cell(cells, "role")
        groups_text, password = cell(cells, "groups"), cell(cells, "password")
        if not any((raw_name, display, role_text, groups_text, password)):
            continue
        problems, warnings = [], []
        # the username
        username = normalise_username(raw_name) if ldap else raw_name
        if not raw_name:
            problems.append({"code": "USERNAME_MISSING"})
        elif settings.is_break_glass(username):
            problems.append({"code": "BREAK_GLASS"})
        elif ldap and not settings.username_matches_pattern(username):
            problems.append({"code": "NOT_WINDOWS_NAME", "value": raw_name})
        elif not ldap and not (2 <= len(username) <= 120 and user_service.USERNAME_RE.fullmatch(username)):
            problems.append({"code": "USERNAME_INVALID", "value": raw_name})
        elif username.lower().startswith("mock.") and not local_demo:
            problems.append({"code": "MOCK_RESERVED"})
        elif username.lower() in existing:
            problems.append({"code": "USERNAME_EXISTS", "value": username})
        elif username.lower() in seen:
            problems.append({"code": "USERNAME_TWICE", "row": seen[username.lower()]})
        if username and username.lower() not in seen:
            seen[username.lower()] = number
        # the name
        display = display or username
        if len(display) > 160:
            problems.append({"code": "NAME_TOO_LONG"})
        # the role
        role = role_by.get(_norm(role_text)) if role_text else None
        if not role_text:
            problems.append({"code": "ROLE_MISSING"})
        elif role is None:
            problems.append({"code": "ROLE_UNKNOWN", "value": role_text})
        # the groups: only a group-scoped role has them
        group_ids, group_refs = [], []
        names = [g.strip() for g in _SEPARATORS.split(groups_text) if g.strip()]
        if role is not None and role.scope == "DEPARTMENT":
            if not names:
                problems.append({"code": "GROUPS_NEEDED"})
            for name in names:
                group = group_by.get(_norm(name))
                if group is None or group.archived_at is not None:
                    problems.append({"code": "GROUP_UNKNOWN", "value": name})
                elif group.id not in group_ids:
                    group_ids.append(group.id)
                    group_refs.append({"code": group.code, "nameEn": group.name_en, "nameAr": group.name_ar})
        elif role is not None and names:
            warnings.append({"code": "GROUPS_IGNORED"})
        # the password
        password_state = None
        if ldap:
            password_state = "DIRECTORY"
            if password:
                warnings.append({"code": "PASSWORD_IGNORED"})
            password = None
        elif password:
            password_state = "SET"
            if len(password) < 8:
                problems.append({"code": "PASSWORD_SHORT"})
        elif demo_password:
            password_state = "DEMO"
            warnings.append({"code": "DEMO_PASSWORD"})
            password = MOCK_PASSWORD
        else:
            problems.append({"code": "PASSWORD_NEEDED"})
        answer_rows.append({
            "row": number, "username": username, "displayName": display,
            "role": {"code": role.code, "nameEn": role.name_en, "nameAr": role.name_ar} if role else None,
            "groups": group_refs, "password": password_state, "problems": problems, "warnings": warnings})
        if not problems:
            to_add.append({"row": number, "username": username, "displayName": display, "role": role.code,
                           "groupIds": group_ids, "password": password})
    with_problems = sum(1 for r in answer_rows if r["problems"])
    answer = {"rows": answer_rows, "total": len(answer_rows), "ready": len(answer_rows) - with_problems,
              "withProblems": with_problems, "canImport": bool(answer_rows) and not with_problems,
              "directorySignIn": ldap}
    return answer, to_add


def check(actor, data: bytes, filename: str = "") -> dict:
    """What an import of this file would do, row by row. Nothing is written."""
    require_admin(actor)
    answer, _rows = _plan(data, filename)
    context.session().rollback()
    return answer


def import_file(actor, data: bytes, filename: str = "") -> dict:
    """Add every person of the file in one transaction, only when no row has a problem."""
    require_admin(actor)
    answer, rows = _plan(data, filename)
    if not answer["canImport"]:
        raise Conflict("Correct the rows the check marks first; nobody was added." if answer["rows"]
                       else "The file has no people to add.", code="IMPORT_HAS_PROBLEMS")
    session = context.session()
    note_ldap = user_service.DIRECTORY_ACCOUNT_NOTE if answer["directorySignIn"] else None
    added = []
    try:
        for r in rows:
            note = AUDIT_NOTE.format(row=r["row"]) + (f". {note_ldap}" if note_ldap else "")
            user = user_service.create_user(r["username"], r["displayName"], r["role"], r["password"], actor=actor,
                                            department_ids=r["groupIds"], note=note, commit=False)
            added.append({"id": str(user.id), "username": user.username})
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"added": len(added), "users": added}


# ---- the template ----------------------------------------------------------------------------------------------------

def template(lang: str) -> tuple[bytes, str]:
    """The Excel file to fill in: the Users sheet (a role drop-down), the instructions with the roles and the groups,
    and a hidden sheet holding the drop-down's values. Headings and instructions in English or Arabic."""
    ar = lang == "ar"
    roles, groups, _role_by, _group_by = _lookups()
    context.session().rollback()
    label = (lambda en, a: a if ar else en)
    head = xlsx.Style(bold=True, color="FFFFFF", fill="142029", border="B9995A", align="center", valign="center", wrap=True)
    title = xlsx.Style(bold=True, size=14, color="142029")
    bold = xlsx.Style(bold=True)
    muted = xlsx.Style(color="5B646B", wrap=True)

    lists = xlsx.Sheet(label("Lists", "القوائم"), hidden=True)
    role_names = [label(r.name_en, r.name_ar) for r in roles]
    for name in role_names:
        lists.add([name])

    users = xlsx.Sheet(label("Users", "المستخدمون"), right_to_left=ar, freeze_rows=1)
    users.add([xlsx.Cell(label(en, a), head) for _key, en, a, _w in COLUMNS], height=32)
    users.widths = {i: w for i, (_k, _en, _a, w) in enumerate(COLUMNS)}
    role_col = xlsx.column_letter(2)
    users.choices.append((f"{role_col}2:{role_col}{TEMPLATE_ROWS + 1}", xlsx.list_range(lists, 0, len(role_names))))

    guide = xlsx.Sheet(label("Instructions", "التعليمات"), right_to_left=ar)
    guide.widths = {0: 34, 1: 70}
    guide.add([xlsx.Cell(label("Adding people from this file", "إضافة الأشخاص من هذا الملف"), title)], height=24)
    lines = [
        (label("Username (U number)", "اسم المستخدم (رقم U)"),
         label("Required. With Windows (directory) sign-in: the Windows username, for example U12345.",
               "إلزامي. عند الدخول بحساب Windows (دليل الشركة): اسم مستخدم Windows، مثل U12345.")),
        (label("Full name", "الاسم الكامل"), label("The name shown in the system (optional: the username otherwise).",
                                                    "الاسم الظاهر في النظام (اختياري: وإلا يُستخدم اسم المستخدم).")),
        (label("Role", "الدور"), label("Required: choose from the list (the roles are below).",
                                       "إلزامي: اختره من القائمة (الأدوار مذكورة أدناه).")),
        (label("Groups", "المجاميع"),
         label("Only for a role tied to groups (see the roles below): one or more group codes or names, separated by "
               "commas. Every other role sees all groups: leave it empty.",
               "لدور مقيّد بمجاميع فقط (انظر الأدوار أدناه): رمز المجموعة أو اسمها، وأكثر من واحدة بفواصل. "
               "الأدوار الأخرى ترى كل المجاميع: اتركها فارغة.")),
        (label("Password", "كلمة المرور"),
         label("At least 8 characters. With Windows (directory) sign-in leave it empty: people use their Windows "
               "password. On the demo an empty password gives the demo password.",
               "8 أحرف على الأقل. عند الدخول بحساب Windows اتركها فارغة: يدخل الشخص بكلمة مرور Windows. "
               "في النسخة التجريبية تعطي كلمة المرور الفارغة كلمة مرور العرض التجريبي.")),
        (label("Then", "بعد ذلك"),
         label("Settings > Users > Import from Excel: check the file, then import. Nobody is added while a row has a "
               "problem. Delete this file afterwards: it holds passwords.",
               "الإعدادات > المستخدمون > استيراد من Excel: افحص الملف ثم استورده. لا يُضاف أحد ما دام في صف مشكلة. "
               "احذف هذا الملف بعد ذلك: فيه كلمات مرور.")),
    ]
    for name, text in lines:
        guide.add([xlsx.Cell(name, bold), xlsx.Cell(text, muted)])
    guide.add([])
    guide.add([xlsx.Cell(label("Roles", "الأدوار"), title)])
    for r in roles:
        guide.add([xlsx.Cell(label(r.name_en, r.name_ar), bold),
                   label("Tied to groups: fill the Groups column" if r.scope == "DEPARTMENT" else "Sees all groups",
                         "مقيّد بمجموعة: املأ عمود المجاميع" if r.scope == "DEPARTMENT" else "يرى كل المجاميع")])
    guide.add([])
    guide.add([xlsx.Cell(label("Groups", "المجاميع"), title)])
    for g in groups:
        if g.archived_at is None:
            guide.add([xlsx.Cell(g.code, bold), label(g.name_en, g.name_ar)])
    content = xlsx.workbook([users, guide, lists], label("People to add", "الأشخاص المراد إضافتهم"))
    return content, ("cpc-users-template-ar.xlsx" if ar else "cpc-users-template.xlsx")
