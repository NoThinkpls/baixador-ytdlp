# Usage guide

[Leia em português](GUIA-DE-USO.md)

## Download media

Paste a link, analyze the available qualities, then choose video, audio, or a clip. The app uses the best available quality by default and lets you select the container, resolution, codec, and destination folder.

The queue can process more than one item, cancel or retry failed work, and show speed, progress, and estimated finish time. Temporary network failures are retried automatically. If the app closes, its queue and partial files resume on the next launch. You can also import a URL list and save output profiles.

Analysis shows a thumbnail, estimated final name, video/audio combinations, approximate size, audio languages, and manual or automatic subtitles published by the source. For audio downloads, cover art, metadata, and chapters are controlled in **Extra content**; audio can also be organized by channel or artist.

Turn on **Create captions when finished** to send every completed file to the Whisper queue. For video, **Embed captions as a track** also makes a captioned copy without re-encoding the image. Downloads continue while captioning runs.

## Content that requires sign-in

For private or age-restricted videos, or whenever YouTube requests access confirmation, use a Netscape-format `cookies.txt` file in **Settings**. Do not share that file: it can grant access to your account.

The app installs Deno automatically when the YouTube JavaScript challenge requires it. Cookies do not replace that requirement.

## Transcription and captions

Drag a video or audio file into the caption page, choose a language, task, and model, and export SRT, WebVTT, ASS, karaoke ASS, TXT, or JSON. Speech can be translated into English. You can provide names or technical terms as context and adjust caption width and duration. Large v3 Turbo prioritizes speed and accuracy but does not support translation.

Use **Manage models** to download weights in advance, monitor progress, review space use, or remove a model. Compatible NVIDIA hardware uses CUDA; other machines use CPU automatically. Apple Silicon uses MLX.

The caption worker is persistent: the protected background process stays open between consecutive queue items and reuses the loaded model. Changing the Whisper model or the GPU memory-saving option reloads only the required model.

## Send a browser link

The installer registers the `baixador://` protocol. Create a bookmark with the address below; clicking it on a video page opens the app and **analyzes** the link. Download only begins after confirmation.

```text
javascript:location.href='baixador://baixar?url='+encodeURIComponent(location.href)
```

Linux registers the protocol through the `.deb` package; macOS registers it through the `.app` bundle.

## Playlists

After analyzing a playlist, use **Choose items** to select only the videos you want; title search is available. The selection becomes yt-dlp's `--playlist-items` option. The selected quality limit, such as 1080p, applies to every item.

## Media tools

The **Tools** page works locally with FFmpeg: trim, extract MP3, remux without recompression, compress, fit a file below a size limit for Discord/WhatsApp/email, create vertical video with a blurred background, and embed captions. Progress is shown in the app and, where supported, on the taskbar. No media is uploaded for these operations.

## Vertical clips

The **Clips** page turns parts of a video into vertical videos for Shorts, Reels and TikTok. Pick a file or paste a YouTube link (only the ranges are downloaded), enter the start and end of each clip (`mm:ss` or `hh:mm:ss`) with an optional title, pick the framing and the title type on the thumbnail cards in **Clip look**, set up the caption and click **Create clips**. The preview on the left shows the clip as it will come out (over a frame of the video for a local file) and follows the page as you scroll. Each clip is saved as `Title - name - corte01.mp4` (title first, so it is easy to find in the folder; without a title, `name - corte01.mp4`); finished clips are kept even if you cancel or a later clip fails.

- **Follow the person** zooms in and follows whoever is on screen, like CapCut's auto reframe: the app looks for faces a few frames per second and, when there is none, follows the motion. The camera only moves when the person leaves the center, and it moves slowly, without jitter. With several people, it follows whoever is speaking (the app looks at each mouth together with the sound); when nobody speaks and people are spread out, it shows the whole frame over a blurred background. **Blurred background** shows the whole frame; **Center crop** fills the screen with the middle of the video.
- In **Title**, choose **Animated title** (pops in and disappears after 2, 3 or 5 seconds, or stays the whole clip; its height is adjustable) or **Fixed title on top**: a dark band at the top with the title on a card in the highlight color for the whole clip, with the video (following the person, blurred background or center crop) below. The optional **Top line** shows in smaller letters on the card, such as the podcast, guest or episode name. Long titles shrink to fit the card in up to 3 lines. The preview shows the first clip's title.
- In **Caption**, choose the animation (highlight, color only, karaoke, one word at a time, group pops in or no highlight), the font, size, text color, spoken-word color, height (as % of the screen), words per caption (1 to 4), casing and a dark box behind the text. The preview shows the result over a frame of the video; drag the caption or the title in it to move them up or down (the title height also has its own field). Your choices are saved for the next clips.
- In **Pacing and effects**, turn pause removal (with the minimum pause) on or off and optionally zoom on cuts, sound effects (whoosh, pop, impact, ding and riser, optionally from a folder with your own sounds; the whoosh goes on cuts and the other sounds only together with zoom on emphasis), and zoom on emphasis. **Output and transcription** holds the progress bar, balanced volume, a `.srt` copy of the caption, the spoken language and the Whisper model.
- To let a text AI pick the clips, titles and where each sound goes, paste its plan line into **AI plan**, right below the clip list. Format and ready-made text for any AI in [AI-PLAN.en.md](AI-PLAN.en.md).
- Every finished clip shows up in **History**, with buttons to open the file, show it in the folder, caption it and make more clips from the same video. Results from the **Tools** tab and videos with embedded captions go to History too.

## Tray and background work

In **Settings**, choose whether completions show system notifications. Closing to the tray keeps active work running; use **Exit** from the tray icon menu to close the app completely.

## Updates and diagnostics

In **Settings → New app version**, you can disable update checks at startup or check manually. On Windows, a lower banner offers the update or lets you dismiss it. The installer is verified using SHA-256 before opening. The check also compares the app's own executable with the hash published in the release: if the version is the same but the file does not match (corrupted or modified), the banner offers to **Reinstall** the official version.

If a site stops working, switch the yt-dlp channel to *Nightly* in **Settings**. To report a problem, export diagnostics from **Settings → Diagnostics**. The ZIP excludes cookies, proxy passwords, URL tokens, and your user-folder name.

## Data locations

On Windows, settings, history, the queue, models, and dependencies are stored in `%LOCALAPPDATA%\BaixadorYtdlp`. On macOS they are in `~/Library/Application Support/BaixadorYtdlp`. On Linux they are in `~/.local/share/BaixadorYtdlp` or the directory selected by `XDG_DATA_HOME`. The download folder is configurable.

