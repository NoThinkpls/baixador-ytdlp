"""Mesma versão, executável diferente do publicado: oferecer reinstalar a oficial."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp.updater import (APP_HASH_NAMES, AppUpdater, ReleaseInfo,
                                    installed_executable_sha256)

ROOT = Path(__file__).resolve().parents[1]
ZIP = "BaixadorYtdlp-1.14.1-macos-arm64.zip"
EXE = "BaixadorYtdlp-1.14.1-setup.exe"


def _payload() -> dict:
    return {
        "tag_name": "v1.14.1",
        "html_url": "https://example.invalid/release",
        "body": "notas",
        "assets": [
            {"name": EXE, "size": 100, "browser_download_url": "https://e.invalid/exe"},
            {"name": ZIP, "size": 300, "browser_download_url": "https://e.invalid/zip"},
            {"name": "SHA256SUMS.txt", "browser_download_url": "https://e.invalid/sums"},
        ],
    }


def _sums(app_hash: str | None) -> str:
    lines = ["a" * 64 + f"  {EXE}", "b" * 64 + f"  {ZIP}"]
    if app_hash:
        lines.append(f"{app_hash}  {APP_HASH_NAMES['macos']}")
    return "\n".join(lines) + "\n"


class ExecutableHashTests(unittest.TestCase):
    def test_source_run_has_nothing_to_compare(self) -> None:
        self.assertIsNone(installed_executable_sha256(frozen=False))

    def test_only_the_app_executable_is_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            python = Path(folder) / "python3"
            python.write_bytes(b"x")
            self.assertIsNone(installed_executable_sha256(str(python), frozen=True))
            app = Path(folder) / "baixador-ytdlp"
            app.write_bytes(b"conteudo")
            self.assertEqual(installed_executable_sha256(str(app), frozen=True),
                             hashlib.sha256(b"conteudo").hexdigest())


class RepairOfferTests(unittest.TestCase):
    def _find(self, local: str | None, sums: str) -> ReleaseInfo | None:
        with patch("baixador_ytdlp.updater.IS_WINDOWS", False), \
                patch("baixador_ytdlp.updater.IS_MACOS", True), \
                patch("baixador_ytdlp.updater.installed_executable_sha256", return_value=local), \
                patch.object(AppUpdater, "_request_json", return_value=_payload()), \
                patch.object(AppUpdater, "_request_text", return_value=sums):
            return AppUpdater().find_update("1.14.1")

    def test_same_version_with_different_executable_offers_reinstall(self) -> None:
        release = self._find("c" * 64, _sums("d" * 64))
        assert release is not None
        self.assertTrue(release.repair)
        self.assertEqual(release.installer_name, ZIP)
        self.assertEqual(release.sha256, "b" * 64)

    def test_matching_executable_is_up_to_date(self) -> None:
        self.assertIsNone(self._find("d" * 64, _sums("D" * 64)))

    def test_release_without_app_hash_keeps_old_behaviour(self) -> None:
        self.assertIsNone(self._find("c" * 64, _sums(None)))

    def test_source_run_is_never_offered_a_reinstall(self) -> None:
        self.assertIsNone(self._find(None, _sums("d" * 64)))

    def test_newer_release_is_a_normal_update(self) -> None:
        with patch("baixador_ytdlp.updater.IS_WINDOWS", False), \
                patch("baixador_ytdlp.updater.IS_MACOS", True), \
                patch.object(AppUpdater, "_request_json", return_value=_payload()), \
                patch.object(AppUpdater, "_request_text", return_value=_sums("d" * 64)):
            release = AppUpdater().find_update("1.14.0")
        assert release is not None
        self.assertFalse(release.repair)


class RepairCannotBeSkippedTests(unittest.TestCase):
    def test_dismissed_version_does_not_hide_a_reinstall(self) -> None:
        from baixador_ytdlp.workers import AppUpdateCheckWorker

        repair = ReleaseInfo("1.14.1", "v1.14.1", "https://e.invalid", ZIP,
                             "https://e.invalid/zip", "b" * 64, repair=True)
        worker = AppUpdateCheckWorker(enabled=True, last_checked_at=0, interval_hours=0,
                                      dismissed_version="1.14.1")
        received = []
        worker.finished_ok.connect(lambda release, _at: received.append(release))
        with patch.object(AppUpdater, "find_update", return_value=repair):
            worker.run()
        self.assertEqual(received, [repair])


class WorkflowPublishesAppHashesTests(unittest.TestCase):
    def test_every_platform_publishes_the_executable_hash(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        for name in APP_HASH_NAMES.values():
            self.assertIn(name, workflow)

    def test_macos_bundle_reports_the_real_version(self) -> None:
        # O Info.plist do PyInstaller vinha com 0.0.0 no "Obter Informações".
        workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
        self.assertIn("Set :CFBundleShortVersionString", workflow)


if __name__ == "__main__":
    unittest.main()
