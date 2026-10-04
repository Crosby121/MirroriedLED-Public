"""Exercise the PHP API over HTTP, including private storage and ownership boundaries."""

from __future__ import annotations

import http.cookiejar
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
import wave


ROOT = Path(__file__).resolve().parents[1]
PHP = shutil.which("php")


def php_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 800)
    return output.getvalue()


class PortalServer:
    def __init__(self, mode="configured", auth_limit=10, max_audio=67108864, storage_limit=268435456, prefix=""):
        self.temp = tempfile.TemporaryDirectory(prefix="mirroried-portal-test-")
        self.root = Path(self.temp.name)
        self.public = self.root / "public_html"
        self.public.mkdir()
        shutil.copytree(ROOT / "customer-portal" / "backend", self.public / prefix / "customer-portal" / "backend")
        self.private = self.root / "mirroriedled-private" / "customer-portal"
        self.private.mkdir(parents=True)
        self.storage = self.private / "storage"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        self.endpoint = self.origin + ("/" + prefix if prefix else "") + "/customer-portal/backend/api.php"
        self.config = self.private / "config.php"
        storage = self.public / "unsafe-data" if mode == "unsafe-storage" else self.storage
        if mode != "unconfigured":
            self.config.write_text(
                "<?php return [\n"
                f"'storage_path'=>{php_quote(str(storage))},\n"
                f"'origin'=>{php_quote(self.origin)},\n"
                "'allow_insecure_localhost'=>true,\n"
                f"'max_audio_bytes'=>{max_audio},\n"
                "'max_video_bytes'=>134217728,\n"
                f"'plans'=>['free'=>['songs'=>3,'videos'=>1,'bytes'=>{storage_limit}]],\n"
                f"'auth_limits'=>['login_ip'=>1000,'login_email'=>{auth_limit},'signup_ip'=>1000,'window_seconds'=>900],\n"
                "];\n",
                encoding="utf-8",
            )
        if mode == "unsafe-config":
            public_config = self.public / "config.php"
            shutil.copyfile(self.config, public_config)
            self.config = public_config
        self.log = tempfile.TemporaryFile()
        env = os.environ.copy()
        env["MLED_PORTAL_CONFIG"] = str(self.config)
        self.process = subprocess.Popen(
            [PHP, "-d", "upload_max_filesize=129M", "-d", "post_max_size=130M", "-S", f"127.0.0.1:{self.port}", "-t", str(self.public)],
            env=env,
            stdout=self.log,
            stderr=self.log,
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.endpoint + "?action=session", timeout=0.5):
                    return
            except (OSError, urllib.error.URLError):
                if self.process.poll() is not None:
                    self.log.seek(0)
                    raise RuntimeError(self.log.read().decode())
                time.sleep(0.05)
        self.close()
        raise RuntimeError("PHP API did not start")

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.log.close()
        self.temp.cleanup()


