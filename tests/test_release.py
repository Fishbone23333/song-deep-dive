import importlib.util
from pathlib import Path
import re
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("song_release", ROOT / "scripts" / "build_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_archive_contains_portable_skill_and_no_development_or_personal_data(self):
        with tempfile.TemporaryDirectory(prefix="song-release-test-") as folder:
            archive = release.build(ROOT, Path(folder) / "song-deep-dive.zip")
            with ZipFile(archive) as package:
                names = set(package.namelist())
                self.assertEqual(names, {
                    "song-deep-dive/SKILL.md",
                    "song-deep-dive/README.md",
                    "song-deep-dive/scripts/memory.py",
                    "song-deep-dive/references/memory.md",
                    "song-deep-dive/references/listening-guide.md",
                })
                self.assertIsNone(package.testzip())

    def test_archive_is_reproducible_and_self_contained(self):
        with tempfile.TemporaryDirectory(prefix="song-release-test-") as folder:
            first = release.build(ROOT, Path(folder) / "first.zip")
            second = release.build(ROOT, Path(folder) / "second.zip")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with ZipFile(first) as package:
                package.extractall(Path(folder) / "extracted")
            installed = Path(folder) / "extracted" / "song-deep-dive"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "scripts" / "memory.py").is_file())
            self.assertTrue((installed / "references" / "memory.md").is_file())
            for document in installed.rglob("*.md"):
                for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                    if target.startswith(("https://", "http://", "#")):
                        continue
                    self.assertTrue((document.parent / target).is_file(), f"Broken packaged link: {document.name} -> {target}")


if __name__ == "__main__":
    unittest.main()
