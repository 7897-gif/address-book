"""Tests for the Excel export / import round trip."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook, load_workbook  # noqa: E402

from excel_io import (  # noqa: E402
    HEADERS,
    ImportError_,
    export_workbook,
    parse_workbook,
    read_import_file,
    template_workbook,
)
from repository import AddressBook  # noqa: E402
from tests.support import make_temp_dir, remove_temp_dir  # noqa: E402


def make_contact(name, methods, favorite=False, company="Acme"):
    return {
        "name": name,
        "company": company,
        "title": "Engineer",
        "notes": "",
        "favorite": favorite,
        "methods": methods,
    }


class ExportTests(unittest.TestCase):
    def test_header_layout(self):
        data = export_workbook([])
        sheet = load_workbook(io.BytesIO(data)).worksheets[0]

        self.assertEqual([cell.value for cell in sheet[1]], HEADERS)
        self.assertIn("Phone 1", HEADERS)
        self.assertIn("Email 1", HEADERS)
        self.assertEqual(HEADERS[:5], ["Name", "Favorite", "Company", "Title", "Notes"])

    def test_one_row_per_contact_and_one_column_per_method(self):
        contacts = [
            make_contact(
                "Ada",
                [
                    {"kind": "phone", "label": "Mobile", "value": "111"},
                    {"kind": "phone", "label": "Office", "value": "222"},
                    {"kind": "email", "label": "", "value": "ada@example.com"},
                ],
                favorite=True,
            ),
            make_contact("Grace", [{"kind": "qq", "value": "4242"}]),
        ]
        sheet = load_workbook(io.BytesIO(export_workbook(contacts))).worksheets[0]
        rows = list(sheet.iter_rows(min_row=2, values_only=True))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "Ada")
        self.assertEqual(rows[0][1], "Yes")
        self.assertEqual(rows[0][HEADERS.index("Phone 1")], "111")
        self.assertEqual(rows[0][HEADERS.index("Phone 2")], "222")
        self.assertEqual(rows[0][HEADERS.index("Email 1")], "ada@example.com")
        self.assertEqual(rows[1][0], "Grace")
        self.assertEqual(rows[1][1], "No")
        self.assertEqual(rows[1][HEADERS.index("QQ 1")], "4242")

    def test_extra_methods_beyond_reserved_slots_are_ignored(self):
        methods = [{"kind": "phone", "label": "", "value": f"1{i}"} for i in range(5)]
        sheet = load_workbook(io.BytesIO(export_workbook([make_contact("Five Phones", methods)]))).worksheets[0]
        row = list(sheet.iter_rows(min_row=2, values_only=True))[0]
        self.assertEqual(row[HEADERS.index("Phone 3")], "12")
        self.assertIsNone(row[HEADERS.index("Email 1")])


class ImportTests(unittest.TestCase):
    def test_round_trip_preserves_everything(self):
        original = [
            make_contact(
                "Ada Lovelace",
                [
                    {"kind": "phone", "label": "", "value": "+44 20 7946 0000"},
                    {"kind": "phone", "label": "", "value": "+44 20 7946 0001"},
                    {"kind": "email", "label": "", "value": "ada@example.com"},
                    {"kind": "address", "label": "", "value": "12 St James's Square, London"},
                ],
                favorite=True,
            )
        ]
        payloads, result = parse_workbook(export_workbook(original))

        self.assertEqual(result.errors, [])
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["name"], "Ada Lovelace")
        self.assertTrue(payloads[0]["favorite"])
        self.assertEqual(len(payloads[0]["methods"]), 4)
        self.assertEqual(
            [m["value"] for m in payloads[0]["methods"]],
            [
                "+44 20 7946 0000",
                "+44 20 7946 0001",
                "ada@example.com",
                "12 St James's Square, London",
            ],
        )

    def test_template_is_importable(self):
        payloads, result = parse_workbook(template_workbook())
        self.assertEqual(result.errors, [])
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["name"], "Jane Doe")

    def test_missing_name_column_is_rejected(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["First name", "Phone 1"])
        sheet.append(["Ada", "123"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        with self.assertRaises(ImportError_):
            parse_workbook(buffer.getvalue())

    def test_row_without_name_is_reported(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Name", "Phone 1"])
        sheet.append([None, "123"])
        sheet.append(["Grace", "456"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        payloads, result = parse_workbook(buffer.getvalue())
        self.assertEqual([p["name"] for p in payloads], ["Grace"])
        self.assertEqual(result.errors[0]["row"], 2)
        self.assertIn("Name", result.errors[0]["message"])

    def test_blank_rows_are_skipped(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Name", "Phone 1"])
        sheet.append([None, None])
        sheet.append(["Grace", "456"])
        sheet.append(["", ""])
        buffer = io.BytesIO()
        workbook.save(buffer)

        payloads, result = parse_workbook(buffer.getvalue())
        self.assertEqual(len(payloads), 1)
        self.assertEqual(result.skipped_empty, 2)

    def test_column_order_and_extra_columns_are_tolerated(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Phone 1", "Company", "Name", "Unrelated column"])
        sheet.append(["123", "Navy", "Grace", "ignored"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        payloads, _ = parse_workbook(buffer.getvalue())
        self.assertEqual(payloads[0]["name"], "Grace")
        self.assertEqual(payloads[0]["company"], "Navy")
        self.assertEqual(payloads[0]["methods"][0]["value"], "123")

    def test_numeric_cells_are_converted_to_text(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Name", "Phone 1", "QQ 1"])
        sheet.append(["Grace", 4155550132, 88451267])
        buffer = io.BytesIO()
        workbook.save(buffer)

        payloads, _ = parse_workbook(buffer.getvalue())
        values = [m["value"] for m in payloads[0]["methods"]]
        self.assertEqual(values, ["4155550132", "88451267"])

    def test_invalid_file_is_rejected(self):
        with self.assertRaises(ImportError_):
            parse_workbook(b"this is not a workbook")


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_temp_dir()
        self.book = AddressBook(str(Path(self.tmp) / "db.sqlite"))

    def tearDown(self):
        remove_temp_dir(self.tmp)

    def test_import_twice_does_not_duplicate(self):
        contact = make_contact("Ada", [{"kind": "phone", "label": "", "value": "111"}])
        data = export_workbook([contact])

        first, _ = read_import_file(self.book, data)
        second, _ = read_import_file(self.book, data)

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["skippedDuplicates"], ["Ada"])
        self.assertEqual(self.book.stats()["total"], 1)


if __name__ == "__main__":
    unittest.main()
