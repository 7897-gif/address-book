"""Record a short demo of the address book as an animated GIF.

Drives a headless Edge/Chrome through the DevTools Protocol using nothing but the
standard library: a minimal WebSocket client, ``Page.startScreencast`` for frames,
and ``Runtime.evaluate`` to click the real UI.

Usage (the server must already be running on http://127.0.0.1:8000):

    python tools/record_demo.py --url http://127.0.0.1:8000/ --out docs/demo/demo.gif
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import struct
import subprocess
import io
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from PIL import Image

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


# --------------------------------------------------------------------- websocket
class WebSocket:
    """Just enough RFC 6455 for the DevTools Protocol."""

    def __init__(self, url: str):
        assert url.startswith("ws://"), url
        rest = url[len("ws://"):]
        host_port, _, path = rest.partition("/")
        host, _, port = host_port.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("websocket handshake failed")
            response += chunk
        if b"101" not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"websocket handshake rejected: {response[:120]!r}")

    def _read_exact(self, count: int) -> bytes:
        buffer = b""
        while len(buffer) < count:
            chunk = self.sock.recv(count - len(buffer))
            if not chunk:
                raise ConnectionError("websocket closed")
            buffer += chunk
        return buffer

    def send(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x81])
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv(self) -> str:
        message = b""
        while True:
            first, second = self._read_exact(2)
            fin = first & 0x80
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            if second & 0x80:
                mask = self._read_exact(4)
                data = bytes(byte ^ mask[index % 4] for index, byte in enumerate(self._read_exact(length)))
            else:
                data = self._read_exact(length)

            if opcode == 0x8:
                raise ConnectionError("websocket closed by peer")
            if opcode == 0x9:
                self.sock.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
                continue
            message += data
            if fin:
                return message.decode()


class CDP:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.next_id = 1
        self.events: list[dict] = []

    def call(self, method: str, params: dict | None = None, session: str | None = None, timeout: float = 30):
        message_id = self.next_id
        self.next_id += 1
        payload = {"id": message_id, "method": method, "params": params or {}}
        if session:
            payload["sessionId"] = session
        self.ws.send(json.dumps(payload))

        deadline = time.time() + timeout
        while time.time() < deadline:
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            if "method" in message:
                self.events.append(message)
        raise TimeoutError(method)


# ------------------------------------------------------------------- recording
def pick_browser() -> str:
    for candidate in EDGE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise SystemExit("No Edge/Chrome binary found.")


def launch_browser(port: int, profile: str) -> subprocess.Popen:
    return subprocess.Popen(
        [
            pick_browser(),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--hide-scrollbars",
            "--window-size=1280,800",
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={port}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_devtools(port: int, timeout: float = 20) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as reply:
                return json.load(reply)["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.25)
    raise SystemExit("DevTools endpoint did not start.")


class Session:
    def __init__(self, cdp: CDP, session_id: str):
        self.cdp = cdp
        self.id = session_id

    def call(self, method: str, params: dict | None = None, timeout: float = 30):
        return self.cdp.call(method, params, session=self.id, timeout=timeout)

    def js(self, expression: str, await_promise: bool = False):
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": await_promise, "returnByValue": True},
        )
        if result.get("exceptionDetails"):
            raise RuntimeError(f"JS failed: {result['exceptionDetails'].get('text')} :: {expression[:120]}")
        return result.get("result", {}).get("value")


def record(url: str, out_path: Path, width: int = 1000, quality: int = 55, fps: int = 8):
    port = 9333
    profile = tempfile.mkdtemp(prefix="cdp-profile-")
    browser = launch_browser(port, profile)
    frames: list[tuple[float, bytes]] = []
    try:
        ws = WebSocket(wait_for_devtools(port))
        cdp = CDP(ws)
        target = cdp.call("Target.createTarget", {"url": "about:blank"})
        attached = cdp.call("Target.attachToTarget", {"targetId": target["targetId"], "flatten": True})
        session = Session(cdp, attached["sessionId"])

        session.call("Page.enable")
        session.call("Runtime.enable")
        session.call("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 800, "deviceScaleFactor": 1, "mobile": False})
        session.call("Page.navigate", {"url": url})

        def pump(seconds: float) -> None:
            """Keep receiving screencast frames while the page does something."""
            end = time.time() + seconds
            while time.time() < end:
                try:
                    message = json.loads(ws.recv())
                except socket.timeout:
                    continue
                cdp.events.append(message)
                if message.get("method") == "Page.screencastFrame":
                    params = message["params"]
                    frames.append((params["metadata"]["timestamp"], base64.b64decode(params["data"])))
                    # Ack without waiting for the reply: a nested call() would read
                    # (and drop) the next screencast frames while blocked.
                    cdp.next_id += 1
                    ws.send(json.dumps({
                        "id": cdp.next_id,
                        "method": "Page.screencastFrameAck",
                        "params": {"sessionId": params["sessionId"]},
                        "sessionId": session.id,
                    }))

        def wait_ready(timeout: float = 15) -> None:
            end = time.time() + timeout
            while time.time() < end:
                if session.js("document.readyState") == "complete" and session.js("document.querySelectorAll('.card').length > 0"):
                    return
                pump(0.2)
            raise RuntimeError("page did not become ready")

        pump(1.0)
        wait_ready()
        session.call("Page.startScreencast", {"format": "jpeg", "quality": quality, "maxWidth": width, "maxHeight": 800, "everyNthFrame": 2})
        pump(1.6)

        def step(name: str, expression: str, hold: float = 1.3) -> None:
            print(f"  路 {name}")
            session.js(expression)
            pump(hold)

        # 1. star a contact
        step(
            "star Hannah Brooks",
            """(() => {
                const card = [...document.querySelectorAll('.card')].find(c => c.textContent.includes('Hannah Brooks'));
                card.querySelector('[data-act="star"]').click();
            })()""",
            hold=1.4,
        )
        # 2. favourites filter
        step("open Favorites", "document.querySelector('.nav-item[data-filter=\\'favorites\\']').click()", hold=1.4)
        # 3. back + search
        step("back to All contacts", "document.querySelector('.nav-item[data-filter=\\'all\\']').click()", hold=1.0)
        step(
            "search 'chen'",
            """(() => {
                const input = document.querySelector('#search');
                input.value = 'chen';
                input.dispatchEvent(new Event('input', {bubbles: true}));
            })()""",
            hold=1.6,
        )
        step(
            "clear search",
            """(() => {
                const input = document.querySelector('#search');
                input.value = '';
                input.dispatchEvent(new Event('input', {bubbles: true}));
            })()""",
            hold=1.0,
        )
        # 4. create a contact
        step("open New contact", "document.querySelector('#btn-new').click()", hold=1.0)
        step(
            "fill the form",
            """(() => {
                const set = (sel, value) => {
                    const el = document.querySelector(sel);
                    el.value = value;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                };
                set('#f-name', 'Test Person');
                set('#f-company', 'Demo Co');
                set('#f-title', 'QA Engineer');
                const rows = document.querySelectorAll('.method-row');
                const setRow = (row, kind, label, value) => {
                    row.querySelector('.m-kind').value = kind;
                    row.querySelector('.m-label').value = label;
                    row.querySelector('.m-value').value = value;
                };
                setRow(rows[0], 'phone', 'Mobile', '+86 130 0000 4321');
                document.querySelector('[data-act="add-method"]').click();
                const rows2 = document.querySelectorAll('.method-row');
                setRow(rows2[1], 'email', 'Work', 'test.person@demo.example');
                document.querySelector('[data-act="add-method"]').click();
                const rows3 = document.querySelectorAll('.method-row');
                setRow(rows3[2], 'wechat', '', 'test_person');
                document.querySelector('#f-favorite').checked = true;
            })()""",
            hold=1.8,
        )
        step("save the contact", "document.querySelector('#contact-form button[type=submit]').click()", hold=2.0)
        # 5. edit it
        step(
            "open the new contact",
            """(() => {
                const card = [...document.querySelectorAll('.card')].find(c => c.textContent.includes('Test Person'));
                card.click();
            })()""",
            hold=1.2,
        )
        step(
            "add an address",
            """(() => {
                document.querySelector('[data-act="add-method"]').click();
                const rows = document.querySelectorAll('.method-row');
                const row = rows[rows.length - 1];
                row.querySelector('.m-kind').value = 'address';
                row.querySelector('.m-label').value = 'Campus';
                row.querySelector('.m-value').value = '2 Xueyuan Road, Fuzhou';
            })()""",
            hold=1.6,
        )
        step("save changes", "document.querySelector('#contact-form button[type=submit]').click()", hold=2.0)
        # 6. import the exported workbook (real multipart upload through app.js)
        workbook = Path("docs/address-book-export.xlsx").read_bytes()
        encoded = base64.b64encode(workbook).decode()
        step(
            "import address-book-export.xlsx",
            f"""(() => {{
                const raw = atob("{encoded}");
                const bytes = new Uint8Array(raw.length);
                for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
                const file = new File([bytes], 'address-book-export.xlsx',
                    {{type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}});
                const input = document.querySelector('#file-input');
                const data = new DataTransfer();
                data.items.add(file);
                input.files = data.files;
                input.dispatchEvent(new Event('change', {{bubbles: true}}));
            }})()""",
            hold=2.6,
        )
        step("close the import summary", "document.querySelector('.dialog-foot [data-act=\\'close\\']').click()", hold=1.2)
        # 7. delete the test contact
        step(
            "delete Test Person",
            """(() => {
                const card = [...document.querySelectorAll('.card')].find(c => c.textContent.includes('Test Person'));
                card.querySelector('[data-act="delete"]').click();
            })()""",
            hold=1.2,
        )
        step("confirm delete", "document.querySelector('.dialog-foot [data-act=\\'confirm\\']').click()", hold=1.6)
        step("open Favorites again", "document.querySelector('.nav-item[data-filter=\\'favorites\\']').click()", hold=1.8)

        session.call("Page.stopScreencast")
        ws.sock.close()
    finally:
        browser.terminate()
        try:
            browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            browser.kill()

    print(f"captured {len(frames)} frames")
    return frames


def frames_to_gif(frames: list[tuple[float, bytes]], out_path: Path, gif_width: int = 720, max_gap: float = 0.35):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    images: list[Image.Image] = []
    durations: list[int] = []
    previous_time = None
    last_image = None

    for timestamp, data in frames:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        if previous_time is None:
            duration = 0
        else:
            duration = min(max(timestamp - previous_time, 0.0), max_gap)
        previous_time = timestamp

        if last_image is not None and image.tobytes() == last_image.tobytes():
            durations[-1] += int(duration * 1000)
            continue

        ratio = gif_width / image.width
        resized = image.resize((gif_width, int(image.height * ratio)), Image.LANCZOS)
        images.append(resized)
        durations.append(max(int(duration * 1000), 60))
        last_image = image

    if not images:
        raise SystemExit("no frames captured")

    # GIF frame delays are in 1/100 s and 0 means "as fast as possible" 鈥?clamp to 2 (=50 ms).
    delays = [max(2, round(duration / 10)) for duration in durations]
    images[0].save(
        out_path,
        save_all=True,
        append_images=images[1:],
        duration=[delay * 10 for delay in delays],
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024 / 1024:.1f} MB, {len(images)} frames)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Record a demo GIF of the address book.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/")
    parser.add_argument("--out", default="docs/demo/address-book-demo.gif")
    parser.add_argument("--width", type=int, default=1000, help="capture width in pixels")
    args = parser.parse_args(argv)

    # Hard watchdog: a hung browser must not hang CI or the terminal forever.
    def _watchdog():
        print("watchdog: recording took too long, aborting", file=sys.stderr, flush=True)
        os._exit(2)

    timer = threading.Timer(1800, _watchdog)
    timer.daemon = True
    timer.start()

    frames = record(args.url, Path(args.out), width=args.width)
    timer.cancel()
    frames_to_gif(frames, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
