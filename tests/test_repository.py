"""Unit tests for the data access layer.

Run with ``python -m unittest discover -s tests -t .``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repository import AddressBook, ValidationError  # noqa: E402
from tests.support import make_temp_dir, remove_temp_dir  # noqa: E402


def sample(name="Ada Lovelace", **overrides):
    payload = {
        "name": name,
        "company": "Analytical Engines",
        "title": "Mathematician",
        "notes": "First programmer.",
        "favorite": False,
        "methods": [
            {"kind": "phone", "label": "Mobile", "value": "+44 20 7946 0000"},
            {"kind": "email", "label": "Work", "value": "ada@example.com"},
        ],
    }
    payload.update(overrides)
    return payload


class AddressBookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_temp_dir()
        self.book = AddressBook(str(Path(self.tmp) / "test.db"))

    def tearDown(self):
        remove_temp_dir(self.tmp)

    def test_create_and_read_contact_with_methods(self):
        contact = self.book.create_contact(sample())

        self.assertGreater(contact["id"], 0)
        self.assertEqual(contact["name"], "Ada Lovelace")
        self.assertEqual([m["kind"] for m in contact["methods"]], ["phone", "email"])
        self.assertEqual(contact["methods"][0]["label"], "Mobile")
        self.assertFalse(contact["favorite"])

    def test_name_is_required(self):
        with self.assertRaises(ValidationError) as ctx:
            self.book.create_contact(sample(name="   "))
        self.assertIn("Name is required.", ctx.exception.errors)

    def test_unknown_method_kind_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.book.create_contact(sample(methods=[{"kind": "fax", "value": "123"}]))

    def test_blank_method_rows_are_dropped(self):
        contact = self.book.create_contact(
            sample(methods=[{"kind": "phone", "value": "  "}, {"kind": "email", "value": "a@b.c"}])
        )
        self.assertEqual(len(contact["methods"]), 1)

    def test_duplicate_methods_are_collapsed(self):
        contact = self.book.create_contact(
            sample(
                methods=[
                    {"kind": "phone", "label": "", "value": "123"},
                    {"kind": "phone", "label": "", "value": "123"},
                ]
            )
        )
        self.assertEqual(len(contact["methods"]), 1)

    def test_methods_keep_their_order(self):
        contact = self.book.create_contact(
            sample(
                methods=[
                    {"kind": "phone", "value": "1"},
                    {"kind": "email", "value": "2"},
                    {"kind": "phone", "value": "3"},
                ]
            )
        )
        self.assertEqual([m["value"] for m in contact["methods"]], ["1", "2", "3"])

    def test_update_replaces_methods(self):
        contact = self.book.create_contact(sample())
        updated = self.book.update_contact(
            contact["id"],
            sample(company="New Co", methods=[{"kind": "qq", "value": "424242"}]),
        )
        self.assertEqual(updated["company"], "New Co")
        self.assertEqual([m["kind"] for m in updated["methods"]], ["qq"])

    def test_update_unknown_contact_returns_none(self):
        self.assertIsNone(self.book.update_contact(9999, sample()))

    def test_favorite_toggle_and_filter(self):
        contact = self.book.create_contact(sample())
        self.book.create_contact(sample("Grace Hopper"))

        starred = self.book.set_favorite(contact["id"], True)
        self.assertTrue(starred["favorite"])

        favorites = self.book.list_contacts(only_favorites=True)
        self.assertEqual([c["name"] for c in favorites], ["Ada Lovelace"])
        self.assertEqual(self.book.stats()["favorites"], 1)

    def test_favorites_sort_first_then_by_name(self):
        self.book.create_contact(sample("Zoe"))
        self.book.create_contact(sample("Adam"))
        self.book.create_contact(sample("Mary", favorite=True))

        names = [c["name"] for c in self.book.list_contacts()]
        self.assertEqual(names, ["Mary", "Adam", "Zoe"])

    def test_search_matches_name_company_and_methods(self):
        self.book.create_contact(sample())
        self.book.create_contact(sample("Grace Hopper", company="US Navy", methods=[]))

        self.assertEqual([c["name"] for c in self.book.list_contacts("ada")], ["Ada Lovelace"])
        self.assertEqual([c["name"] for c in self.book.list_contacts("navy")], ["Grace Hopper"])
        self.assertEqual([c["name"] for c in self.book.list_contacts("ada@example")], ["Ada Lovelace"])
        self.assertEqual(self.book.list_contacts("nobody"), [])

    def test_delete_removes_methods(self):
        contact = self.book.create_contact(sample())
        self.assertTrue(self.book.delete_contact(contact["id"]))
        self.assertIsNone(self.book.get_contact(contact["id"]))
        self.assertFalse(self.book.delete_contact(contact["id"]))
        self.assertEqual(self.book.stats()["methods"], 0)

    def test_find_duplicate(self):
        payload = sample()
        self.book.create_contact(payload)

        self.assertIsNotNone(self.book.find_duplicate(payload))
        self.assertIsNone(self.book.find_duplicate(sample(methods=[{"kind": "phone", "value": "999"}])))
        self.assertIsNone(self.book.find_duplicate(sample(name="Someone Else")))
        # Labels are cosmetic: the same values under different labels are a duplicate.
        relabelled = sample(
            methods=[
                {"kind": "phone", "label": "Office", "value": "+44 20 7946 0000"},
                {"kind": "email", "label": "", "value": "ada@example.com"},
            ]
        )
        self.assertIsNotNone(self.book.find_duplicate(relabelled))


if __name__ == "__main__":
    unittest.main()
