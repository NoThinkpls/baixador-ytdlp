# Platforms, performance, and security

[Leia em português](PLATAFORMAS-E-SEGURANCA.md)

## Windows

The installer is per-user and does not require UAC. The portable edition does not create shortcuts or modify the installed-app list: extract the ZIP and run `baixador-ytdlp.exe`. Its settings, logs, and tools are kept in the `data` folder next to the executable.

Windows may show SmartScreen while the installer has not accumulated enough signing reputation. Every release contains `SHA256SUMS.txt`; validate the installer with:

```powershell
Get-FileHash .\baixador-ytdlp-setup.exe -Algorithm SHA256
```

## macOS on Apple Silicon

The macOS build is arm64 for M1, M2, M3, and M4 Macs running macOS 14 or later.

- **DMG:** open it, drag `baixador-ytdlp.app` to **Applications**, then eject the disk image.
- **Portable ZIP:** extract it and open `baixador-ytdlp.app` from any folder, without installation.

Until Developer ID signing and notarization are configured, macOS can ask for additional confirmation under **Privacy & Security**. In-app updating is available only through the Windows installer; download new macOS releases manually. The UI uses macOS's existing SF Pro fonts and does not redistribute Apple fonts.

## Linux (Ubuntu/Debian)

The first official Linux distribution targets x86_64, Ubuntu 22.04 or later, and Debian 12 or later.

- **`.deb`:** install with `sudo apt install ./baixador-ytdlp-linux-amd64.deb`.
- **Portable:** extract the `.tar.gz`, enter the created folder, and run `./baixador-ytdlp`; data stays in the `data` subfolder.

At first launch, yt-dlp, FFmpeg, and Deno are obtained from official sources under `~/.local/share/BaixadorYtdlp/bin`. Tools already on `PATH` are used only when the corresponding advanced option is enabled. Linux app updates are manual through the release page.

## Performance and privacy

Downloads mainly depend on network speed. Captioning uses CUDA with compatible NVIDIA hardware and CPU/int8 as a fallback. On Apple Silicon, it uses **MLX Whisper** on the integrated GPU; if MLX cannot start, it falls back to CPU/NEON and uses only the performance cores reported by macOS. Video conversion can use NVENC or AMD AMF on Windows and VideoToolbox on macOS when the installed FFmpeg supports them.

The first use of each Whisper model downloads its weights to local app data. The model manager can download them in advance, show progress, and remove them later. Audio and video are never sent to a remote transcription service. A persistent, isolated caption process retains the loaded model for following queue items when compatible.

## Security measures

- HTTPS downloads always validate certificates; there is no insecure TLS fallback.
- yt-dlp, FFmpeg, and Deno are installed only after a valid publisher SHA-256 is available. The verified hash is stored and checked again before future runs.
- Whisper and MLX weights use immutable revisions, never a mutable branch.
- The app installer is validated with SHA-256. `SHA256SUMS.txt` is signed with Ed25519, and the updater accepts a hash only when that signature matches the public key built into the app. Packages also carry GitHub Actions provenance attestations.
- Python dependencies are installed from hash-pinned lock files, including transitive dependencies; a CycloneDX SBOM is generated from each actual build environment.
- On Windows, each subprocess runs in a Job Object. Cancelling or closing the app ends the complete process tree, including yt-dlp, FFmpeg, and Deno.
- The `baixador://` protocol only analyzes a received link; no download starts without confirmation.
- Subprocesses do not use a shell and ignore external yt-dlp configuration.
- Links, proxy data, and cookie paths are redacted before logging. Cookies, history, and settings remain local. Never publish `cookies.txt` or `settings.json`.
- Corporate endpoint policies can block an app that downloads binaries into a user profile.

