"""Multi-process exclusive session ownership contracts (e08s01)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from orbitrelay.sessions import SessionBusyError, SessionStore


class SessionConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "sessions"
        self.store = SessionStore(root=self.root)
        self.metadata = self.store.create(session_id="shared", model="m")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _spawn(self, script: str, *args: str) -> subprocess.Popen[str]:
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        return subprocess.Popen(
            [sys.executable, "-c", script, *args],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_second_owner_fails_immediately(self) -> None:
        holder = self.store.acquire_lease("shared")
        try:
            with self.assertRaises(SessionBusyError):
                self.store.acquire_lease("shared")
            self.assertTrue(self.store.is_session_active("shared"))
        finally:
            holder.release()
        self.assertFalse(self.store.is_session_active("shared"))

    def test_bounded_wait_acquires_after_release(self) -> None:
        script = textwrap.dedent(
            f"""
            import time
            from pathlib import Path
            from orbitrelay.sessions import SessionStore
            store = SessionStore(root=Path({str(self.root)!r}))
            lease = store.acquire_lease("shared")
            print("HOLD", flush=True)
            time.sleep(0.4)
            lease.release()
            print("RELEASED", flush=True)
            """
        )
        proc = self._spawn(script)
        # wait until holding
        assert proc.stdout is not None
        line = proc.stdout.readline()
        self.assertIn("HOLD", line)
        started = time.time()
        lease = self.store.acquire_lease("shared", wait_seconds=2.0)
        elapsed = time.time() - started
        lease.release()
        _out, err = proc.communicate(timeout=3)
        self.assertEqual(proc.returncode, 0, err)
        self.assertLess(elapsed, 2.0)
        self.assertGreaterEqual(elapsed, 0.2)

    def test_bounded_wait_times_out(self) -> None:
        holder = self.store.acquire_lease("shared")
        try:
            started = time.time()
            with self.assertRaises(SessionBusyError):
                self.store.acquire_lease("shared", wait_seconds=0.2)
            self.assertGreaterEqual(time.time() - started, 0.2)
        finally:
            holder.release()

    def test_crash_releases_kernel_lock(self) -> None:
        script = textwrap.dedent(
            f"""
            import os
            from pathlib import Path
            from orbitrelay.sessions import SessionStore
            store = SessionStore(root=Path({str(self.root)!r}))
            lease = store.acquire_lease("shared")
            print("HOLD", flush=True)
            os._exit(0)
            """
        )
        proc = self._spawn(script)
        assert proc.stdout is not None
        self.assertIn("HOLD", proc.stdout.readline())
        proc.communicate(timeout=2)
        # lock should be free after process exit
        lease = self.store.acquire_lease("shared")
        lease.release()

    def test_independent_sessions_do_not_block(self) -> None:
        self.store.create(session_id="other", model="m2")
        first = self.store.acquire_lease("shared")
        second = self.store.acquire_lease("other")
        first.release()
        second.release()

    def test_conflict_before_provider_via_cli(self) -> None:
        # Hold lease in this process; another acquirer fails before any provider work.
        holder = self.store.acquire_lease("shared")
        try:
            with self.assertRaises(SessionBusyError):
                SessionStore(root=self.root).acquire_lease("shared")
        finally:
            holder.release()


if __name__ == "__main__":
    unittest.main()
