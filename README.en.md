# Baixador YT-DLP

[Leia em português](README.md)

Download video and audio, transcribe media locally, and edit files in an Apple + Discord inspired interface for Windows, macOS on Apple Silicon, and Linux.

## Download

| Platform | Recommended package | Download |
| --- | --- | --- |
| Windows 10/11 | Installer, with shortcut and in-app updates | [Download installer](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-setup.exe) |
| Windows 10/11 | Portable ZIP, no installation required | [Download portable edition](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-windows.zip) |
| macOS 14+ on M1/M2/M3/M4 | DMG installer | [Download macOS installer](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.dmg) |
| macOS 14+ on M1/M2/M3/M4 | Portable ZIP | [Download macOS portable edition](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.zip) |
| Ubuntu 22.04+/Debian 12+ x86_64 | `.deb` package | [Download `.deb`](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-linux-amd64.deb) |
| Linux x86_64 | Portable archive | [Download portable edition](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-linux-x86_64.tar.gz) |

The links use stable aliases for the latest approved release. If a version was just published, wait for the **Publish release** GitHub Actions job to finish before downloading it.

## What it does

- Downloads video, audio, playlists, and clips with format and quality choices.
- Previews metadata, estimated output name, formats, audio languages, and available subtitles before starting.
- Queues work, resumes partial downloads, retries temporary errors, and accepts a batch of pasted URLs.
- Creates local captions with faster-whisper in SRT, WebVTT, ASS, karaoke ASS, TXT, or JSON; it can translate speech into English.
- Keeps the transcription process alive between queued media files, reusing an already loaded Whisper model when the model and GPU memory profile are unchanged.
- Can send a completed download to the caption queue and embed the resulting subtitles as a selectable media track without re-encoding.
- Provides local FFmpeg tools for trimming, audio extraction, remuxing, compression, vertical video, and subtitle embedding.
- Offers an optional nightly yt-dlp channel, model manager, diagnostics export with sensitive data redacted, taskbar progress, tray notifications, and optional background operation.
- Uses CUDA with compatible NVIDIA GPUs, MLX on Apple Silicon, and a safe CPU/int8 fallback. Video conversion can use NVENC, AMD AMF, or VideoToolbox when available.

## Interface language

Open **Settings → Appearance → Interface language**, choose **English**, and restart the app. The setting is applied at the next startup so downloads, conversions, and captioning jobs are never interrupted.

## Documentation

- [Usage guide](docs/USAGE-GUIDE.en.md)
- [Platforms, performance, and security](docs/PLATFORMS-AND-SECURITY.en.md)
- [Build and release](docs/BUILD-AND-RELEASE.en.md)
- [Portuguese documentation](README.md#documentação)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## License and responsible use

Baixador YT-DLP uses [yt-dlp](https://github.com/yt-dlp/), [FFmpeg](https://ffmpeg.org/), and their respective licenses. Download only content you have the right to access and use. This repository is licensed under the [MIT License](LICENSE).

