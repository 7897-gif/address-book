"""End-to-end tests against a real HTTP server on a random port."""

from __future__ import annotations

import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from excel_io import export_workbook  # noqa: E402
from server import create_server  # noqa: E402
from tests.support import make_temp_dir, remove_temp_dir  # noqa: E402

BASE_DIR = Path(__file__).resolve().parents[1]


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = make_temp_dir()
        db_path = str(Path(cls.tmp) / "http.db")
        cls.server = create_server("127.0.0.1", 0, db_path, BASE_DIR / "static")
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        remove_temp_dir(cls.tmp)

    # ------------------------------------------------------------- helpers
    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        payload = body
        all_headers = dict(headers or {})
        if isinstance(body, dict):
            payload = json.dumps(body).encode()
            all_headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=all_headers)
        response = conn.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type") or ""
        conn.close()
        if "json" in content_type:
            return response.status, json.loads(raw.decode("utf-8")), response
        return response.status, raw, response

    def create(self, name, **overrides):
        payload = {
            "name": name,
            "company": "Acme",
            "title": "Engineer",
            "notes": "",
            "favorite": False,
            "methods": [{"kind": "phone", "label": "Mobile", "value": "+1 555 0100"}],
        }
        payload.update(overrides)
        status, body, _ = self.request("POST", "/api/contacts", payload)
        self.assertEqual(status, 201, body)
        return body["contact"]

    def multipart(self, filename, data):
        boundary = "----addressbookboundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
        ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
        return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    # ---------------------------------------------------------------- tests
    def test_index_page_is_served(self):
        status, body, response = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Address Book", body.decode("utf-8"))
        self.assertIn("text/html", response.getheader("Content-Type"))

    def test_static_assets_are_served(self):
        for path in ("/css/style.css", "/js/app.js"):
            status, body, _ = self.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertGreater(len(body), 100, path)

    def test_path_traversal_is_blocked(self):
        status, _, _ = self.request("GET", "/../app.py")
        self.assertEqual(status, 404)

    def test_create_list_update_delete(self):
        contact = self.create(
            "HTTP Tester",
            methods=[{"kind": "phone", "value": "123"}, {"kind": "email", "value": "http@example.com"}],
        )
        self.assertEqual(contact["name"], "HTTP Tester")
        self.assertEqual(len(contact["methods"]), 2)

        status, body, _ = self.request("GET", "/api/contacts")
        self.assertEqual(status, 200)
        names = [item["name"] for item in body["items"]]
        self.assertIn("HTTP Tester", names)
        self.assertGreaterEqual(body["stats"]["total"], 1)

        status, body, _ = self.request("GET", f"/api/contacts/{contact['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(body["contact"]["name"], "HTTP Tester")

        status, body, _ = self.request(
            "PUT",
            f"/api/contacts/{contact['id']}",
            {"name": "HTTP Tester 2", "methods": [{"kind": "qq", "value": "42"}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["contact"]["name"], "HTTP Tester 2")
        self.assertEqual(body["contact"]["methods"][0]["kind"], "qq")

        status, body, _ = self.request("DELETE", f"/api/contacts/{contact['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(body["deleted"], contact["id"])

        status, _, _ = self.request("GET", f"/api/contacts/{contact['id']}")
        self.assertEqual(status, 404)

    def test_validation_error_returns_400(self):
        status, body, _ = self.request("POST", "/api/contacts", {"name": "  "})
        self.assertEqual(status, 400)
        self.assertIn("Name is required.", body["errors"])

    def test_favorite_endpoint(self):
        contact = self.create("Favourite Tester")
        status, body, _ = self.request("POST", f"/api/contacts/{contact['id']}/favorite", {"favorite": True})
        self.assertEqual(status, 200)
        self.assertTrue(body["contact"]["favorite"])

        status, body, _ = self.request("GET", "/api/contacts?favorite=1")
        self.assertEqual(status, 200)
        self.assertTrue(all(item["favorite"] for item in body["items"]))
        self.assertIn("Favourite Tester", [item["name"] for item in body["items"]])

    def test_search_endpoint(self):
        self.create("Searchable Person", company="Deep Sea Labs")
        status, body, _ = self.request("GET", "/api/contacts?q=deep%20sea")
        self.assertEqual(status, 200)
        self.assertEqual([item["name"] for item in body["items"]], ["Searchable Person"])

    def test_export_returns_xlsx(self):
        self.create("Exported Person")
        status, body, response = self.request("GET", "/api/export")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"PK"))
        self.assertIn("attachment", response.getheader("Content-Disposition"))

    def test_import_sheet(self):
        data = export_workbook(
            [
                {
                    "name": "Imported Person",
                    "company": "Import Co",
                    "title": "Analyst",
                    "notes": "",
                    "favorite": True,
                    "methods": [{"kind": "phone", "label": "", "value": "+86 138 0000 0000"}],
                }
            ]
        )
        body, headers = self.multipart("contacts.xlsx", data)
        status, payload, _ = self.request("POST", "/api/import", body, headers)

        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["created"], 1)
        self.assertEqual(payload["errors"], [])

        status, payload, _ = self.request("GET", "/api/contacts?q=Imported")
        self.assertEqual([item["name"] for item in payload["items"]], ["Imported Person"])

    def test_import_rejects_bad_file(self):
        body, headers = self.multipart("contacts.xlsx", b"not a workbook")
        status, payload, _ = self.request("POST", "/api/import", body, headers)
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_unknown_route_returns_404_json(self):
        status, body, _ = self.request("GET", "/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_template_download(self):
        status, body, response = self.request("GET", "/api/template")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"PK"))
        self.assertIn("template", response.getheader("Content-Disposition"))


if __name__ == "__main__":
    unittest.main()
