# Build and release

> Windows releases use Nuitka. The performance and security comparison, the
> PyInstaller fallback, and outstanding validation are documented in the
> Portuguese [Nuitka assessment](AVALIACAO-NUITKA.md).

[Leia em português](COMPILACAO-E-RELEASE.md)

Official builds are produced by GitHub Actions. A push to `main` validates and builds Windows, macOS, and Linux. Only if every platform passes does the workflow create the `vX.Y.Z` tag matching `APP_VERSION` and publish the release. A manually pushed tag remains compatible with the same validation flow.

## Release files

| Platform | Versioned file | Stable README alias |
| --- | --- | --- |
| Windows installer | `BaixadorYtdlp-X.Y.Z-setup.exe` | `baixador-ytdlp-setup.exe` |
| Windows portable | `BaixadorYtdlp-X.Y.Z-portable-windows.zip` | `baixador-ytdlp-portable-windows.zip` |
| macOS Apple Silicon installer | `BaixadorYtdlp-X.Y.Z-macos-arm64.dmg` | `baixador-ytdlp-macos-arm64.dmg` |
| macOS Apple Silicon portable | `BaixadorYtdlp-X.Y.Z-macos-arm64.zip` | `baixador-ytdlp-macos-arm64.zip` |
| Linux Ubuntu/Debian x86_64 package | `BaixadorYtdlp-X.Y.Z-linux-amd64.deb` | `baixador-ytdlp-linux-amd64.deb` |
| Linux x86_64 portable | `BaixadorYtdlp-X.Y.Z-portable-linux-x86_64.tar.gz` | `baixador-ytdlp-portable-linux-x86_64.tar.gz` |

`SHA256SUMS.txt`, `SHA256SUMS-macos.txt`, `SHA256SUMS-linux.txt`, CycloneDX inventories (`sbom-*.cdx.json`), and provenance attestations accompany the packages. Stable aliases keep `/releases/latest/download/...` links valid after newer versions are published.

The workflow checks that all six aliases are listed in the README and that every package and hash reaches the release step. A packaging error therefore prevents publication of a release with missing downloads. If a release for the version already exists without assets, the approved build updates it.

## Publishing

1. Update the app version for a distributed change.
2. Run tests and push the commit to `main`.
3. Follow the run in [GitHub Actions](../../actions): it validates all three systems, creates the matching tag, and publishes the release.
4. Announce the release only after **Build Windows**, **Build macOS Apple Silicon**, **Build Linux (Ubuntu/Debian)**, and **Publish release** all succeed.

Do not create the tag or release manually in the normal workflow. The automation creates or updates both when all packages finish. While the final step is still running, download links can return “file not found.”

## Local development

`build.ps1` and `build.cmd` are development helpers only. On Windows,
`build.ps1` defaults to Nuitka; use `-Packager PyInstaller` for the fallback
route. Use the artifacts produced by GitHub Actions for distribution.

