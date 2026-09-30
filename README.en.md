<div align="center">

<img src="assets/icon.png" alt="Baixador YT-DLP" width="112" height="112">

# Baixador YT-DLP

**Download, transcribe and edit video and audio — fully local, GPU accelerated.**

A modern interface for [yt-dlp](https://github.com/yt-dlp/yt-dlp) with local Whisper transcription
and video tools. Free, open source, and nothing leaves your computer.

[![Version](https://img.shields.io/github/v/release/NoThinkpls/baixador-ytdlp?display_name=tag&label=version&color=5865F2)](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/NoThinkpls/baixador-ytdlp/total?label=downloads&color=3BA55D)](https://github.com/NoThinkpls/baixador-ytdlp/releases)
[![Build](https://img.shields.io/github/actions/workflow/status/NoThinkpls/baixador-ytdlp/build.yml?branch=main&label=build)](https://github.com/NoThinkpls/baixador-ytdlp/actions)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-0078D4)](#-download)
[![MIT License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

[**Download**](#-download) ·
[Features](#-features) ·
[Usage guide](docs/USAGE-GUIDE.en.md) ·
[Changelog](CHANGELOG.md) ·
[Português](README.md)

<br>

<img src="docs/images/baixar-dark.png" alt="Baixador YT-DLP download page" width="860">

</div>

## ✨ Why use it

- **Genuinely fast.** Parallel fragment downloads; clips from long YouTube videos use the HLS format and are downloaded in parallel parts joined losslessly: ~25× real time on average as measured (30 minutes of a 1080p live stream in ~75 seconds).
- **Everything stays local.** Transcription, conversion and cutting run on your machine. No audio or video is uploaded anywhere.
- **Uses your GPU.** NVIDIA (NVENC and CUDA), AMD (AMF and VAAPI), Intel (Quick Sync) and Apple Silicon (VideoToolbox and MLX), with an automatic CPU fallback if the GPU rejects a file.
- **Secure by default.** yt-dlp, FFmpeg and Deno come from official sources with verified SHA-256; TLS certificate validation is never disabled.
- **Pleasant to use.** Light and dark themes, Portuguese and English, a persistent queue, and unobtrusive notices.

## 📥 Download

| Platform | Recommended package | Download |
| --- | --- | --- |
| Windows 10/11 | Installer, with shortcut and in-app updates | [Download installer](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-setup.exe) |
| Windows 10/11 | Portable ZIP, no installation required | [Download portable edition](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-windows.zip) |
| macOS 14+ on M1/M2/M3/M4 | DMG installer | [Download macOS installer](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.dmg) |
| macOS 14+ on M1/M2/M3/M4 | Portable ZIP | [Download macOS portable edition](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.zip) |
| Ubuntu 22.04+/Debian 12+ x86_64 | `.deb` package | [Download `.deb`](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-linux-amd64.deb) |
| Linux x86_64 | Portable archive | [Download portable edition](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-linux-x86_64.tar.gz) |

> The links use stable aliases for the latest approved release. If a version was just published, wait for the **Publish release** GitHub Actions job to finish.

**First launch:** the app downloads yt-dlp, FFmpeg and Deno from their official sources. After that each component is downloaded again only when a newer version exists (FFmpeg, for example, only when a newer stable branch is released).

## 🚀 Features

### Downloading

- Video, audio, playlists and **clips** with format and quality choices. Clips are not re-encoded (long ones are split into parallel parts); the start may shift to the nearest keyframe.
- Metadata preview with thumbnail, estimated file name, sizes, codecs, audio languages and available subtitles.
- Batch URLs, one-click sending from the browser through the `baixador://` protocol, and playlist item picking.
- Persistent queue with **pause and resume**, partial-file resume and automatic retries.
- Cover, metadata and chapters also for audio; optional music organisation by channel/artist.
- Optional nightly yt-dlp channel for site fixes ahead of the stable release.
- Beyond YouTube: Instagram, X, TikTok, Facebook, Reddit, Vimeo, Twitch, SoundCloud and other sites yt-dlp supports, with error notices that name the right site. Instagram stories and restricted content need a login: the warning appears immediately, and a single `cookies.txt` (or Firefox) covers every site; importing one after another keeps both.

### Captions and transcription

- Local Whisper up to **Large v3 Turbo**, translation to English and context vocabulary.
- SRT, VTT, ASS, karaoke ASS, TXT and JSON output, for several files and folders at once.
- **Download and caption** flow: when a download finishes, the file joins the Whisper queue and can get the subtitles as a track, without re-encoding.
- CUDA on NVIDIA GPUs, **MLX** on Apple Silicon, optimised CPU elsewhere.

<div align="center">
<img src="docs/images/legendar-dark.png" alt="Captions page" width="720">
</div>

### Video tools

- 16 tools in five groups: trim, **change speed**, rotate/flip and vertical video (Shorts/Reels); extract audio (MP3, M4A, Opus, FLAC, WAV), **normalize volume** and remove audio; **convert to MP4 or WebM**, remux without loss, shrink and **fit under a size limit** (Discord, WhatsApp, email); **make GIFs** and **capture a frame**; add and **extract subtitles** and **strip metadata** (GPS, title, camera).
- Conversion through **NVENC, AMF or VideoToolbox** when available, falling back to the CPU if the GPU fails. The original file is never modified.

<div align="center">
<img src="docs/images/ferramentas-light.png" alt="Tools page (light theme)" width="720">
</div>

### Interface

- Light and dark themes, **Portuguese and English** (Settings → Appearance), compact sidebar and custom icons.
- Windows taskbar progress, tray notifications and optional background operation.
- In-app updates on Windows, verified by SHA-256 (and Ed25519 signature on signed releases) before installing.

<div align="center">
<img src="docs/images/configuracoes-dark.png" alt="Settings" width="720">
</div>

## ⚙️ Acceleration by platform

| | Windows | macOS (Apple Silicon) | Linux |
| --- | --- | --- | --- |
| Conversion and cuts | NVIDIA NVENC · AMD AMF · Intel Quick Sync | VideoToolbox | NVENC · Intel Quick Sync · VAAPI (AMD/Intel) |
| Transcription | NVIDIA CUDA · CPU | MLX on GPU · CPU | CPU/int8 |

Planned next (Intel QSV, VAAPI, hardware decoding, parallel cuts): [`docs/PLANO-OTIMIZACAO-PLATAFORMAS.md`](docs/PLANO-OTIMIZACAO-PLATAFORMAS.md) (Portuguese).

## 🔒 Privacy and security

- Nothing is sent to third-party services beyond requests to the source site, GitHub releases and the official component sources.
- Components are installed only when the vendor publishes a valid SHA-256, which is checked again before each run.
- Cookies, history and settings stay local and are stripped from exported diagnostics, along with proxy passwords and URL tokens.
- Cancelling or closing the app ends the whole process tree (yt-dlp, FFmpeg, Deno).
- See [Platforms, performance and security](docs/PLATFORMS-AND-SECURITY.en.md) and the [security policy](SECURITY.md).

## 📚 Documentation

| | |
| --- | --- |
| [Usage guide](docs/USAGE-GUIDE.en.md) | From the first download to tools and captions |
| [Platforms and security](docs/PLATFORMS-AND-SECURITY.en.md) | Performance, GPU and security model |
| [Build and release](docs/BUILD-AND-RELEASE.en.md) | Nuitka build, CI and publishing |
| [Changelog](CHANGELOG.md) | Version history |
| [Contributing](CONTRIBUTING.md) | Environment, tests and conventions |
| [Portuguese documentation](README.md#-documentação) | Full documentation set |

## 🛠️ Development

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-windows.lock   # or requirements-macos/linux
python main.py                                            # run the app
python -m unittest discover -s tests                      # tests (QT_QPA_PLATFORM=offscreen)
ruff check .
```

On Windows, `.\build.ps1` builds the executable with Nuitka (`-Installer` creates the installer). See [Build and release](docs/BUILD-AND-RELEASE.en.md).

## ⚖️ License and responsible use

Baixador YT-DLP uses [yt-dlp](https://github.com/yt-dlp/) and [FFmpeg](https://ffmpeg.org/) under their respective licenses. Download only content you have the right to access and use. This repository is licensed under the [MIT License](LICENSE).
