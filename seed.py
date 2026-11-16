"""Fill a database with demo contacts: ``python seed.py --reset``."""

from __future__ import annotations

import argparse
from pathlib import Path

from repository import AddressBook

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "data" / "addressbook.db"

DEMO_CONTACTS = [
    {
        "name": "Amelia Chen",
        "company": "Northwind Robotics",
        "title": "Engineering Manager",
        "notes": "Owns the perception team. Prefers short calls on Tuesday mornings.",
        "favorite": True,
        "methods": [
            {"kind": "phone", "label": "Mobile", "value": "+86 138 0000 1122"},
            {"kind": "phone", "label": "Office", "value": "+86 591 8800 1122"},
            {"kind": "email", "label": "Work", "value": "amelia.chen@northwind.example"},
            {"kind": "wechat", "label": "", "value": "amelia_chen"},
        ],
    },
    {
        "name": "Daniel Okafor",
        "company": "Lumen Analytics",
        "title": "Data Scientist",
        "notes": "Met at the 2026 data platform meetup.",
        "favorite": True,
        "methods": [
            {"kind": "phone", "label": "Mobile", "value": "+44 7700 900123"},
            {"kind": "email", "label": "Work", "value": "d.okafor@lumen.example"},
            {"kind": "address", "label": "Office", "value": "18 Finsbury Square, London"},
        ],
    },
    {
        "name": "Sofia Martins",
        "company": "Atlas Design Studio",
        "title": "Product Designer",
        "notes": "Reviews the UI mockups for the course project.",
        "favorite": False,
        "methods": [
            {"kind": "email", "label": "Personal", "value": "sofia.martins@example.com"},
            {"kind": "wechat", "label": "", "value": "sofia_design"},
            {"kind": "other", "label": "Portfolio", "value": "https://sofia.example/portfolio"},
        ],
    },
    {
        "name": "Kenji Watanabe",
        "company": "Sakura Systems",
        "title": "Backend Engineer",
        "notes": "Helped with the SQLite schema review.",
        "favorite": False,
        "methods": [
            {"kind": "phone", "label": "Mobile", "value": "+81 90 1234 5678"},
            {"kind": "email", "label": "Work", "value": "kenji@sakura.example"},
            {"kind": "qq", "label": "", "value": "88451267"},
        ],
    },
    {
        "name": "Priya Raman",
        "company": "Fuzhou University",
        "title": "Lab Instructor",
        "notes": "Office hours: Wednesday 14:00-16:00, Building 3, Room 402.",
        "favorite": True,
        "methods": [
            {"kind": "phone", "label": "Office", "value": "+86 591 2286 0000"},
            {"kind": "email", "label": "Work", "value": "priya.raman@fzu.example"},
            {"kind": "address", "label": "Campus", "value": "2 Xueyuan Road, Minhou, Fuzhou"},
        ],
    },
    {
        "name": "Marcus Weber",
        "company": "Helix Cloud",
        "title": "Site Reliability Engineer",
        "notes": "On-call rotation contact for the deployment week.",
        "favorite": False,
        "methods": [
            {"kind": "phone", "label": "Mobile", "value": "+49 151 2345 6789"},
            {"kind": "email", "label": "Work", "value": "m.weber@helix.example"},
            {"kind": "other", "label": "GitHub", "value": "https://github.com/mweber"},
        ],
    },
    {
        "name": "李思远",
        "company": "厦门大学",
        "title": "研究生",
        "notes": "同一门软件工程课的同学，负责接口测试。",
        "favorite": False,
        "methods": [
            {"kind": "phone", "label": "手机", "value": "+86 139 0000 7788"},
            {"kind": "wechat", "label": "", "value": "lisiyuan_xmu"},
            {"kind": "email", "label": "", "value": "lisiyuan@example.com"},
        ],
    },
    {
        "name": "Hannah Brooks",
        "company": "Meridian Legal",
        "title": "Legal Counsel",
        "notes": "Contact for the open-source licence question.",
        "favorite": False,
        "methods": [
            {"kind": "email", "label": "Work", "value": "h.brooks@meridian.example"},
            {"kind": "phone", "label": "Office", "value": "+1 212 555 0143"},
        ],
    },
]


def seed(book: AddressBook, reset: bool = False) -> int:
    if reset:
        for contact in book.list_contacts():
            book.delete_contact(contact["id"])
    elif book.stats()["total"]:
        return 0

    for payload in DEMO_CONTACTS:
        book.create_contact(payload)
    return len(DEMO_CONTACTS)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Load demo contacts into the address book.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--reset", action="store_true", help="delete existing contacts first")
    args = parser.parse_args(argv)

    book = AddressBook(args.db)
    count = seed(book, reset=args.reset)
    print(f"Inserted {count} demo contacts into {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
