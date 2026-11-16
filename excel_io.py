"""Excel import / export built on openpyxl.

Export layout — one row per contact, one column per kind of information:

    Name | Favorite | Company | Title | Notes | Phone 1 | Phone 2 | Phone 3 |
    Email 1 | Email 2 | Email 3 | WeChat 1 | WeChat 2 | QQ 1 | Address 1 | Other 1 | Other 2

Import understands the same layout, and is tolerant about column order and
extra columns.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from repository import KIND_LABELS, MAX_METHODS, normalize_payload

SHEET_TITLE = "Contacts"

#: ``(kind, how many columns are reserved for it)``
METHOD_SLOTS = (
    ("phone", 3),
    ("email", 3),
    ("wechat", 2),
    ("qq", 1),
    ("address", 1),
    ("other", 2),
)

BASE_HEADERS = ["Name", "Favorite", "Company", "Title", "Notes"]


def method_headers() -> list[tuple[str, str, int]]:
    """Return ``(header, kind, slot)`` triples in export order."""
    headers: list[tuple[str, str, int]] = []
    for kind, count in METHOD_SLOTS:
        for slot in range(1, count + 1):
            headers.append((f"{KIND_LABELS[kind]} {slot}", kind, slot))
    return headers


HEADERS = BASE_HEADERS + [h for h, _, _ in method_headers()]

MAX_IMPORT_ROWS = 5000
MAX_IMPORT_BYTES = 5 * 1024 * 1024

HEADER_FILL = PatternFill("solid", fgColor="1F2A44")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center")
THIN = Side(style="thin", color="D6DBE5")
CELL_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
YES_FONT = Font(bold=True, color="B45309")


@dataclass
class ImportResult:
    created: int = 0
    skipped_duplicates: list[str] = field(default_factory=list)
    skipped_empty: int = 0
    errors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return self.created + len(self.skipped_duplicates) + self.skipped_empty + len(self.errors)

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "skippedDuplicates": self.skipped_duplicates,
            "skippedEmpty": self.skipped_empty,
            "errors": self.errors,
            "warnings": self.warnings,
            "totalRows": self.total_rows,
        }


class ImportError_(ValueError):
    """Raised when the uploaded file is not a usable address-book sheet."""


# --------------------------------------------------------------------- export
def export_workbook(contacts: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_TITLE
    sheet.append(HEADERS)

    for contact in contacts:
        by_slot: dict[tuple[str, int], str] = {}
        counters: dict[str, int] = {}
        for method in contact.get("methods", []):
            kind = method["kind"]
            counters[kind] = counters.get(kind, 0) + 1
            slot = counters[kind]
            limit = dict(METHOD_SLOTS).get(kind, 0)
            if slot <= limit:
                by_slot[(kind, slot)] = method["value"]

        row = [
            contact["name"],
            "Yes" if contact.get("favorite") else "No",
            contact.get("company", ""),
            contact.get("title", ""),
            contact.get("notes", ""),
        ]
        row += [by_slot.get((kind, slot), "") for _, kind, slot in method_headers()]
        sheet.append(row)

    _style_sheet(sheet, len(contacts))
    _autosize(sheet)
    return _to_bytes(workbook)


def template_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_TITLE
    sheet.append(HEADERS)
    sheet.append(
        [
            "Jane Doe",
            "Yes",
            "Acme Ltd.",
            "Product Manager",
            "Met at the 2026 developer meetup.",
            "+1 415 555 0132",
            "+1 415 555 0199",
            "",
            "jane.doe@example.com",
            "",
            "",
            "jane_doe",
            "",
            "",
            "1 Market Street, San Francisco",
            "",
            "",
        ]
    )
    _style_sheet(sheet, 1)
    _autosize(sheet)

    guide = workbook.create_sheet("How to fill in")
    guide.column_dimensions["A"].width = 4
    guide.column_dimensions["B"].width = 92
    guide["B1"] = "Import rules"
    guide["B1"].font = Font(bold=True, size=14)
    rules = [
        "Row 1 is the header row: do not rename, reorder or delete it (extra columns are ignored).",
        "Every following row is one contact. A row without a Name is reported as an error and skipped.",
        "Favorite accepts Yes / No (also true, false, 1 and 0).",
        "Repeat a kind of contact method by filling the next numbered column, e.g. Phone 1, Phone 2, Phone 3.",
        "Each numbered column is imported as a separate contact method; empty cells are simply ignored.",
        "Blank rows are skipped. Re-importing the same sheet will not create duplicates.",
        "The file must stay in .xlsx format and be smaller than 5 MB.",
    ]
    for index, rule in enumerate(rules, start=2):
        guide[f"B{index}"] = rule
        guide[f"B{index}"].alignment = Alignment(wrap_text=True, vertical="top")

    return _to_bytes(workbook)


def _style_sheet(sheet, data_rows: int) -> None:
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGN
        cell.border = CELL_BORDER
    sheet.row_dimensions[1].height = 24

    for row in sheet.iter_rows(min_row=2, max_row=max(data_rows + 1, 2)):
        for cell in row:
            cell.border = CELL_BORDER
            cell.alignment = Alignment(vertical="center")
        row[1].alignment = Alignment(horizontal="center", vertical="center")
        if row[1].value == "Yes":
            row[1].font = YES_FONT

    sheet.freeze_panes = "A2"
    if data_rows:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{data_rows + 1}"


def _autosize(sheet) -> None:
    widths = {"Name": 20, "Favorite": 10, "Company": 22, "Title": 18, "Notes": 40}
    for index, header in enumerate(HEADERS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = widths.get(header, 20)


def _to_bytes(workbook: Workbook) -> bytes:
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------- import
def parse_workbook(data: bytes) -> tuple[list[dict], ImportResult]:
    """Parse an uploaded workbook into contact payloads plus a result summary."""
    if not data:
        raise ImportError_("The uploaded file is empty.")
    if len(data) > MAX_IMPORT_BYTES:
        raise ImportError_("The file is larger than 5 MB.")

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises a variety of errors for bad files
        raise ImportError_(f"'{exc}' — please upload an .xlsx file exported or created from the template.") from exc

    try:
        sheet = workbook.worksheets[0]
    except IndexError as exc:  # pragma: no cover - openpyxl always has one sheet
        raise ImportError_("The workbook does not contain any sheet.") from exc

    rows = sheet.iter_rows(values_only=True)
    header_row = next(rows, None)
    if header_row is None:
        raise ImportError_("The sheet is empty; row 1 must contain the column headers.")

    mapping = _map_headers(header_row)
    if "name" not in mapping:
        raise ImportError_(
            "The sheet has no 'Name' column. Download the template to see the expected layout."
        )

    result = ImportResult()
    payloads: list[dict] = []

    for offset, row in enumerate(rows, start=2):
        if offset - 1 > MAX_IMPORT_ROWS:
            result.errors.append({"row": offset, "message": f"Stopped after {MAX_IMPORT_ROWS} rows."})
            break
        if row is None or all(_is_blank(value) for value in row):
            result.skipped_empty += 1
            continue

        payload, error = _row_to_payload(row, mapping)
        if error:
            result.errors.append({"row": offset, "message": error})
            continue
        payloads.append(payload)

    return payloads, result


def _row_to_payload(row: tuple, mapping: dict) -> tuple[dict | None, str | None]:
    def get(column_index: int | None):
        if column_index is None or column_index >= len(row):
            return None
        return row[column_index]

    name = get(mapping["name"])
    if _is_blank(name):
        return None, "Name is empty."

    payload = {
        "name": str(name).strip(),
        "favorite": _as_bool(get(mapping.get("favorite"))),
        "company": _as_text(get(mapping.get("company"))),
        "title": _as_text(get(mapping.get("title"))),
        "notes": _as_text(get(mapping.get("notes"))),
        "methods": [],
    }

    for (kind, slot), columns in mapping["methods"].items():
        for column in columns:
            value = _as_text(get(column))
            if not value:
                continue
            payload["methods"].append({"kind": kind, "label": "", "value": value})
            break

    if len(payload["methods"]) > MAX_METHODS:
        return None, f"Too many contact methods ({len(payload['methods'])})."

    try:
        payload = normalize_payload(payload)
    except ValueError as exc:
        reasons = getattr(exc, "errors", None) or [str(exc)]
        return None, " ".join(reasons)

    return payload, None


def _map_headers(header_row: tuple) -> dict:
    mapping: dict = {"methods": {}}
    for index, raw in enumerate(header_row):
        if raw is None:
            continue
        header = str(raw).strip().lower()
        if not header:
            continue
        if header in {"name", "favorite", "company", "title", "notes"}:
            mapping.setdefault(header, index)
            continue

        match = re.fullmatch(r"([a-z]+)\s*(\d+)?", header)
        if not match:
            continue
        kind = match.group(1)
        slot = int(match.group(2) or 1)
        if kind in dict(METHOD_SLOTS):
            mapping["methods"].setdefault((kind, slot), []).append(index)

    return mapping


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "是"}
    return False


def read_import_file(book, data: bytes) -> tuple[dict, list[dict]]:
    """Parse a file and persist the new contacts; returns (summary, new contacts)."""
    payloads, result = parse_workbook(data)
    created: list[dict] = []
    for payload in payloads:
        if book.find_duplicate(payload) is not None:
            result.skipped_duplicates.append(payload["name"])
            continue
        created.append(book.create_contact(payload))
        result.created += 1
    return result.to_dict(), created
