<p align="center">
  <img src="assets/icon.png" width="96" alt="Baixador YT-DLP icon">
</p>

<h1 align="center">Baixador YT-DLP</h1>

<p align="center">
  Download media, transcribe audio locally, and edit video files in one desktop app for Windows, macOS on Apple Silicon, and Linux.
</p>

<p align="center">
  <a href="README.md">Leia em português</a> ·
  <a href="https://github.com/NoThinkpls/baixador-ytdlp/releases/latest">Get the latest release</a> ·
  <a href="docs/README.md">Documentation</a>
</p>

<p align="center">
  <a href="https://github.com/NoThinkpls/baixador-ytdlp/releases/latest"><img src="https://img.shields.io/github/v/release/NoThinkpls/baixador-ytdlp?display_name=tag&label=release" alt="Latest release"></a>
  <a href="https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/build.yml"><img src="https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/build.yml/badge.svg?branch=main" alt="Build"></a>
  <a href="https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/security.yml"><img src="https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/security.yml/badge.svg?branch=main" alt="Security"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ea44f" alt="MIT License"></a>
</p>

## Download for your platform

| Platform | Recommended option | Download |
| --- | --- | --- |
| Windows 10/11 | Installer with shortcut and in-app updates | [Download installer](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-setup.exe) |
| Windows 10/11 | Run without installing | [Portable edition](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-windows.zip) |
| macOS on M1/M2/M3/M4 | Drag the DMG app to Applications | [Download for macOS](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.dmg) |
| macOS on M1/M2/M3/M4 | Run without installing | [Portable edition](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.zip) |
| Ubuntu 22.04+/Debian 12+ x86_64 | System-integrated package | [Download `.deb`](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-linux-amd64.deb) |
| Linux x86_64 | Run without installing | [Portable edition](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-linux-x86_64.tar.gz) |

These links use stable aliases for the latest approved release. Verify the SHA-256 checksums shipped with the installers when you need integrity proof.

## What you can do

- **Download with control.** Videos, audio, playlists, and clips, with a preview of formats, languages, estimated size, and final filename.
- **Transcribe on your computer.** SRT, VTT, ASS, karaoke, TXT, and JSON captions with Whisper, including optional English translation and context.
- **Edit without leaving the app.** Trim, extract audio, fit a size limit, make vertical video, remux, and embed subtitles with real progress.
- **Use the available hardware.** CUDA for NVIDIA, MLX on Apple Silicon, NVENC/AMF/VideoToolbox when supported, and a safe CPU fallback.
- **Work through a queue.** Paste many links, resume partial downloads, retry transient failures, and keep tasks working in the background.
- **Keep data under your control.** Diagnostics redact sensitive data; cookies are not sent by the app and transcription runs locally.

## Quick start

1. Download the recommended package for your platform and open the app.
2. Paste a link, inspect the available options, and choose a format and folder.
3. To create captions, open **Transcription**, choose a model, and add media to the queue. The first use of a model may download it to your user profile.

See the [usage guide](docs/USAGE-GUIDE.en.md) for playlists, sign-in-required sites, the `baixador://` protocol, media tools, and troubleshooting.

## Platforms and security

| System | Architecture | Transcription | Video acceleration |
| --- | --- | --- | --- |
| Windows 10/11 | x86_64 | NVIDIA CUDA or CPU/int8 | NVENC and AMD AMF |
| macOS 14+ | Apple Silicon | MLX or CPU | VideoToolbox |
| Ubuntu/Debian | x86_64 | CPU/int8 | Depends on the available FFmpeg |

Official releases are built and checked on all three systems before publication. They include SHA-256 checksums, dependency inventories (SBOM), and provenance attestation. Details are in [Platforms and security](docs/PLATFORMS-AND-SECURITY.en.md).

## Documentation

- [Documentation hub](docs/README.md)
- [Usage guide](docs/USAGE-GUIDE.en.md) · [Guia de uso](docs/GUIA-DE-USO.md)
- [Platforms and security](docs/PLATFORMS-AND-SECURITY.en.md) · [Plataformas e segurança](docs/PLATAFORMAS-E-SEGURANCA.md)
- [Build and releases](docs/BUILD-AND-RELEASE.en.md) · [Build e releases](docs/COMPILACAO-E-RELEASE.md)
- [Changelog](CHANGELOG.md)

## Community and development

Found a problem? Open an [issue](https://github.com/NoThinkpls/baixador-ytdlp/issues/new/choose) without including cookies, tokens, or private links. To contribute, read the [contribution guide](CONTRIBUTING.md) and [security policy](SECURITY.md).

## License and responsible use

The code is released under the [MIT License](LICENSE). The app uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [FFmpeg](https://ffmpeg.org/); their licenses and notices are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Download only content that you have the right to access and use.
