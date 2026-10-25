import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "memory.py"
SPEC = importlib.util.spec_from_file_location("song_memory", SCRIPT)
memory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(memory)
TODAY = date(2026, 10, 25)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="song-deep-dive-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "personal-data"
        self.env = dict(os.environ, SONG_DEEP_DIVE_DATA_DIR=str(self.directory), PYTHONDONTWRITEBYTECODE="1")

    def call(self, *args, success=True, env=None):
        process = subprocess.run([sys.executable, "-B", str(SCRIPT), "--today", TODAY.isoformat(), *args], env=env or self.env, capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(process.returncode == 0, success, process.stdout + process.stderr)
        self.assertFalse(process.stderr, process.stderr)
        output = json.loads(process.stdout)
        self.assertEqual(output["ok"], success)
        return output

    def write_state(self, state):
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "preferences.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def test_show_and_filter_do_not_create_data(self):
        output = self.call("show")
        self.assertFalse(output["exists"])
        self.assertFalse(output["saved"])
        self.assertEqual(output["state"], memory.empty_state())
        self.call("filter", "--track", "evermore", "Taylor Swift")
        self.assertFalse(self.directory.exists())

    def test_onboarding_skip_survives_new_process(self):
        self.call("onboard", "--skip")
        output = self.call("show")
        self.assertEqual(output["state"]["onboarding_status"], "skipped")
        self.assertTrue(output["exists"])

    def test_explicit_artist_update_completes_initial_onboarding(self):
        self.call("artists", "add", "--artist", "王菲")
        self.assertEqual(self.call("show")["state"]["onboarding_status"], "completed")

    def test_artist_updates_preserve_other_state_and_deduplicate(self):
        self.call("onboard", "--artist", "Taylor Swift", "--artist", "陈奕迅")
        self.call("record", "--track", "evermore", "Taylor Swift")
        output = self.call("artists", "add", "--artist", "  TAYLOR   SWIFT ", "--artist", "Ariana Grande")
        self.assertEqual(output["state"]["favorite_artists"], ["Taylor Swift", "陈奕迅", "Ariana Grande"])
        output = self.call("artists", "remove", "--artist", "taylor swift")
        self.assertEqual(output["state"]["favorite_artists"], ["陈奕迅", "Ariana Grande"])
        output = self.call("artists", "set", "--artist", "王菲")
        self.assertEqual(output["state"]["favorite_artists"], ["王菲"])
        self.assertEqual(len(output["state"]["recent_recommendations"]), 1)

    def test_filter_uses_identity_not_listening_history(self):
        self.call("record", "--track", "evermore", "Taylor Swift", "--track", "ghostin", "Ariana Grande")
        output = self.call("filter", "--track", "ＥＶＥＲＭＯＲＥ", " TAYLOR   SWIFT", "--track", "new song", "artist", "--track", "NEW SONG", "ARTIST")
        self.assertEqual([item["title"] for item in output["available"]], ["new song"])
        self.assertEqual(len(output["excluded"]), 2)
        self.assertNotIn("listening_history", output["state"])
        self.assertNotIn("mood", output["state"])

    def test_recording_same_track_refreshes_without_duplicates(self):
        state = memory.empty_state()
        state["recent_recommendations"] = [{"track_id": memory.track_id("evermore", "Taylor Swift"), "recommended_on": "2026-10-01"}]
        self.write_state(state)
        output = self.call("record", "--track", "EVERMORE", "taylor swift")
        self.assertEqual(len(output["state"]["recent_recommendations"]), 1)
        self.assertEqual(output["state"]["recent_recommendations"][0]["recommended_on"], TODAY.isoformat())

    def test_retention_boundary_and_future_clock(self):
        state = memory.empty_state()
        state["recent_recommendations"] = [
            {"track_id": str(days), "recommended_on": (TODAY - timedelta(days=days)).isoformat()}
            for days in (89, 90, -1)
        ]
        self.write_state(state)
        before = (self.directory / "preferences.json").read_bytes()
        shown = self.call("show")["state"]
        self.assertEqual({item["track_id"] for item in shown["recent_recommendations"]}, {"89", "-1"})
        self.assertEqual((self.directory / "preferences.json").read_bytes(), before)
        saved = self.call("artists", "add", "--artist", "王菲")["state"]
        self.assertEqual({item["track_id"] for item in saved["recent_recommendations"]}, {"89", "-1"})

    def test_corrupt_memory_is_not_overwritten_even_by_clear(self):
        self.directory.mkdir()
        target = self.directory / "preferences.json"
        target.write_bytes(b"{broken\xff")
        before = target.read_bytes()
        for command in (("show",), ("onboard", "--skip"), ("clear", "--scope", "all")):
            output = self.call(*command, success=False)
            self.assertEqual(output["error"]["code"], "corrupt_memory")
            self.assertEqual(target.read_bytes(), before)

    def test_unknown_schema_and_extra_personal_fields_are_preserved(self):
        for change in ({"schema_version": 2}, {"mood": "private"}, {"recent_recommendations": [{"track_id": "a", "recommended_on": "not-a-date"}]}):
            state = memory.empty_state()
            state.update(change)
            self.write_state(state)
            before = (self.directory / "preferences.json").read_bytes()
            self.call("artists", "add", "--artist", "Taylor Swift", success=False)
            self.assertEqual((self.directory / "preferences.json").read_bytes(), before)

    def test_empty_artist_and_invalid_date_are_not_saved(self):
        self.call("onboard", "--artist", "  ", success=False)
        self.assertFalse((self.directory / "preferences.json").exists())
        env = dict(self.env)
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--today", "2026-02-30", "show"], env=env, capture_output=True, encoding="utf-8")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid_date")

    def test_clear_scopes(self):
        self.call("onboard", "--artist", "Taylor Swift")
        self.call("record", "--track", "evermore", "Taylor Swift")
        output = self.call("clear", "--scope", "recommendations")["state"]
        self.assertEqual(output["favorite_artists"], ["Taylor Swift"])
        self.assertEqual(output["recent_recommendations"], [])
        output = self.call("clear", "--scope", "artists")["state"]
        self.assertEqual(output["onboarding_status"], "completed")
        self.assertEqual(self.call("clear", "--scope", "all")["state"], memory.empty_state())

    def test_permission_error_is_not_treated_as_missing_memory(self):
        store = memory.MemoryStore(self.directory, TODAY)
        with patch.object(Path, "open", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                store.read()
        self.assertFalse(self.directory.exists())

    def test_failed_atomic_replace_keeps_original_and_cleans_temp(self):
        self.call("onboard", "--artist", "Taylor Swift")
        before = (self.directory / "preferences.json").read_bytes()
        store = memory.MemoryStore(self.directory, TODAY)
        with patch.object(memory.os, "replace", side_effect=PermissionError("read only")):
            with self.assertRaises(PermissionError):
                store.mutate(lambda state: state["favorite_artists"].append("Ariana Grande"))
        self.assertEqual((self.directory / "preferences.json").read_bytes(), before)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    @unittest.skipUnless(os.name == "nt", "Real Windows read-only file behavior")
    def test_read_only_file_can_be_read_but_not_replaced(self):
        import stat
        self.call("onboard", "--artist", "Taylor Swift")
        target = self.directory / "preferences.json"
        before = target.read_bytes()
        target.chmod(stat.S_IREAD)
        try:
            self.call("show")
            output = self.call("artists", "add", "--artist", "Ariana Grande", success=False)
            self.assertEqual(output["error"]["code"], "permission_denied")
            self.assertEqual(target.read_bytes(), before)
        finally:
            target.chmod(stat.S_IWRITE | stat.S_IREAD)

    def test_concurrent_processes_preserve_all_updates(self):
        self.call("onboard", "--skip")
        processes = []
        for number in range(8):
            commands = ("artists", "add", "--artist", f"Artist {number}") if number % 2 == 0 else ("record", "--track", f"Track {number}", "Artist")
            processes.append(subprocess.Popen([sys.executable, "-B", str(SCRIPT), "--today", TODAY.isoformat(), *commands], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, stdout.decode("utf-8") + stderr.decode("utf-8"))
        state = self.call("show")["state"]
        self.assertEqual(set(state["favorite_artists"]), {f"Artist {n}" for n in range(0, 8, 2)})
        self.assertEqual(len(state["recent_recommendations"]), 4)

    def test_live_lock_times_out_and_releases(self):
        self.directory.mkdir()
        lock = self.directory / "preferences.json.lock"
        with memory.exclusive_lock(lock):
            process = subprocess.run([sys.executable, "-B", str(SCRIPT), "--today", TODAY.isoformat(), "--lock-timeout", "0.05", "onboard", "--skip"], env=self.env, capture_output=True, encoding="utf-8", timeout=10)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(json.loads(process.stdout)["error"]["code"], "lock_timeout")
            self.assertFalse((self.directory / "preferences.json").exists())
        self.call("onboard", "--skip")

    def test_competing_recommendations_are_registered_only_once(self):
        commands = [sys.executable, "-B", str(SCRIPT), "--today", TODAY.isoformat(), "record", "--if-new", "--track", "evermore", "Taylor Swift"]
        processes = [subprocess.Popen(commands, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(6)]
        successes = 0
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, stderr.decode("utf-8"))
            result = json.loads(stdout)
            successes += len(result["recorded"])
            self.assertEqual(len(result["recorded"]) + len(result["already_recent"]), 1)
        self.assertEqual(successes, 1)
        self.assertEqual(len(self.call("show")["state"]["recent_recommendations"]), 1)


class PathTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.gettempdir()).resolve() / "song-home"

    def test_override_and_reject_relative_paths(self):
        expected = self.home / "custom"
        self.assertEqual(memory.data_directory({"SONG_DEEP_DIVE_DATA_DIR": str(expected)}, "win32", self.home), expected)
        with self.assertRaises(memory.StoreError):
            memory.data_directory({"SONG_DEEP_DIVE_DATA_DIR": "relative"}, "win32", self.home)
        with self.assertRaises(memory.StoreError):
            memory.MemoryStore(ROOT / "data", TODAY)

    def test_windows_default_and_environment(self):
        self.assertEqual(memory.data_directory({}, "win32", self.home), self.home / "AppData" / "Local" / "song-deep-dive")
        self.assertEqual(memory.data_directory({"LOCALAPPDATA": str(self.home / "local")}, "win32", self.home), self.home / "local" / "song-deep-dive")

    def test_macos_and_linux_defaults(self):
        self.assertEqual(memory.data_directory({}, "darwin", self.home), self.home / "Library" / "Application Support" / "song-deep-dive")
        self.assertEqual(memory.data_directory({}, "linux", self.home), self.home / ".local" / "share" / "song-deep-dive")
        self.assertEqual(memory.data_directory({"XDG_DATA_HOME": str(self.home / "xdg")}, "linux", self.home), self.home / "xdg" / "song-deep-dive")
        with self.assertRaises(memory.StoreError):
            memory.data_directory({"XDG_DATA_HOME": "relative"}, "linux", self.home)


if __name__ == "__main__":
    unittest.main()
