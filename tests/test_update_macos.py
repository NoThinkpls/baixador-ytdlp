"""Atualização do app no macOS: antes a checagem dizia "já está atualizado" sempre."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp.updater import (_MAC_SWAP_SCRIPT, MACOS_STAGING, AppUpdater, UpdateError,
                                    mac_app_bundle)

ZIP = "BaixadorYtdlp-1.13.8-macos-arm64.zip"


def _payload(*extra_assets: dict) -> dict:
    return {
        "tag_name": "v1.13.8",
        "html_url": "https://example.invalid/release",
        "assets": [
            {"name": "BaixadorYtdlp-1.13.8-setup.exe", "browser_download_url": "https://e.invalid/exe"},
            {"name": ZIP, "size": 300, "browser_download_url": "https://e.invalid/zip"},
            {"name": "SHA256SUMS.txt", "browser_download_url": "https://e.invalid/sums"},
            *extra_assets,
        ],
    }


def _on_mac():
    return (patch("baixador_ytdlp.updater.IS_WINDOWS", False),
            patch("baixador_ytdlp.updater.IS_MACOS", True))


class MacFindUpdateTests(unittest.TestCase):
    def test_mac_finds_the_zip_of_the_new_version(self) -> None:
        sums = "a" * 64 + "  BaixadorYtdlp-1.13.8-setup.exe\n" + "b" * 64 + f"  {ZIP}\n"
        windows, mac = _on_mac()
        with windows, mac, patch.object(AppUpdater, "_request_json", return_value=_payload()), \
                patch.object(AppUpdater, "_request_text", return_value=sums):
            release = AppUpdater().find_update("1.13.7")
        assert release is not None
        self.assertEqual(release.installer_name, ZIP)
        self.assertEqual(release.sha256, "b" * 64)
        self.assertEqual(release.size, 300)

    def test_mac_still_reports_current_version_as_up_to_date(self) -> None:
        windows, mac = _on_mac()
        with windows, mac, patch.object(AppUpdater, "_request_json", return_value=_payload()):
            self.assertIsNone(AppUpdater().find_update("1.13.8"))

    def test_older_release_uses_the_macos_checksum_file(self) -> None:
        # Até a 1.13.7 o hash do Mac só estava no SHA256SUMS-macos.txt.
        texts = {
            "https://e.invalid/sums": "a" * 64 + "  BaixadorYtdlp-1.13.8-setup.exe\n",
            "https://e.invalid/sums-mac": "c" * 64 + f"  dist/installer/{ZIP}\n",
        }
        payload = _payload({"name": "SHA256SUMS-macos.txt",
                            "browser_download_url": "https://e.invalid/sums-mac"})
        windows, mac = _on_mac()
        with windows, mac, patch.object(AppUpdater, "_request_json", return_value=payload), \
                patch.object(AppUpdater, "_request_text", side_effect=texts.__getitem__):
            release = AppUpdater().find_update("1.13.7")
        assert release is not None
        self.assertEqual(release.sha256, "c" * 64)

    def test_signed_release_does_not_accept_the_unsigned_macos_file(self) -> None:
        texts = {
            "https://e.invalid/sums": "a" * 64 + "  BaixadorYtdlp-1.13.8-setup.exe\n",
            "https://e.invalid/sums-mac": "c" * 64 + f"  {ZIP}\n",
        }
        payload = _payload({"name": "SHA256SUMS-macos.txt",
                            "browser_download_url": "https://e.invalid/sums-mac"})
        windows, mac = _on_mac()
        with windows, mac, patch("baixador_ytdlp.updater.RELEASE_PUBLIC_KEYS", ("chave",)), \
                patch.object(AppUpdater, "_verify_checksum_signature"), \
                patch.object(AppUpdater, "_request_json", return_value=payload), \
                patch.object(AppUpdater, "_request_text", side_effect=texts.__getitem__), \
                self.assertRaises(UpdateError):
            AppUpdater().find_update("1.13.7")


class MacBundleTests(unittest.TestCase):
    def test_source_checkout_is_never_replaced(self) -> None:
        # sys.executable do venv resolve para o Python.app do framework.
        python_app = "/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app"
        with self.assertRaisesRegex(UpdateError, "código-fonte"):
            mac_app_bundle(f"{python_app}/Contents/MacOS/Python", frozen=False)

    def test_translocated_copy_asks_to_move_to_applications(self) -> None:
        path = "/private/var/folders/x/AppTranslocation/ABC/d/baixador-ytdlp.app/Contents/MacOS/b"
        with self.assertRaisesRegex(UpdateError, "Aplicativos"):
            mac_app_bundle(path, frozen=True)

    def test_finds_the_running_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / "baixador-ytdlp.app"
            (app / "Contents" / "MacOS").mkdir(parents=True)
            exe = app / "Contents" / "MacOS" / "baixador-ytdlp"
            exe.write_text("")
            self.assertEqual(mac_app_bundle(str(exe), frozen=True), app.resolve())


class MacLaunchTests(unittest.TestCase):
    def _run(self, codesign_code: int):
        calls: list[list[str]] = []

        def fake_run(argv, **_kwargs):
            calls.append(list(argv))
            if argv[0].endswith("ditto"):
                bundle = Path(argv[-1]) / "baixador-ytdlp-portable" / "baixador-ytdlp.app"
                (bundle / "Contents").mkdir(parents=True)
            code = codesign_code if argv[0].endswith("codesign") else 0
            return subprocess.CompletedProcess(argv, code, "", "")

        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        archive = Path(folder) / ZIP
        archive.write_bytes(b"PK")
        target = Path("/Applications/baixador-ytdlp.app")
        windows, mac = _on_mac()
        with windows, mac, patch("baixador_ytdlp.updater.UPDATE_DIR", Path(folder)), \
                patch("baixador_ytdlp.updater.mac_app_bundle", return_value=target), \
                patch("baixador_ytdlp.updater.subprocess.run", side_effect=fake_run), \
                patch("baixador_ytdlp.updater.subprocess.Popen") as popen:
            try:
                AppUpdater.launch_installer(archive)
            except UpdateError as exc:
                return calls, popen, exc, Path(folder)
        return calls, popen, None, Path(folder)

    def test_valid_bundle_schedules_the_swap_after_the_app_closes(self) -> None:
        calls, popen, error, folder = self._run(codesign_code=0)
        self.assertIsNone(error)
        self.assertTrue(calls[0][0].endswith("ditto"))
        self.assertIn("--strict", calls[1])
        argv = popen.call_args.args[0]
        self.assertEqual(argv[:3], ["/bin/sh", "-c", _MAC_SWAP_SCRIPT])
        self.assertEqual(argv[4], str(os.getpid()))
        self.assertEqual(argv[5], "/Applications/baixador-ytdlp.app")
        self.assertEqual(argv[6], str(folder / MACOS_STAGING / "baixador-ytdlp-portable"
                                      / "baixador-ytdlp.app"))
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_invalid_signature_blocks_the_swap(self) -> None:
        _calls, popen, error, _folder = self._run(codesign_code=1)
        self.assertIsInstance(error, UpdateError)
        popen.assert_not_called()


@unittest.skipUnless(shutil.which("sh"), "sh ausente")
class MacSwapScriptTests(unittest.TestCase):
    """Roda o script de verdade, com um ``open`` falso no PATH."""

    def _swap(self, folder: Path, new_exists: bool) -> tuple[Path, Path]:
        fake_bin = folder / "bin"
        fake_bin.mkdir()
        opened = folder / "aberto.txt"
        (fake_bin / "open").write_text(f'#!/bin/sh\necho "$1" > "{opened}"\n')
        (fake_bin / "open").chmod(0o755)
        target = folder / "Apps" / "baixador-ytdlp.app"
        (target / "Contents").mkdir(parents=True)
        (target / "Contents" / "versao").write_text("antiga")
        new = folder / "nova" / "baixador-ytdlp.app"
        if new_exists:
            (new / "Contents").mkdir(parents=True)
            (new / "Contents" / "versao").write_text("nova")
        finished = subprocess.Popen(["true"])
        finished.wait()
        env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"}
        subprocess.run(["sh", "-c", _MAC_SWAP_SCRIPT, "teste", str(finished.pid), str(target),
                        str(new), str(folder / "log.txt")], env=env, check=False, timeout=30)
        return target, opened

    def test_swaps_the_bundle_and_reopens_the_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            target, opened = self._swap(folder, new_exists=True)
            self.assertEqual((target / "Contents" / "versao").read_text(), "nova")
            self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ["baixador-ytdlp.app"])
            self.assertEqual(opened.read_text().strip(), str(target))

    def test_failed_swap_restores_the_previous_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            target, opened = self._swap(folder, new_exists=False)
            self.assertEqual((target / "Contents" / "versao").read_text(), "antiga")
            self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ["baixador-ytdlp.app"])
            self.assertTrue(opened.is_file())


if __name__ == "__main__":
    unittest.main()
