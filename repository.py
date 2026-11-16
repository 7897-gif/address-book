"""Data access layer for contacts and their contact methods."""

from __future__ import annotations

from typing import Any, Iterable

from db import connect, init_db, now

KINDS = ("phone", "email", "wechat", "qq", "address", "other")

KIND_LABELS = {
    "phone": "Phone",
    "email": "Email",
    "wechat": "WeChat",
    "qq": "QQ",
    "address": "Address",
    "other": "Other",
}

MAX_NAME = 80
MAX_FIELD = 120
MAX_VALUE = 200
MAX_NOTES = 2000
MAX_METHODS = 20


class ValidationError(ValueError):
    """Raised when a contact payload cannot be accepted."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "是"}
    return False


def normalize_payload(payload: dict) -> dict:
    """Validate and clean a contact payload coming from the UI or an import.

    Blank contact-method rows are silently dropped (a half-typed row in the
    form should not block saving); a missing name is a hard error.
    """
    errors: list[str] = []
    name = _text(payload.get("name"), MAX_NAME)
    if not name:
        errors.append("Name is required.")

    methods: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    raw_methods = payload.get("methods") or []
    if not isinstance(raw_methods, list):
        errors.append("'methods' must be a list.")
        raw_methods = []

    for index, raw in enumerate(raw_methods):
        if not isinstance(raw, dict):
            continue
        kind = _text(raw.get("kind"), 20).lower() or "phone"
        if kind not in KINDS:
            errors.append(f"Unknown contact method type: {kind!r}.")
            continue
        value = _text(raw.get("value"), MAX_VALUE)
        if not value:
            continue
        label = _text(raw.get("label"), 40)
        key = (kind, label.lower(), value.lower())
        if key in seen:
            continue
        seen.add(key)
        methods.append({"kind": kind, "label": label, "value": value, "position": len(methods)})

    if len(methods) > MAX_METHODS:
        errors.append(f"A contact can hold at most {MAX_METHODS} contact methods.")

    if errors:
        raise ValidationError(errors)

    return {
        "name": name,
        "company": _text(payload.get("company"), MAX_FIELD),
        "title": _text(payload.get("title"), MAX_FIELD),
        "notes": _text(payload.get("notes"), MAX_NOTES),
        "favorite": _bool(payload.get("favorite")),
        "methods": methods,
    }


class AddressBook:
    """A thin repository around one SQLite database file."""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        init_db(self.db_path)

    # ------------------------------------------------------------------ read
    def list_contacts(self, query: str = "", only_favorites: bool = False) -> list[dict]:
        sql = ["SELECT DISTINCT c.* FROM contacts c"]
        where: list[str] = []
        params: list[Any] = []

        query = (query or "").strip()
        if query:
            like = f"%{query}%"
            sql.append("LEFT JOIN contact_methods m ON m.contact_id = c.id")
            where.append(
                "(c.name LIKE ? OR c.company LIKE ? OR c.title LIKE ? OR c.notes LIKE ? OR m.value LIKE ?)"
            )
            params.extend([like, like, like, like, like])

        if only_favorites:
            where.append("c.favorite = 1")

        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY c.favorite DESC, c.name COLLATE NOCASE ASC, c.id ASC")

        with connect(self.db_path) as conn:
            rows = conn.execute(" ".join(sql), params).fetchall()
            contacts = [dict(row) for row in rows]
            self._attach_methods(conn, contacts)
        return contacts

    def get_contact(self, contact_id: int) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if row is None:
                return None
            contact = dict(row)
            self._attach_methods(conn, [contact])
        return contact

    def stats(self) -> dict:
        with connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
            favorites = conn.execute("SELECT COUNT(*) FROM contacts WHERE favorite = 1").fetchone()[0]
            methods = conn.execute("SELECT COUNT(*) FROM contact_methods").fetchone()[0]
        return {"total": total, "favorites": favorites, "methods": methods}

    @staticmethod
    def _attach_methods(conn, contacts: Iterable[dict]) -> None:
        contacts = list(contacts)
        for contact in contacts:
            contact["methods"] = []
        if not contacts:
            return
        ids = [c["id"] for c in contacts]
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT * FROM contact_methods WHERE contact_id IN ({placeholders}) "
            "ORDER BY contact_id, position, id",
            ids,
        ).fetchall()
        by_id = {c["id"]: c for c in contacts}
        for row in rows:
            method = dict(row)
            by_id[method["contact_id"]]["methods"].append(
                {
                    "id": method["id"],
                    "kind": method["kind"],
                    "label": method["label"],
                    "value": method["value"],
                }
            )

    # ----------------------------------------------------------------- write
    def create_contact(self, payload: dict) -> dict:
        data = normalize_payload(payload)
        stamp = now()
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO contacts (name, company, title, notes, favorite, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    data["name"],
                    data["company"],
                    data["title"],
                    data["notes"],
                    int(data["favorite"]),
                    stamp,
                    stamp,
                ),
            )
            contact_id = int(cursor.lastrowid)
            self._replace_methods(conn, contact_id, data["methods"])
            conn.commit()
        return self.get_contact(contact_id)

    def update_contact(self, contact_id: int, payload: dict) -> dict | None:
        data = normalize_payload(payload)
        with connect(self.db_path) as conn:
            exists = conn.execute("SELECT 1 FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if exists is None:
                return None
            conn.execute(
                "UPDATE contacts SET name = ?, company = ?, title = ?, notes = ?, favorite = ?, "
                "updated_at = ? WHERE id = ?",
                (
                    data["name"],
                    data["company"],
                    data["title"],
                    data["notes"],
                    int(data["favorite"]),
                    now(),
                    contact_id,
                ),
            )
            self._replace_methods(conn, contact_id, data["methods"])
            conn.commit()
        return self.get_contact(contact_id)

    def delete_contact(self, contact_id: int) -> bool:
        with connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            conn.commit()
            return cursor.rowcount > 0

    def set_favorite(self, contact_id: int, favorite: bool) -> dict | None:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE contacts SET favorite = ?, updated_at = ? WHERE id = ?",
                (int(bool(favorite)), now(), contact_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return self.get_contact(contact_id)

    def bulk_create(self, payloads: Iterable[dict]) -> list[dict]:
        return [self.create_contact(payload) for payload in payloads]

    def find_duplicate(self, payload: dict) -> dict | None:
        """Return an existing contact that carries exactly the same data.

        Used by the Excel importer so that importing the same sheet twice does
        not create a second copy of every contact. Labels ("Mobile", "Office")
        are a UI concern and are *not* part of the Excel format, so they are
        ignored here — otherwise exporting and re-importing your own address
        book would duplicate every contact whose methods had a label.
        """
        data = normalize_payload(payload)
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, name, company, title, notes FROM contacts WHERE name = ? COLLATE NOCASE",
                (data["name"],),
            ).fetchall()
            candidates = [dict(row) for row in rows]
            self._attach_methods(conn, candidates)

        wanted = sorted((m["kind"], m["value"].lower()) for m in data["methods"])
        for candidate in candidates:
            have = sorted((m["kind"], m["value"].lower()) for m in candidate["methods"])
            if (
                have == wanted
                and candidate["company"] == data["company"]
                and candidate["title"] == data["title"]
                and candidate["notes"] == data["notes"]
            ):
                return candidate
        return None

    @staticmethod
    def _replace_methods(conn, contact_id: int, methods: list[dict]) -> None:
        conn.execute("DELETE FROM contact_methods WHERE contact_id = ?", (contact_id,))
        conn.executemany(
            "INSERT INTO contact_methods (contact_id, kind, label, value, position) "
            "VALUES (?, ?, ?, ?, ?)",
            [(contact_id, m["kind"], m["label"], m["value"], m["position"]) for m in methods],
        )
