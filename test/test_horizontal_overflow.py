# -*- coding: utf-8 -*-

"""Fail if a library page can scroll sideways, and if the home rows cannot."""

import base64
import json
import os
import socket
import struct
import subprocess
import time
import unittest
import urllib.request
from hashlib import sha512

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE = os.environ.get("CW_BASE_URL", "http://127.0.0.1:8084")
UA = "CWOverflow/1.0"
WIDTHS = (360, 768, 1280, 1920)
PATHS = (
    "/",
    "/genres",
    "/genres/Fantasy",
    "/series",
    "/series/1",
    "/discover/stored",
    "/book/36",
    "/admin/view",
    "/admin/config",
    "/admin/viewconfig",
)

MEASURE = """
(() => {
  const doc = document.documentElement;
  const rows = Array.from(document.querySelectorAll(".library-row-scroller"));
  const nav = document.querySelector(".library-topnav");
  window.scrollTo(0, 500);
  const navTop = nav ? nav.getBoundingClientRect().top : 0;
  window.scrollTo(0, 0);
  return {
    path: location.pathname,
    scrollWidth: doc.scrollWidth,
    clientWidth: doc.clientWidth,
    rowScrolls: rows.some((row) => row.scrollWidth > row.clientWidth + 1),
    navTop: navTop
  };
})()
"""


class Cdp:
    def __init__(self, url):
        rest = url.split("://", 1)[1]
        hostport, path = rest.split("/", 1)
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
            % (path, hostport, key)
        )
        self.sock.sendall(request.encode())
        data = b""
        while b"\r\n\r\n" not in data:
            data += self.sock.recv(4096)
        self.next_id = 0

    def call(self, method, params=None, expect=None):
        self.next_id += 1
        message_id = self.next_id
        payload = json.dumps({"id": message_id, "method": method, "params": params or {}}).encode()
        self._send(payload)
        while True:
            message = json.loads(self._recv())
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise RuntimeError(message["error"])
            return message.get("result", {})

    def _send(self, payload):
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0xFE)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0xFF)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv(self):
        def exact(count):
            buf = b""
            while len(buf) < count:
                chunk = self.sock.recv(count - len(buf))
                if not chunk:
                    raise RuntimeError("devtools socket closed")
                buf += chunk
            return buf

        while True:
            first, second = exact(2)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", exact(8))[0]
            payload = exact(length)
            if opcode == 1:
                return payload.decode()


def _server_up():
    try:
        urllib.request.urlopen(BASE + "/login", timeout=3).read(32)
        return True
    except Exception:
        return False


def _session_cookie():
    import sqlite3
    from flask import Flask, session

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(root, "app.db")
    base = "%s|%s" % (b"::ffff:127.0.0.1", UA.encode())
    ident = sha512(base.encode("utf8")).hexdigest()
    token = "overflow-token"
    con = sqlite3.connect(db_path, timeout=5)
    key = con.execute("select flask_session_key from flask_settings").fetchone()[0]
    expiry = int(time.time()) + 900
    con.execute("delete from user_session where random = ?", (token,))
    con.execute(
        "insert into user_session (user_id, session_key, random, expiry) values (?,?,?,?)",
        (1, ident, token, expiry),
    )
    con.commit()
    con.close()
    app = Flask("overflow-check")
    app.secret_key = key
    with app.test_request_context("/"):
        session["_user_id"] = "1"
        session["_fresh"] = True
        session["_id"] = ident
        session["_random"] = token
        response = app.response_class()
        app.session_interface.save_session(app, session, response)
        cookie = response.headers.get("Set-Cookie").split(";", 1)[0].split("=", 1)[1]
    return cookie


def _drop_session():
    import sqlite3

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    con = sqlite3.connect(os.path.join(root, "app.db"), timeout=5)
    con.execute("delete from user_session where random = ?", ("overflow-token",))
    con.commit()
    con.close()


class HorizontalOverflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(CHROME) or not _server_up():
            raise unittest.SkipTest("Chrome or the library server is not available")
        cls.cookie = _session_cookie()
        cls.profile = "/tmp/cw-overflow-profile"
        cls.port = 9333
        cls.proc = subprocess.Popen(
            [
                CHROME,
                "--headless=new",
                "--remote-debugging-port=%s" % cls.port,
                "--user-data-dir=%s" % cls.profile,
                "--no-first-run",
                "--disable-gpu",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 8
        version = None
        while time.time() < deadline:
            try:
                version = json.load(urllib.request.urlopen("http://127.0.0.1:%s/json/version" % cls.port))
                break
            except Exception:
                time.sleep(0.2)
        if not version:
            raise unittest.SkipTest("Chrome devtools did not start")
        targets = json.load(urllib.request.urlopen("http://127.0.0.1:%s/json" % cls.port))
        pages = [item for item in targets if item.get("type") == "page"]
        if not pages:
            browser = Cdp(version["webSocketDebuggerUrl"])
            created = browser.call("Target.createTarget", {"url": "about:blank"})
            time.sleep(0.3)
            targets = json.load(urllib.request.urlopen("http://127.0.0.1:%s/json" % cls.port))
            pages = [item for item in targets if item.get("id") == created.get("targetId")]
        cls.cdp = Cdp(pages[0]["webSocketDebuggerUrl"])
        cls.cdp.call("Network.enable")
        cls.cdp.call("Page.enable")
        cls.cdp.call("Emulation.setUserAgentOverride", {"userAgent": UA})
        cls.cdp.call("Network.setCookie", {
            "name": "session",
            "value": cls.cookie,
            "url": BASE,
        })

    @classmethod
    def tearDownClass(cls):
        proc = getattr(cls, "proc", None)
        if proc is not None:
            proc.terminate()
        try:
            _drop_session()
        except Exception:
            return

    def test_pages_do_not_scroll_sideways(self):
        home_rows = False
        for width in WIDTHS:
            self.cdp.call("Emulation.setDeviceMetricsOverride", {
                "width": width,
                "height": 900,
                "deviceScaleFactor": 1,
                "mobile": False,
            })
            for path in PATHS:
                metrics = self._open(BASE + path)
                self.assertLessEqual(
                    metrics["scrollWidth"],
                    metrics["clientWidth"] + 1,
                    "%s at %s is %s wide inside %s" % (
                        path, width, metrics["scrollWidth"], metrics["clientWidth"]
                    ),
                )
                if path == "/" and metrics["rowScrolls"]:
                    home_rows = True
                if path == "/" and width == 1280:
                    self.assertLessEqual(metrics["navTop"], 2, "navbar did not stay pinned")
            self.cdp.call("Network.deleteCookies", {"name": "session", "url": BASE})
            login = self._open(BASE + "/login")
            self.cdp.call("Network.setCookie", {"name": "session", "value": self.cookie, "url": BASE})
            self.assertLessEqual(login["scrollWidth"], login["clientWidth"] + 1, "login at %s" % width)
        self.assertTrue(home_rows, "home carousels should scroll inside the row")

    def _open(self, url):
        self.cdp.call("Page.navigate", {"url": url})
        deadline = time.time() + 12
        while time.time() < deadline:
            result = self.cdp.call("Runtime.evaluate", {
                "expression": "document.readyState",
                "returnByValue": True,
            })
            if result.get("result", {}).get("value") == "complete":
                break
            time.sleep(0.15)
        time.sleep(0.8)
        result = self.cdp.call("Runtime.evaluate", {
            "expression": MEASURE,
            "returnByValue": True,
        })
        return result["result"]["value"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