class Client:
    def __init__(self, server):
        self.server = server
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = None
        self.json("session")

    def raw(self, action, body=None, headers=None, query=""):
        request = urllib.request.Request(
            self.server.endpoint + "?action=" + action + query,
            data=body,
            headers=headers or {},
        )
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers

    def json(self, action, data=None, headers=None, query=""):
        request_headers = {} if data is None else {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        if data is not None:
            data = {"csrf": self.csrf, **data}
        status, body, response_headers = self.raw(action, None if data is None else json.dumps(data).encode(), request_headers, query)
        payload = json.loads(body)
        if "csrf" in payload:
            self.csrf = payload["csrf"]
        return status, payload, response_headers

    def signup(self, plan="free"):
        self.email = f"customer-{uuid.uuid4().hex}@example.com"
        self.password = "correct horse battery stable"
        return self.json("signup", {"name": "Test Customer", "email": self.email, "password": self.password, "requestedPlan": plan})

    def upload(self, name="song.wav", contents=None, declared_mime="audio/wav"):
        boundary = "mirroried" + uuid.uuid4().hex
        content = wav_bytes() if contents is None else contents
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\n{self.csrf}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: {declared_mime}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        status, response, headers = self.raw("upload", body, {"Content-Type": "multipart/form-data; boundary=" + boundary})
        return status, json.loads(response), headers


@unittest.skipUnless(PHP, "PHP with pdo_sqlite and fileinfo is required for HTTP integration tests")
class CustomerPortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = subprocess.run([PHP, "-m"], capture_output=True, text=True, check=True).stdout
        if "pdo_sqlite" not in modules or "fileinfo" not in modules:
            raise unittest.SkipTest("PHP pdo_sqlite and fileinfo extensions are required")
        cls.server = PortalServer()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def customer(self, plan="free"):
        client = Client(self.server)
        status, result, _ = client.signup(plan)
        self.assertEqual(status, 201, result)
        return client, result

    def test_public_session_and_private_configuration_fail_closed(self):
        for mode in ("unconfigured", "unsafe-storage", "unsafe-config"):
            with self.subTest(mode=mode):
                server = PortalServer(mode)
                try:
                    client = Client(server)
                    status, result, _ = client.json("session")
                    self.assertEqual(status, 200)
                    self.assertFalse(result["configured"])
                    self.assertFalse(result["capabilities"]["signup"])
                    self.assertIsNone(result["csrf"])
                    self.assertFalse(result["capabilities"]["payments"])
                    self.assertNotIn(str(server.root), json.dumps(result))
                    status, _, _ = client.json("signup", {"name": "Test", "email": "test@example.com", "password": "long-enough-password"})
                    self.assertEqual(status, 503)
                    self.assertFalse((server.public / "unsafe-data").exists())
                finally:
                    server.close()

    def test_requested_paid_plan_still_has_free_entitlement(self):
        client, result = self.customer("premium-plus")
        self.assertEqual(result["user"]["requestedPlan"], "premium-plus")
        self.assertEqual(result["user"]["effectivePlan"], "free")
        self.assertFalse(result["capabilities"]["hardwareSync"])
        self.assertEqual(result["capabilities"]["maxFileBytes"]["audio"], 67108864)
        self.assertTrue(all(plan["price"] is None and plan["draft"] for plan in result["plans"]))
        _, library, _ = client.json("library")
        self.assertEqual(library["limits"]["songs"], 3)
        with sqlite3.connect(self.server.storage / "portal.sqlite") as database:
            row = database.execute("SELECT password_hash FROM users WHERE email=?", (client.email,)).fetchone()
        self.assertNotEqual(row[0], client.password)
        self.assertNotIn(client.password, row[0])
        verify = subprocess.run([PHP, "-r", "exit(password_verify($argv[1], $argv[2]) ? 0 : 1);", client.password, row[0]], capture_output=True)
        self.assertEqual(verify.returncode, 0)

    def test_staging_prefix_retains_authenticated_session(self):
        server = PortalServer(prefix="MLED_v5_TEST")
        try:
            client = Client(server)
            status, account, _ = client.signup()
            self.assertEqual(status, 201, account)
            status, session, _ = client.json("session")
            self.assertEqual(status, 200)
            self.assertTrue(session["authenticated"])
            cookie = next(c for c in client.cookies if c.name == "mirroried_customer")
            self.assertEqual(cookie.path, "/MLED_v5_TEST/customer-portal/")
            status, _, _ = client.upload()
            self.assertEqual(status, 201)
        finally:
            server.close()

    def test_csrf_origin_methods_and_cookie_settings(self):
        client = Client(self.server)
        _, _, headers = client.json("session")
        cookie = headers.get("Set-Cookie", "")
        # Subsequent requests may not emit a cookie, so inspect the cookie jar too.
        self.assertTrue(any(c.name == "mirroried_customer" and c.has_nonstandard_attr("HttpOnly") for c in client.cookies))
        first = urllib.request.urlopen(self.server.endpoint + "?action=session")
        self.assertIn("SameSite=Strict", first.headers.get("Set-Cookie", ""))
        first.close()
        fields = {"email": "someone@example.com", "password": "correct horse battery stable"}
        status, _, _ = client.json("login", {**fields, "csrf": "wrong"})
        self.assertEqual(status, 419)
        status, _, _ = client.json("login", fields, {"Origin": "https://attacker.example"})
        self.assertEqual(status, 403)
        status, _, _ = client.json("login")
        self.assertEqual(status, 405)
        status, _, _ = client.json("session", {})
        self.assertEqual(status, 405)

    def test_private_upload_ranges_owner_boundary_and_logout(self):
        client, result = self.customer()
        status, upload, _ = client.upload()
        self.assertEqual(status, 201, upload)
        item = upload["item"]
        self.assertEqual(item["kind"], "audio")
        self.assertEqual(item["bytes"], len(wav_bytes()))
        self.assertNotIn(str(self.server.storage), json.dumps(upload))
        self.assertEqual(list((self.server.storage / "media").glob(item["id"] + ".media"))[0].stat().st_mode & 0o777, 0o600)
        status, media, headers = client.raw("media", query="&id=" + item["id"])
        self.assertEqual(status, 200)
        self.assertEqual(media, wav_bytes())
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", headers["Cache-Control"])
        status, media, headers = client.raw("media", headers={"Range": "bytes=0-15"}, query="&id=" + item["id"])
        self.assertEqual(status, 206)
        self.assertEqual(media, wav_bytes()[:16])
        self.assertEqual(headers["Content-Range"], f"bytes 0-15/{len(wav_bytes())}")
        status, media, _ = client.raw("media", headers={"Range": "bytes=-20"}, query="&id=" + item["id"])
        self.assertEqual(status, 206)
        self.assertEqual(media, wav_bytes()[-20:])
        for range_value in ("bytes=99999-", "bytes=4-2", "bytes=0-5,10-20", "bytes=-0"):
            status, _, _ = client.raw("media", headers={"Range": range_value}, query="&id=" + item["id"])
            self.assertEqual(status, 416)
        stranger, _ = self.customer()
        status, _, _ = stranger.raw("media", query="&id=" + item["id"])
        self.assertEqual(status, 404)
        status, _, _ = stranger.json("delete", {"id": item["id"]})
        self.assertEqual(status, 404)
        _, library, _ = stranger.json("library")
        self.assertEqual(library["items"], [])
        old_csrf = client.csrf
        old_session = next(c.value for c in client.cookies if c.name == "mirroried_customer")
        status, logged_out, _ = client.json("logout", {})
        self.assertEqual(status, 200)
        self.assertFalse(logged_out["authenticated"])
        self.assertNotEqual(client.csrf, old_csrf)
        self.assertNotEqual(next(c.value for c in client.cookies if c.name == "mirroried_customer"), old_session)
        status, _, _ = client.raw("media", query="&id=" + item["id"])
        self.assertEqual(status, 401)
        status, logged_in, _ = client.json("login", {"email": client.email, "password": client.password})
        self.assertEqual(status, 200)
        self.assertEqual(logged_in["user"]["id"], result["user"]["id"])
        status, _, _ = client.json("delete", {"id": item["id"]})
        self.assertEqual(status, 200)
        self.assertFalse((self.server.storage / "media" / (item["id"] + ".media")).exists())
        status, _, _ = client.raw("media", query="&id=" + item["id"])
        self.assertEqual(status, 404)

    def test_media_validation_does_not_trust_name_or_client_mime(self):
        client, _ = self.customer()
        samples = [
            ("bad.mp3", b"<?php echo 'bad'; ?>", "audio/mpeg"),
            ("bad.mp3", wav_bytes(), "audio/mpeg"),
            ("bad.wav", b"<html>fake media</html>", "audio/wav"),
            ("bad.php.wav", wav_bytes(), "audio/wav"),
            ("bad.svg", b"<svg></svg>", "video/mp4"),
            ("empty.wav", b"", "audio/wav"),
        ]
        for name, contents, mime in samples:
            with self.subTest(name=name):
                status, _, _ = client.upload(name, contents, mime)
                self.assertEqual(status, 422)
        _, library, _ = client.json("library")
        self.assertEqual(library["usage"], {"songs": 0, "videos": 0, "bytes": 0})

    def test_quotas_are_enforced_and_delete_restores_capacity(self):
        client, _ = self.customer("premium")
        ids = []
        for index in range(3):
            status, result, _ = client.upload(f"song-{index}.wav")
            self.assertEqual(status, 201)
            ids.append(result["item"]["id"])
        status, result, _ = client.upload("over-limit.wav")
        self.assertEqual(status, 409)
        self.assertIn("song limit", result["error"])
        _, library, _ = client.json("library")
        self.assertEqual(library["usage"]["songs"], 3)
        self.assertEqual(library["usage"]["bytes"], 3 * len(wav_bytes()))
        client.json("delete", {"id": ids[0]})
        status, _, _ = client.upload("replacement.wav")
        self.assertEqual(status, 201)

    def test_file_and_account_storage_size_limits(self):
        for max_audio, storage_limit in ((1000, 268435456), (67108864, 1000)):
            server = PortalServer(max_audio=max_audio, storage_limit=storage_limit)
            try:
                client = Client(server)
                client.signup()
                status, _, _ = client.upload()
                self.assertEqual(status, 413 if max_audio == 1000 else 409)
                _, library, _ = client.json("library")
                self.assertEqual(library["usage"]["bytes"], 0)
            finally:
                server.close()

    def test_login_throttles_repeated_wrong_passwords(self):
        server = PortalServer(auth_limit=3)
        try:
            client = Client(server)
            client.signup()
            client.json("logout", {})
            for _ in range(3):
                status, _, _ = client.json("login", {"email": client.email, "password": "wrong-password"})
                self.assertEqual(status, 401)
            status, result, headers = client.json("login", {"email": client.email, "password": client.password})
            self.assertEqual(status, 429)
            self.assertIn("Retry-After", headers)
            self.assertFalse(Client(server).json("session")[1]["authenticated"])
        finally:
            server.close()

    def test_account_input_validation_and_duplicate_email(self):
        client, _ = self.customer()
        status, _, _ = client.json("signup", {"name": "Other", "email": client.email, "password": client.password})
        self.assertEqual(status, 409)
        fields = {"name": "New Customer", "email": "new@example.com", "password": "long-enough-password", "requestedPlan": "free"}
        for change in ({"email": "invalid"}, {"name": ""}, {"password": "short"}, {"password": "a" * 73}, {"requestedPlan": "admin"}):
            status, _, _ = client.json("signup", {**fields, **change})
            self.assertEqual(status, 422)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required to generate a real MP4 test fixture")
    def test_video_upload_count_limit_and_container_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="mirroried-video-test-") as temp:
            video = Path(temp) / "clip.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=32x32:d=0.2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
            client, _ = self.customer()
            status, result, _ = client.upload("clip.mp4", video.read_bytes(), "video/mp4")
            self.assertEqual(status, 201, result)
            self.assertEqual(result["item"]["kind"], "video")
            self.assertEqual(result["usage"]["videos"], 1)
            status, _, _ = client.upload("another.mp4", video.read_bytes(), "video/mp4")
            self.assertEqual(status, 409)
            status, _, _ = client.upload("fake.webm", video.read_bytes(), "video/webm")
            self.assertEqual(status, 422)


if __name__ == "__main__":
    unittest.main()
