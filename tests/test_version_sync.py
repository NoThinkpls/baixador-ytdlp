from __future__ import annotations

import re
import unittest
from pathlib import Path

from baixador_ytdlp.config import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


class VersionSyncTests(unittest.TestCase):
    def test_all_windows_metadata_matches_app_version(self) -> None:
        installer = (ROOT / "installer.iss").read_text(encoding="utf-8")
        info = (ROOT / "version_info.txt").read_text(encoding="utf-8")
        self.assertIn(f'#define AppVersion "{APP_VERSION}"', installer)
        self.assertEqual(
            set(re.findall(r"(?:FileVersion|ProductVersion)', '([0-9.]+)'", info)),
            {f"{APP_VERSION}.0"},
        )


if __name__ == "__main__":
    unittest.main()
