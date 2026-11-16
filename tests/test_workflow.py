import os
import re
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from pathlib import Path
from threading import Barrier
from time import time
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from cssd import create_app, db


class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        source = Path(cls.temp.name) / "seed.db"
        with db.connect(source) as conn:
            db.migrate(conn, "up")
            db.seed(conn, {username: "synthetic-test-password" for username in db.DEMO_ROLES})
        conn.close()
        cls.seed_db = source.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "test.db"
        self.path.write_bytes(self.seed_db)
        self.app = create_app({"TESTING": True, "DATABASE": str(self.path), "DATABASE_URL": None, "SECRET_KEY": "test-only"})
        self.conn = db.connect(self.path)
        self.addCleanup(self.conn.close)
        self.codes = {row["label"]: row["qr"] for row in self.conn.execute("SELECT label,qr FROM containers")}
        self.clients = {}

    def client(self, user):
        if user not in self.clients:
            c = self.app.test_client()
            self.login(c, user)
            self.clients[user] = c
        return self.clients[user]

    def login(self, client, user, next_path=""):
        page = client.get("/login")
        csrf = re.search(rb'name="csrf" value="([^"]+)"', page.data)[1].decode()
        result = client.post("/login", data=dict(
            csrf=csrf, username=user, password="synthetic-test-password", next=next_path,
        ))
        self.assertEqual(result.status_code, 303)
        return result

    def post(self, user, path, status=303, key=None, client=None, **fields):
        c = client or self.client(user)
        with c.session_transaction() as s:
            csrf = s.setdefault("csrf", "synthetic-test-csrf")
        data = dict(fields, csrf=csrf)
        if key:
            data["key"] = key
        else:
            import secrets
            data["key"] = secrets.token_hex(16)
        result = c.post(path, data=data)
        self.assertEqual(result.status_code, status, result.data[:3000].decode())
        return result

    def cycle(self, code="C-001", first=2):
        qr = self.codes[code]
        self.post("setting", f"/c/{qr}/start")
        cycle_id = self.conn.execute("""
            SELECT cy.id FROM cycles cy JOIN containers c ON c.id=cy.container_id
            WHERE c.qr=? AND cy.closed_at IS NULL
        """, (qr,)).fetchone()["id"]
        self.assertEqual(self.client("setting").get(f"/c/{qr}").status_code, 200)
        self.post("setting", f"/cycles/{cycle_id}/verify",
                  physical_check="yes", qty_1=first, qty_2=1, qty_3=1)
        return cycle_id

    def processed(self, code="C-001"):
        cycle_id = self.cycle(code)
        self.post("setting", f"/cycles/{cycle_id}/pack")
        self.post("steril", f"/cycles/{cycle_id}/batch-start", reference=f"SIM-{cycle_id}")
        self.post("steril", f"/cycles/{cycle_id}/batch-complete")
        return cycle_id

    def available(self, code="C-001"):
        cycle_id = self.processed(code)
        self.post("qc", f"/cycles/{cycle_id}/qc", outcome="RELEASE", evidence="EVIDENCE-SYNTHETIC")
        return cycle_id

    def requested(self, *codes, user="ok"):
        response = self.post(user, "/loans/new", containers=list(codes))
        loan_id = int(response.location.split("/")[-1])
        self.assertEqual(self.client("gudang").get(f"/loans/{loan_id}").status_code, 200)
        self.post("gudang", f"/loans/{loan_id}/pick")
        return loan_id

    def recipient(self, user="ok"):
        return self.conn.execute("SELECT id FROM users WHERE username=?", (user,)).fetchone()["id"]

    def return_one(self, loan, label, first, status=303, key=None):
        item = self.conn.execute("""
            SELECT li.id FROM loan_items li JOIN containers c ON c.id=li.container_id
            WHERE loan_id=? AND c.label=?
        """, (loan, label)).fetchone()["id"]
        path = f"/c/{self.codes[label]}/return/{item}"
        return self.post("dekon", path, status, key=key, physical_check="yes",
                         qty_1=first, qty_2=1, qty_3=1, note_1="Catatan kondisi demo")

    def state(self, table, identifier):
        self.assertIn(table, ("loans", "cycles"))
        return self.conn.execute(f"SELECT state FROM {table} WHERE id=?", (identifier,)).fetchone()["state"]

    def test_bulk_end_to_end(self):
        first = self.available()
        second = self.available("C-002")
        self.assertEqual(self.client("ok").get("/loans/new").status_code, 200)
        loan = self.requested("C-001", self.codes["C-002"])
        self.assertEqual(self.client("ok2").get(f"/loans/{loan}").status_code, 404)
        self.post("gudang", f"/loans/{loan}/handover", physical_check="yes", recipient=self.recipient(), key="handover")
        self.post("gudang", f"/loans/{loan}/handover", physical_check="yes", recipient=self.recipient(), key="handover")
        self.assertEqual(self.conn.execute("SELECT count(*) AS total FROM audit_events WHERE action='HANDOVER'").fetchone()["total"], 1)
        self.post("gudang", f"/loans/{loan}/handover", 409, physical_check="no", recipient=self.recipient(), key="handover")
        self.return_one(loan, "C-001", 1, status=409)
        self.assertEqual(self.client("ok2").get("/lookup?code=C-001").status_code, 404)
        self.assertEqual(self.client("ok").get("/lookup?code=C-001").status_code, 302)
        self.post("ok", f"/loans/{loan}/receive", physical_check="yes")
        dekon = self.client("dekon")
        self.assertIn(b"Periksa pengembalian", dekon.get(f"/loans/{loan}").data)
        receipt = self.return_one(loan, "C-001", 1, key="return").location
        self.assertTrue(receipt.startswith("/returns/"))
        self.assertEqual(self.return_one(loan, "C-001", 1, key="return").location, receipt)
        self.assertIn(receipt.encode(), dekon.get(f"/loans/{loan}").data)
        self.assertIn(b"Catatan kondisi demo", dekon.get(receipt).data)
        self.assertEqual(self.client("ok").get(receipt).status_code, 403)
        self.assertEqual(self.client("ok2").get(receipt).status_code, 403)
        self.return_one(loan, "C-001", 1, status=409)
        self.assertEqual(self.state("loans", loan), "PARTIALLY_RETURNED")
        self.assertEqual(self.state("cycles", first), "DISCREPANCY")
        self.assertEqual(self.state("cycles", second), "BORROWED")
        self.return_one(loan, "C-002", 2)
        self.assertEqual(self.state("loans", loan), "RETURNED")
        self.assertEqual(self.state("cycles", second), "DIRTY_RECEIVED")
        self.assertEqual(self.conn.execute("SELECT count(*) AS total FROM notifications").fetchone()["total"], 1)
        case = self.conn.execute("SELECT id FROM discrepancy_cases").fetchone()["id"]
        page = self.client("supervisor").get(f"/cases/{case}")
        self.assertIn(b"OK Demo A", page.data)
        self.assertIn(b"Klem Hemostat Mosquito Lurus", page.data)
        self.assertIn(b"Petugas Demo gudang", page.data)
        self.assertIn(b"Petugas Demo ok", page.data)
        self.assertIn(b"Petugas Demo dekon", page.data)
        self.assertIn(receipt.encode(), page.data)
        self.post("supervisor", f"/cases/{case}/investigate", reason="Rekonsiliasi simulasi")
        self.post("supervisor", f"/cases/{case}/resolve", reason="Temuan latihan didokumentasikan")
        self.post("dekon", f"/cycles/{first}/decontaminate", reason="SIM-DEKON-1")
        new = self.cycle(first=1)
        self.assertNotEqual(first, new)
        self.assertIn(b"Siklus 1", dekon.get(receipt).data)
        history = self.client("supervisor").get(f"/cases/{case}").data
        self.assertIn(b"Rekonsiliasi simulasi", history)
        self.assertIn(b"Temuan latihan didokumentasikan", history)
        self.assertEqual(self.conn.execute("SELECT verified FROM cycle_items WHERE cycle_id=? AND instrument_id=1", (first,)).fetchone()["verified"], 2)
        page = self.client("setting").get(f"/c/{self.codes['C-001']}")
        self.assertIn(b"Histori siklus", page.data)
        self.assertIn(b"Selisih terhadap template", page.data)
        self.assertIn(b"VERIFY_RETURN", self.client("supervisor").get("/audit").data)

    def test_setting_queue_and_custom_cycle_after_return(self):
        qr = self.codes["C-001"]
        path = f"/c/{qr}"
        previous = self.available()
        loan = self.requested("C-001")
        self.post("gudang", f"/loans/{loan}/handover", physical_check="yes", recipient=self.recipient())
        self.post("ok", f"/loans/{loan}/receive", physical_check="yes")
        setting = self.client("setting")
        queue = "/?modul=setting"
        self.assertNotIn(path.encode(), setting.get(queue).data)
        self.return_one(loan, "C-001", 2)
        waiting = setting.get(queue + "&status=DIRTY_RECEIVED").data
        self.assertIn(path.encode(), waiting)
        self.assertIn(b"Menunggu dekontaminasi", waiting)
        self.post("setting", f"{path}/start", 409)
        self.post("dekon", f"/cycles/{previous}/decontaminate", reason="SIM-DEKON-KHUSUS")
        self.assertIn(path.encode(), setting.get(queue + "&status=DECONTAMINATED").data)
        self.post("setting", f"{path}/start")
        cycle = self.conn.execute("SELECT id,template_id FROM cycles WHERE sequence=2").fetchone()
        base = f"/cycles/{cycle['id']}"
        self.assertIn(b"Susun komposisi khusus", setting.get(path).data)
        self.post("ok", base + "/composition", 403, mode="custom", template_id=cycle["template_id"], qty_2=3)
        self.post("setting", base + "/composition", 400, mode="custom", template_id=cycle["template_id"])
        self.post("setting", base + "/composition", mode="custom", template_id=cycle["template_id"], qty_2=3, qty_3=2)
        self.post("setting", base + "/verify", 409, template_id=cycle["template_id"], physical_check="yes", qty_2=3, qty_3=2)
        template = self.conn.execute("SELECT template_id FROM cycles WHERE id=?", (cycle["id"],)).fetchone()[0]
        self.post("setting", base + "/verify", template_id=template, physical_check="yes", qty_2=3, qty_3=2)
        self.post("setting", base + "/composition", 409, mode="standard", template_id=template)
        self.assertEqual([tuple(item) for item in self.conn.execute(
            "SELECT instrument_id,verified FROM cycle_items WHERE cycle_id=? ORDER BY instrument_id", (cycle["id"],)
        )], [(2, 3), (3, 2)])
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM cycle_items WHERE cycle_id=?", (previous,)
        ).fetchone()[0], 3)
        self.assertEqual(self.conn.execute("SELECT template_id FROM containers WHERE qr=?", (qr,)).fetchone()[0], cycle["template_id"])
        self.assertEqual(setting.get("/api/container-preview?code=C-001").status_code, 403)
        self.assertEqual(self.client("ok").get("/api/container-preview?code=C-001").status_code, 409)
        self.post("setting", base + "/pack")
        self.post("steril", base + "/batch-start", reference="SIM-BATCH-KHUSUS")
        self.post("steril", base + "/batch-complete")
        self.post("qc", base + "/qc", outcome="RELEASE", evidence="SIM-QC-KHUSUS")
        self.assertEqual(self.client("ok").get("/api/container-preview?code=C-001").json["set"], "Set khusus C-001")

    def test_shared_batch_is_atomic_and_preserves_individual_qc(self):
        first = self.cycle()
        second = self.cycle("C-002")
        self.post("setting", f"/cycles/{first}/pack")
        self.post("steril", "/batches", 409, cycles=[first, second], reference="SIM-BERSAMA")
        self.assertEqual(self.state("cycles", first), "PACKAGED")
        self.post("setting", f"/cycles/{second}/pack")
        self.assertIn(b"Mulai batch terpilih", self.client("steril").get("/?modul=sterilisasi").data)
        self.post("ok", "/batches", 403, cycles=[first, second], reference="SIM-BERSAMA")
        self.post("steril", "/batches", 400, cycles=[first, first], reference="SIM-BERSAMA")
        self.post("steril", "/batches", cycles=[first, second], reference="SIM-BERSAMA", key="batch-start")
        self.post("steril", "/batches", cycles=[first, second], reference="SIM-BERSAMA", key="batch-start")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 1)
        self.assertEqual(self.state("cycles", second), "PROCESSING")
        self.post("steril", f"/cycles/{second}/batch-complete", process_evidence="SIM-BUKTI-BATCH")
        self.assertEqual(self.state("cycles", first), "QC_PENDING")
        self.assertEqual(self.state("cycles", second), "QC_PENDING")
        self.post("qc", f"/cycles/{first}/qc", outcome="RELEASE", evidence="SIM-KONTROL-1")
        self.assertEqual(self.state("cycles", second), "QC_PENDING")
        page = self.client("steril").get(f"/c/{self.codes['C-001']}").data
        self.assertIn(b"SIM-BUKTI-BATCH", page)
        self.assertIn(b"C-002", page)
        audit = self.client("supervisor").get("/audit?modul=sterilisasi&container=C-002").data
        self.assertIn(b"BATCH_START", audit)
        self.assertIn(b"BATCH_COMPLETE", audit)
        with self.assertRaises(sqlite3.IntegrityError):
            db.migrate(self.conn, "down")
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 4)

    def test_physical_validation_and_qc_permission(self):
        qr = self.codes["C-001"]
        self.post("setting", f"/c/{qr}/start")
        self.post("setting", f"/c/{qr}/start", 409)
        self.post("setting", "/cycles/1/verify", 400, physical_check="yes", qty_1=-1, qty_2=1, qty_3=1)
        self.post("setting", "/cycles/1/verify", 400, qty_1=2, qty_2=1, qty_3=1)
        self.post("setting", "/cycles/1/verify", physical_check="yes", qty_1=1, qty_2=1, qty_3=1)
        self.post("setting", "/cycles/1/pack", 409)
        cycle = self.processed("C-002")
        self.post("ok", f"/cycles/{cycle}/qc", 403, outcome="RELEASE", evidence="demo")
        self.post("ok", "/loans/new", 409, containers=["C-002"])
        self.post("qc", f"/cycles/{cycle}/qc", outcome="REJECT", evidence="demo")
        self.post("ok", "/loans/new", 409, containers=["C-002"])
        self.assertEqual(self.state("cycles", cycle), "REJECTED")

    def test_login_guide_and_switching_actors(self):
        browser = self.app.test_client()
        self.assertEqual(browser.get("/master").status_code, 302)
        self.assertNotIn(b"Coba sebagai aktor demo", browser.get("/login").data)
        self.app.config["DEMO_GUIDE"] = True
        page = browser.get("/login?akun=ok")
        self.assertIn(b'value="ok"', page.data)
        self.assertIn(b"Coba sebagai aktor demo", page.data)
        csrf = re.search(rb'name="csrf" value="([^"]+)"', page.data)[1].decode()
        wrong = browser.post("/login", data={"csrf": csrf, "username": "ok", "password": "wrong"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(browser.get("/loans/new").status_code, 302)

        for username, visible, restricted in (
            ("admin", "/master", "/loans/new"),
            ("setting", "/?modul=setting", "/accounts"),
            ("ok", "/loans/needs", "/audit"),
            ("supervisor", "/reports", "/accounts"),
        ):
            self.login(browser, username)
            self.assertEqual(browser.get("/login").status_code, 302)
            dashboard = browser.get("/")
            self.assertIn(f'href="{visible}"'.encode(), dashboard.data)
            self.assertTrue(dashboard.cache_control.no_store)
            self.assertEqual(browser.get(visible).status_code, 200)
            self.assertEqual(browser.get(restricted).status_code, 403)
            self.assertEqual(browser.post("/logout").status_code, 400)
            self.post(username, "/logout", client=browser)
            self.assertEqual(browser.get(visible).status_code, 302)

    def test_supabase_email_login_requires_linked_identity(self):
        auth_id = "a01b02c3-0102-4000-8000-000000000001"
        # Exercise request/session behavior with SQLite; PostgreSQL stores the column as UUID.
        self.conn.execute("ALTER TABLE users ADD COLUMN auth_user_id TEXT")
        self.conn.execute("UPDATE users SET auth_user_id=? WHERE username='ok'", (auth_id,))
        self.app.config.update(
            SUPABASE_URL="https://steritrack.example.com", SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
            DEMO_GUIDE=True,
        )
        browser = self.app.test_client()
        with browser.session_transaction() as session:
            session["actor"] = self.recipient("admin")
        self.assertEqual(browser.get("/").status_code, 302)
        page = browser.get("/login?akun=ok%40steritrack.example.com")
        self.assertIn(b'type="email"', page.data)
        self.assertIn(b'value="ok@steritrack.example.com"', page.data)
        csrf = re.search(rb'name="csrf" value="([^"]+)"', page.data)[1].decode()
        body = {"csrf": csrf, "username": "ok@steritrack.example.com", "password": "supabase-test"}
        with patch("cssd.web.supabase_auth.sign_in") as sign_in:
            sign_in.return_value = ("a01b02c3-0102-4000-8000-000000000002", int(time()) + 60)
            self.assertEqual(browser.post("/login", data=body).status_code, 401)
            sign_in.return_value = (auth_id, int(time()) + 60)
            result = browser.post("/login", data={**body, "role": "admin"})
            self.assertEqual(result.status_code, 303)
            self.assertEqual(browser.get("/loans/new").status_code, 200)
            self.assertEqual(browser.get("/master").status_code, 403)
            with browser.session_transaction() as session:
                session["supabase_expires_at"] = int(time()) - 1
            self.assertEqual(browser.get("/").status_code, 302)

    def test_init_demo_issues_separate_credentials(self):
        self.app.config["DATABASE"] = str(Path(self.directory.name) / "new-demo.db")
        result = self.app.test_cli_runner().invoke(args=["init-demo"])
        self.assertEqual(result.exit_code, 0, result.output)
        credentials = dict(re.findall(r"^([a-z0-9]+) +[^/]+ / ([^\s]+)$", result.output, re.MULTILINE))
        self.assertEqual(set(credentials), set(db.DEMO_ROLES))
        self.assertEqual(len(set(credentials.values())), len(credentials))
        browser = self.app.test_client()
        page = browser.get("/login")
        csrf = re.search(rb'name="csrf" value="([^"]+)"', page.data)[1].decode()
        self.assertEqual(browser.post("/login", data={
            "csrf": csrf, "username": "ok", "password": credentials["setting"],
        }).status_code, 401)
        self.assertEqual(browser.post("/login", data={
            "csrf": csrf, "username": "ok", "password": credentials["ok"],
        }).status_code, 303)

    def test_four_roles_shared_dashboard_and_qc_permissions(self):
        self.assertEqual(
            {r["role"] for r in self.conn.execute("SELECT DISTINCT role FROM users")},
            {"admin", "petugas_cssd", "petugas_unit", "supervisor"},
        )
        admin = self.client("admin")
        cssd = self.client("setting")
        self.assertIn(b'href="/accounts"', admin.get("/").data)
        self.assertEqual(admin.get("/accounts").status_code, 200)
        self.assertEqual(cssd.get("/accounts").status_code, 403)
        self.assertEqual(cssd.get("/audit").status_code, 403)
        for module in ("setting", "sterilisasi", "qc", "gudang", "dekontaminasi", "riwayat"):
            self.assertIn(f'href="/?modul={module}"'.encode(), cssd.get("/").data)
            self.assertEqual(cssd.get(f"/?modul={module}").status_code, 200)
        self.post("admin", "/accounts", username="ahmad.cssd", name="Ahmad Demo",
                  role="petugas_cssd", unit=1, password="synthetic-test-password")
        self.post("setting", "/accounts", 403, username="blocked")
        user_id = self.recipient("ahmad.cssd")
        qr = self.codes["C-001"]
        cycle_id = self.cycle()
        self.post("setting", f"/cycles/{cycle_id}/pack")
        self.post("setting", f"/cycles/{cycle_id}/batch-start", reference="SHARED-ROLE-DEMO")
        self.post("setting", f"/cycles/{cycle_id}/batch-complete")
        self.assertIn(b"C-001", cssd.get("/?modul=qc").data)
        detail = cssd.get(f"/c/{qr}").data
        self.assertIn(b"SHARED-ROLE-DEMO", detail)
        qc_path = f"/cycles/{cycle_id}/qc"
        self.assertNotIn(qc_path.encode(), detail)
        for outcome in ("RELEASE", "REJECT", "QUARANTINE"):
            self.post("setting", qc_path, 403, outcome=outcome, evidence="demo")
        self.post("admin", qc_path, 403, outcome="RELEASE", evidence="demo")
        permission_path = f"/accounts/{user_id}/qc"
        self.post("setting", permission_path, 403, can_release_qc=1, reason="Unauthorized")
        self.post("admin", permission_path, can_release_qc=1, reason="Synthetic assignment")
        worker = self.client("ahmad.cssd")
        self.assertIn(qc_path.encode(), worker.get(f"/c/{qr}").data)
        self.post("admin", permission_path, can_release_qc=0, reason="Synthetic revocation")
        self.post("ahmad.cssd", qc_path, 403, outcome="RELEASE", evidence="demo")
        self.post("admin", permission_path, can_release_qc=1, reason="Synthetic reassignment")
        self.post("ahmad.cssd", qc_path, outcome="RELEASE", evidence="demo")
        self.assertEqual(self.state("cycles", cycle_id), "AVAILABLE")
        day = datetime.now(ZoneInfo("Asia/Jakarta")).date().isoformat()
        audit = admin.get(f"/audit?actor={user_id}&modul=qc&container=C-001&day={day}")
        self.assertIn(b"ahmad.cssd", audit.data)
        self.assertIn(b"C-001", audit.data)
        self.assertIn(b"RELEASE", audit.data)
        self.assertNotIn(b"SHARED-ROLE-DEMO", audit.data)
        self.assertNotIn(b"synthetic-test-password", admin.get("/audit").data)

    def test_sqlite_role_upgrade_preserves_accounts_and_audit(self):
        legacy = Path(self.directory.name) / "legacy.db"
        conn = db.connect(legacy)
        self.addCleanup(conn.close)
        conn.executescript((db.MIGRATIONS / "001_up.sql").read_text(encoding="utf-8"))
        conn.executescript("""
            PRAGMA user_version=1;
            INSERT INTO units VALUES(1,'CSSD');
            INSERT INTO users VALUES(17,'existing.qc','QC staff','preserved',1,'QC');
            INSERT INTO users VALUES(31,'existing.setting','Setting staff','preserved',1,'SETTING');
            INSERT INTO audit_events(actor_id,action,entity,entity_id,reason,details)
                VALUES(17,'QC','cycle',11,'prior event','{}');
        """)
        db.apply_schema(conn)
        db.apply_schema(conn)
        users = [tuple(r) for r in conn.execute(
            "SELECT id,password_hash,role,can_release_qc FROM users ORDER BY id"
        )]
        self.assertEqual(users, [(17, "preserved", "petugas_cssd", 1), (31, "preserved", "petugas_cssd", 0)])
        self.assertEqual(conn.execute("SELECT actor_id FROM audit_events").fetchone()[0], 17)
        self.assertFalse(conn.execute("PRAGMA foreign_key_check").fetchall())
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE users SET role='QC' WHERE id=17")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE users SET role='admin',can_release_qc=1 WHERE id=31")

    def test_excel_report_filters_by_event_date_and_unit(self):
        self.available()
        loan = self.requested("C-001")
        self.post("gudang", f"/loans/{loan}/handover", physical_check="yes", recipient=self.recipient())
        self.post("ok", f"/loans/{loan}/receive", physical_check="yes")
        self.return_one(loan, "C-001", 1)
        # Both dates are 00:05 WIB on the following calendar day.
        self.conn.execute("UPDATE loans SET handed_over_at=? WHERE id=?", ("2026-11-13 17:05:00", loan))
        self.conn.execute("UPDATE returns SET received_at=? WHERE loan_id=?", ("2026-11-14 17:05:00", loan))
        self.conn.execute("UPDATE units SET name=? WHERE id=2", ("=1+1",))

        supervisor = self.client("supervisor")
        self.assertIn(b'formaction="/reports.xlsx"', supervisor.get("/reports").data)
        self.assertEqual(self.app.test_client().get("/reports.xlsx").status_code, 302)
        self.assertEqual(self.client("ok").get("/reports.xlsx").status_code, 403)
        self.assertEqual(supervisor.get("/reports.xlsx?day=invalid").status_code, 400)

        def workbook(day, unit):
            response = supervisor.get(f"/reports.xlsx?day={day}&unit={unit}")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.cache_control.no_store)
            self.assertIn(f"laporan-steritrack-{day}.xlsx", response.headers["Content-Disposition"])
            return ZipFile(BytesIO(response.data))

        def rows(archive, sheet):
            xml = ElementTree.fromstring(archive.read(f"xl/worksheets/sheet{sheet}.xml"))
            self.assertIsNone(xml.find(".//{*}f"))
            return xml.findall(".//{*}sheetData/{*}row")

        with workbook("2026-11-14", 2) as archive:
            self.assertEqual(len(rows(archive, 2)), 2)
            self.assertEqual(len(rows(archive, 3)), 1)
        with workbook("2026-11-15", 2) as archive:
            self.assertEqual(len(rows(archive, 2)), 1)
            self.assertEqual(len(rows(archive, 3)), 4)
            differences = rows(archive, 4)
            self.assertEqual(len(differences), 2)
            self.assertEqual(differences[1].find("{*}c[@r='J2']/{*}v").text, "-1")
            self.assertIn(b"=1+1", archive.read("xl/sharedStrings.xml"))
        with workbook("2026-11-15", 3) as archive:
            self.assertEqual(len(rows(archive, 3)), 1)
            self.assertEqual(len(rows(archive, 4)), 1)

    def test_reports_include_old_outstanding_items_and_active_cases(self):
        self.available()
        self.available("C-002")
        loan = self.requested("C-001", "C-002")
        self.post("gudang", f"/loans/{loan}/handover", physical_check="yes", recipient=self.recipient())
        self.post("ok", f"/loans/{loan}/receive", physical_check="yes")
        self.return_one(loan, "C-001", 1)
        case = self.conn.execute("SELECT id FROM discrepancy_cases").fetchone()["id"]

        supervisor = self.client("supervisor")
        query = "?day=2020-01-01&unit=2"
        page = supervisor.get("/reports" + query)
        self.assertIn(b"Belum ada serah terima pada tanggal ini", page.data)
        self.assertNotIn(f"C-001 · Pinjaman #{loan}".encode(), page.data)
        self.assertIn(f"C-002 · Pinjaman #{loan}".encode(), page.data)
        self.assertIn(f'href="/cases/{case}"'.encode(), page.data)
        other_unit = supervisor.get("/reports?day=2020-01-01&unit=3")
        self.assertNotIn(f'href="/cases/{case}"'.encode(), other_unit.data)
        self.assertNotIn(f"C-002 · Pinjaman #{loan}".encode(), other_unit.data)

        def detail_count(sheet):
            result = supervisor.get("/reports.xlsx" + query)
            self.assertEqual(result.status_code, 200)
            with ZipFile(BytesIO(result.data)) as archive:
                xml = ElementTree.fromstring(archive.read(f"xl/worksheets/sheet{sheet}.xml"))
                return len(xml.findall(".//{*}sheetData/{*}row")) - 1

        self.assertEqual(detail_count(5), 1)
        self.assertEqual(detail_count(6), 1)
        self.post("supervisor", f"/cases/{case}/investigate", reason="Pemeriksaan simulasi")
        self.assertEqual(detail_count(6), 1)
        self.post("supervisor", f"/cases/{case}/resolve", reason="Kasus simulasi selesai")
        self.return_one(loan, "C-002", 2)
        self.assertEqual(detail_count(5), 0)
        self.assertEqual(detail_count(6), 0)

    def test_dashboard_action_queues_follow_status_and_permissions(self):
        self.available()
        cycle = self.cycle("C-002")
        self.post("setting", f"/cycles/{cycle}/pack")
        self.post("steril", f"/cycles/{cycle}/batch-start", reference="QUEUE-SIM")
        cssd = self.client("setting")
        qc = self.client("qc")
        unit = self.client("ok")
        other_unit = self.client("ok2")
        supervisor = self.client("supervisor")

        queue = cssd.get("/").data
        self.assertIn(b"Perlu ditindaklanjuti", queue)
        self.assertIn(b"status=PROCESSING#daftar-kontainer", queue)
        self.assertNotIn(b"Tinjau hasil QC", queue)
        pending = cssd.get("/?modul=sterilisasi&status=PROCESSING").data
        self.assertIn(b"C-002", pending)
        self.assertNotIn(self.codes["C-001"].encode(), pending)
        self.assertEqual(cssd.get("/?modul=sterilisasi&status=QC_PENDING").status_code, 404)
        self.assertEqual(unit.get("/?modul=sterilisasi&status=PROCESSING").status_code, 404)

        self.post("steril", f"/cycles/{cycle}/batch-complete")
        self.assertIn(b"Tinjau hasil QC", qc.get("/").data)
        self.assertIn(b"C-002", qc.get("/?modul=qc&status=QC_PENDING").data)
        self.assertNotIn(self.codes["C-002"].encode(), cssd.get("/?modul=sterilisasi&status=PROCESSING").data)

        loan = self.requested("C-001")
        self.assertIn(b'id="antrean-gudang"', cssd.get("/?modul=gudang").data)
        self.post("gudang", f"/loans/{loan}/handover", physical_check="yes", recipient=self.recipient())
        link = f"/loans/{loan}#konfirmasi-penerimaan".encode()
        self.assertIn(link, unit.get("/").data)
        self.assertNotIn(link, other_unit.get("/").data)
        self.assertIn(b'id="konfirmasi-penerimaan"', unit.get(f"/loans/{loan}").data)
        self.post("ok", f"/loans/{loan}/receive", physical_check="yes")
        self.assertNotIn(link, unit.get("/").data)

        self.return_one(loan, "C-001", 1)
        self.assertIn(b"/reports#kasus-aktif", supervisor.get("/").data)
        self.assertIn(b'id="kasus-aktif"', supervisor.get("/reports").data)
        self.assertNotIn(b"Perlu ditindaklanjuti", self.client("admin").get("/").data)

    def test_stock_selection_and_warehouse_queue(self):
        self.available()
        self.processed("C-002")
        borrower = self.client("ok")
        warehouse = self.client("gudang")
        page = borrower.get("/loans/new")
        self.assertIn(self.codes["C-001"].encode(), page.data)
        self.assertNotIn(self.codes["C-002"].encode(), page.data)
        preview = borrower.get("/api/container-preview?code=C-001")
        self.assertEqual(preview.json, {
            "id": self.codes["C-001"], "label": "C-001", "set": "Set Bedah Minor", "instrument": None,
        })
        self.assertEqual(borrower.get("/api/container-preview?code=C-002").status_code, 409)
        self.assertEqual(warehouse.get("/api/container-preview?code=C-001").status_code, 403)
        self.post("ok", "/loans/new", 400, containers=["C-001", self.codes["C-001"]])

        result = self.post("ok", "/loans/new", containers=[self.codes["C-001"]])
        loan_id = int(result.location.split("/")[-1])
        queue = warehouse.get("/?modul=gudang")
        self.assertIn(result.location.encode(), queue.data)
        self.assertIn(b"Menunggu proses", queue.data)
        self.assertIn(b"Menunggu proses", borrower.get(result.location).data)
        summary = borrower.get("/").data.split(b"Peminjaman unit", 1)[1]
        self.assertIn("C-001 · Set Bedah Minor".encode(), summary)
        self.assertIn(b"Menunggu proses", summary)
        self.assertNotIn(b"OK Demo A", summary)
        self.post("gudang", f"/loans/{loan_id}/pick")
        self.assertIn(b"Sedang disiapkan", warehouse.get("/?modul=gudang").data)
        self.post("gudang", f"/loans/{loan_id}/handover", physical_check="yes", recipient=self.recipient())
        self.assertNotIn(result.location.encode(), warehouse.get("/?modul=gudang").data)
        self.assertIn(b"Diserahkan", borrower.get(result.location).data)
        self.assertNotIn(self.codes["C-001"].encode(), borrower.get("/loans/new").data)
        self.assertEqual(borrower.get("/api/container-preview?code=C-001").status_code, 409)
        self.post("ok", "/loans/new", 409, containers=[self.codes["C-001"]])

    def test_piece_stock_in_mixed_loan(self):
        self.available()
        self.post("admin", "/master/template", name="Pinset Anatomi", qty_2=1)
        template = self.conn.execute("SELECT id FROM templates WHERE name='Pinset Anatomi'").fetchone()["id"]
        for label in ("C-021", "C-022", "C-023"):
            self.post("admin", "/master/container", template=template, label=label)
            qr = self.conn.execute("SELECT qr FROM containers WHERE label=?", (label,)).fetchone()["qr"]
            self.post("setting", f"/c/{qr}/start")
            cycle_id = self.conn.execute("""
                SELECT cy.id FROM cycles cy JOIN containers c ON c.id=cy.container_id WHERE c.qr=?
            """, (qr,)).fetchone()["id"]
            self.post("setting", f"/cycles/{cycle_id}/verify", physical_check="yes", qty_2=1)
            self.post("setting", f"/cycles/{cycle_id}/pack")
            self.post("steril", f"/cycles/{cycle_id}/batch-start", reference=f"SIM-{label}")
            self.post("steril", f"/cycles/{cycle_id}/batch-complete")
            if label != "C-023":
                self.post("qc", f"/cycles/{cycle_id}/qc", outcome="RELEASE", evidence=f"SIM-{label}")

        borrower = self.client("ok")
        page = borrower.get("/loans/new").data
        self.assertIn(b'aria-label="Jumlah Pinset Anatomi"', page)
        self.assertIn(b"2 alat tersedia", page)
        self.assertIn(b"C-021", page)
        self.assertIn(b"C-022", page)
        self.assertNotIn(b"C-023", page)
        self.assertEqual(
            borrower.get("/api/container-preview?code=C-021").json["instrument"], "Pinset Anatomi",
        )
        self.post("ok", "/loans/new", 409, containers=["C-023"])

        needs_path = self.post("ok", "/loans/needs", set_1=1, piece_2=2).location
        self.post("gudang", needs_path + "/pick")
        self.post("gudang", needs_path + "/allocate", 409, containers=["C-021", "C-022"])
        self.post("gudang", needs_path + "/allocate", containers=["C-001", "C-021", "C-022"])
        self.post("gudang", needs_path + "/cancel", reason="Skenario pengujian selesai")

        response = self.post("ok", "/loans/new", containers=["C-001", "C-021", "C-022"])
        summary = borrower.get("/").data.split(b"Peminjaman unit", 1)[1]
        for label in ("C-021", "C-022"):
            self.assertIn(f"{label} · Pinset Anatomi".encode(), summary)
        self.assertIn("C-001 · Set Bedah Minor".encode(), summary)
        self.assertEqual(self.client("ok2").get(response.location).status_code, 404)
        warehouse = self.client("gudang")
        self.assertIn(b"Pinset Anatomi", warehouse.get(response.location).data)
        self.post("gudang", response.location + "/pick")
        self.post("gudang", response.location + "/handover", physical_check="yes", recipient=self.recipient())
        self.assertNotIn(b"C-021", borrower.get("/loans/new").data)

    def test_standard_need_accepts_empty_stock_and_reallocates(self):
        self.assertIn(b"Set Bedah Minor", self.client("ok").get("/loans/needs").data)
        fields = {"set_1": 1, "needed_at": "2026-11-16T08:30"}
        requested = self.post("ok", "/loans/needs", key="need-once", **fields)
        path = requested.location
        self.assertEqual(self.post("ok", "/loans/needs", key="need-once", **fields).location, path)
        self.assertEqual(self.client("ok2").get(path).status_code, 404)
        self.assertIn(b"08:30 WIB", self.client("ok").get(path).data)
        self.assertIn(path.encode(), self.client("gudang").get("/?modul=gudang").data)
        self.post("gudang", path + "/pick")
        self.post("gudang", path + "/handover", 409, physical_check="yes", recipient=self.recipient())
        first = self.available()
        second = self.available("C-002")
        self.post("ok", path + "/allocate", 403, containers=["C-001"])
        self.post("gudang", path + "/allocate", 409, containers=["C-001", "C-002"])
        self.post("gudang", path + "/allocate", containers=["C-001"])
        self.post("gudang", path + "/allocate", containers=["C-002"])
        self.post("gudang", path + "/handover", 409, allocation=first, physical_check="yes", recipient=self.recipient())
        self.post("gudang", path + "/handover", allocation=second, physical_check="yes", recipient=self.recipient())
        self.assertEqual(self.state("cycles", first), "AVAILABLE")
        self.assertEqual(self.state("cycles", second), "BORROWED")

    def test_custom_need_can_reuse_an_unassigned_standard_draft(self):
        qr = self.codes["C-001"]
        self.post("setting", f"/c/{qr}/start")
        cycle = self.conn.execute("SELECT id,template_id FROM cycles WHERE container_id=1").fetchone()
        path = self.post("ok", "/loans/needs?jenis=khusus", custom_2=3).location
        self.post("gudang", path + "/pick")
        self.assertIn(b"C-001", self.client("setting").get(path).data)
        self.post("setting", path + "/prepare-custom", container=1)
        assigned = self.conn.execute("SELECT id,template_id FROM cycles WHERE container_id=1").fetchall()
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0]["id"], cycle["id"])
        self.assertNotEqual(assigned[0]["template_id"], cycle["template_id"])
        self.assertEqual(self.conn.execute("SELECT template_id FROM containers WHERE id=1").fetchone()[0], cycle["template_id"])
        self.assertEqual(self.conn.execute("SELECT prepared_cycle_id FROM loans").fetchone()[0], cycle["id"])
        other = self.post("ok2", "/loans/needs?jenis=khusus", custom_2=4).location
        self.post("gudang", other + "/pick")
        self.post("setting", other + "/prepare-custom", 409, container=1)

    def test_custom_count_can_become_new_plan_without_rewriting_history(self):
        qr = self.codes["C-001"]
        path = f"/c/{qr}"
        self.post("setting", path + "/start")
        cycle = self.conn.execute("SELECT id,template_id FROM cycles").fetchone()
        old = f"/cycles/{cycle['id']}"
        self.post("setting", old + "/composition", template_id=cycle["template_id"], mode="custom", qty_1=1, qty_2=1)
        template = self.conn.execute("SELECT template_id FROM cycles").fetchone()[0]
        self.post("setting", old + "/verify", template_id=template, physical_check="yes", qty_1=3, qty_2=2)
        self.post("setting", old + "/pack", 409)
        self.assertIn(b"Gunakan hasil hitung sebagai rencana baru", self.client("setting").get(path).data)
        self.post("ok", old + "/revise-composition", 403, mode="use-count")
        self.post("setting", old + "/revise-composition", mode="use-count", key="revise-custom")
        self.post("setting", old + "/revise-composition", mode="use-count", key="revise-custom")
        self.post("setting", old + "/revise-composition", 409, mode="use-count")
        previous = self.conn.execute("SELECT closed_at FROM cycles WHERE id=?", (cycle["id"],)).fetchone()["closed_at"]
        self.assertIsNotNone(previous)
        self.assertEqual([tuple(r) for r in self.conn.execute(
            "SELECT expected,verified FROM cycle_items WHERE cycle_id=? ORDER BY instrument_id", (cycle["id"],)
        )], [(1, 3), (1, 2)])
        revised = self.conn.execute("SELECT id,template_id FROM cycles WHERE closed_at IS NULL").fetchone()
        self.assertEqual(self.state("cycles", revised["id"]), "DRAFT")
        new = f"/cycles/{revised['id']}"
        self.post("setting", new + "/pack", 409)
        self.post("setting", new + "/verify", template_id=revised["template_id"], physical_check="yes", qty_1=3, qty_2=2)
        self.post("setting", new + "/pack")
        self.assertEqual(self.state("cycles", revised["id"]), "PACKAGED")

    def test_linked_custom_set_can_recount_but_keeps_unit_plan(self):
        path = self.post("ok", "/loans/needs?jenis=khusus", custom_2=3).location
        self.post("gudang", path + "/pick")
        self.post("setting", path + "/prepare-custom", container=1)
        old = self.conn.execute("SELECT id,template_id FROM cycles").fetchone()
        cycle = f"/cycles/{old['id']}"
        self.post("setting", cycle + "/verify", template_id=old["template_id"], physical_check="yes", qty_2=2)
        self.post("setting", cycle + "/revise-composition", 409, mode="use-count")
        self.post("setting", cycle + "/revise-composition", mode="recount")
        new = self.conn.execute("SELECT id,template_id FROM cycles WHERE closed_at IS NULL").fetchone()
        self.assertEqual(new["template_id"], old["template_id"])
        self.assertEqual(self.conn.execute("SELECT prepared_cycle_id FROM loans").fetchone()[0], new["id"])
        self.post("setting", f"/cycles/{new['id']}/verify", template_id=new["template_id"], physical_check="yes", qty_2=3)
        self.post("setting", f"/cycles/{new['id']}/pack")

    def test_custom_need_to_return_checklist(self):
        request = self.post("ok", "/loans/needs?jenis=khusus", custom_2=3, custom_3=2)
        path = request.location
        self.post("gudang", path + "/pick")
        self.assertIn(b"Mulai setting sesuai permintaan", self.client("setting").get(path).data)
        setting = self.post("setting", path + "/prepare-custom", container=1)
        cycle_id, template = self.conn.execute("SELECT id,template_id FROM cycles WHERE container_id=1").fetchone()
        self.post("setting", path + "/prepare-custom", 409, container=2)
        self.post("gudang", path + "/allocate", 409, containers=["C-001"])
        base = f"/cycles/{cycle_id}"
        self.post("setting", base + "/verify", physical_check="yes", template_id=template, qty_2=3, qty_3=2)
        self.post("setting", base + "/pack")
        self.post("steril", base + "/batch-start", reference="SIM-KEBUTUHAN")
        self.post("steril", base + "/batch-complete")
        self.post("qc", base + "/qc", outcome="RELEASE", evidence="SIM-KEBUTUHAN")
        self.assertIn(b"C-001", self.client("gudang").get(path).data)
        self.post("gudang", path + "/allocate", containers=["C-001"])
        self.post("gudang", path + "/handover", allocation=cycle_id, physical_check="yes", recipient=self.recipient())
        self.post("ok", path + "/receive", physical_check="yes")
        container = self.client("dekon").get(setting.location)
        self.assertIn(b'name="count_2" value="match" required', container.data)
        item = self.conn.execute("SELECT id FROM loan_items WHERE cycle_id=?", (cycle_id,)).fetchone()["id"]
        returned = f"{setting.location}/return/{item}"
        self.post("dekon", returned, 400, physical_check="yes", count_2="match", count_3="different")
        self.post("dekon", returned, physical_check="yes", count_2="match", count_3="different", qty_3=1)
        self.assertEqual([tuple(item) for item in self.conn.execute(
            "SELECT expected,actual FROM return_items ORDER BY instrument_id"
        )], [(3, 3), (2, 1)])
        self.assertEqual(self.state("cycles", cycle_id), "DISCREPANCY")

    def test_rollback_when_one_in_batch_unavailable(self):
        first = self.available()
        second = self.available("C-002")
        bulk = self.requested("C-001", "C-002")
        competing = self.requested("C-002", user="ok2")
        self.post("gudang", f"/loans/{competing}/handover", physical_check="yes", recipient=self.recipient("ok2"))
        self.post("gudang", f"/loans/{bulk}/handover", 409, physical_check="yes", recipient=self.recipient())
        self.assertEqual(self.state("loans", bulk), "PICKING")
        self.assertEqual(self.state("cycles", first), "AVAILABLE")
        self.assertEqual(self.state("cycles", second), "BORROWED")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM loan_items WHERE loan_id=? AND handed_at IS NOT NULL", (bulk,)).fetchone()[0], 0)

    def test_concurrent_handover(self):
        self.available()
        one = self.requested("C-001")
        two = self.requested("C-001", user="ok2")
        warehouse = self.client("gudang")
        with warehouse.session_transaction() as session:
            shared = dict(session)
        barrier = Barrier(2)
        jobs = [(one, self.recipient()), (two, self.recipient("ok2"))]

        def submit(job):
            loan, recipient = job
            c = self.app.test_client()
            with c.session_transaction() as session:
                session.update(shared, csrf="race-csrf")
            barrier.wait(timeout=5)
            return c.post(f"/loans/{loan}/handover", data={
                "csrf": "race-csrf", "key": f"race-{loan}", "physical_check": "yes", "recipient": recipient,
            }).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(submit, jobs)), [303, 409])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM loan_items WHERE handed_at IS NOT NULL").fetchone()[0], 1)

    def test_database_guards_and_migration_reversal(self):
        first = self.cycle()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE cycle_items SET verified=8 WHERE cycle_id=?", (first,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE template_items SET expected=8 WHERE template_id=1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM audit_events")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO cycles(container_id,template_id,sequence,state,created_by) VALUES(1,1,99,'DRAFT',1)")
        db.migrate(self.conn, "down")
        db.migrate(self.conn, "up")
        self.assertEqual(self.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_qr_privacy_and_real_png(self):
        import cv2
        import numpy as np

        qr = self.codes["C-001"]
        anonymous = self.app.test_client()
        path = f"/c/{qr}"
        response = anonymous.get(path)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(b"Instrumen", response.data)
        self.assertEqual(self.login(anonymous, "setting", path).location, path)
        self.assertEqual(anonymous.post(path + "/start").status_code, 400)
        response = anonymous.get(path + "/qr.png")
        self.assertEqual(response.mimetype, "image/png")
        pixels = cv2.imdecode(np.frombuffer(response.data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        decoded, *_ = cv2.QRCodeDetector().detectAndDecode(pixels)
        self.assertEqual(decoded, "http://localhost" + path)


    def test_master_and_report_navigation(self):
        admin = self.client("admin")
        self.assertIn(b'href="/master"', admin.get("/").data)
        self.assertEqual(admin.get("/master").status_code, 200)
        self.assertEqual(self.client("ok").get("/master").status_code, 403)
        self.post("admin", "/master/instrument", name="Instrumen Tambahan")
        self.post("admin", "/master/template", name="Set Uji", qty_1=1)
        template_id = self.conn.execute("SELECT id FROM templates WHERE name='Set Uji'").fetchone()["id"]
        self.post("admin", "/master/container", label="C-003", template=template_id)
        self.assertIn(b"C-003", admin.get("/master").data)
        supervisor = self.client("supervisor")
        self.assertIn(b'href="/reports"', supervisor.get("/").data)
        self.assertEqual(supervisor.get("/reports").status_code, 200)
        self.assertEqual(supervisor.get("/reports?unit=invalid").status_code, 400)
        self.assertEqual(self.client("ok").get("/reports").status_code, 403)

    @unittest.skipUnless(os.environ.get("CSSD_TEST_DATABASE_URL"), "Set CSSD_TEST_DATABASE_URL for PostgreSQL")
    def test_postgres_backend(self):
        url = os.environ["CSSD_TEST_DATABASE_URL"]
        conn = db.Postgres(url)
        self.addCleanup(conn.close)
        marker = conn.execute("SELECT to_regnamespace('cssd_app') AS schema").fetchone()["schema"]
        self.assertIsNone(marker, "Use a fresh test database with no cssd_app schema")
        with db.write_transaction(conn):
            migration = db.MIGRATIONS / "postgres" / "001_up.sql"
            conn.execute(migration.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO cssd_app.schema_migrations VALUES (1)")
            conn.execute("INSERT INTO units(id,name) VALUES (99,'Legacy CSSD')")
            conn.execute("INSERT INTO users(id,username,name,password_hash,unit_id,role) "
                         "VALUES(99,'legacy.qc','Legacy QC','preserved',99,'QC')")
        db.apply_schema(conn)
        db.apply_schema(conn)
        self.assertIsNone(conn.execute("SELECT auth_user_id FROM users WHERE id=99").fetchone()["auth_user_id"])
        self.assertEqual(conn.execute("SELECT role,can_release_qc FROM users WHERE id=99").fetchone(),
                         {"role": "petugas_cssd", "can_release_qc": 1})
        conn.execute("DELETE FROM users WHERE id=99")
        conn.execute("DELETE FROM units WHERE id=99")
        db.seed(conn, {username: "synthetic-test-password" for username in db.DEMO_ROLES})
        self.conn = conn
        self.app.config["DATABASE_URL"] = url
        self.codes = {row["label"]: row["qr"] for row in conn.execute("SELECT label,qr FROM containers")}
        self.test_bulk_end_to_end()
        self.test_master_and_report_navigation()
        for query in ("UPDATE audit_events SET reason='tampered'", "DELETE FROM audit_events", "TRUNCATE audit_events"):
            with self.assertRaises(Exception) as raised, db.write_transaction(conn):
                conn.execute(query)
            self.assertEqual(getattr(raised.exception, "sqlstate", None), "23514")
