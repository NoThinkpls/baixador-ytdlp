# AI plan for Clips

On the **Clips** page, the **AI plan** field takes one line of text that tells the app
which clips to make, with which title, and where to put sounds and zoom. The idea is to
split the work: a text AI (ChatGPT, Claude, Gemini or another) reads the whole
transcript and understands the context; Baixador only executes it, down to the word.

You don't need any specific prompt. Just ask your AI to end its answer with the line in
the format below.

## How to use it

1. Transcribe the whole video on the **Captions** tab and export the `.srt`.
2. Send the `.srt` to your AI along with the plan request (ready-made text below).
3. Copy the line that starts with `{"bx":1` (or the whole answer).
4. On **Clips**, choose the video, paste the line into **AI plan** and click **Apply
   plan**. With the field empty, the button reads the clipboard, so you can copy the
   AI's whole answer and just click.

The clip list is replaced by the plan's. Each clip with effects shows a `✦` with the
number of points; hover to see them. **Sound effects** and **Zoom on emphasis** are
turned on automatically when the plan has sounds or zoom. You can still edit start, end
and title by hand before creating the clips.

## Format

A single, deliberately compact line of JSON:

```
{"bx":1,"t":"f","l":"PS. JOHN · SUNDAY SERVICE","c":[["12:03","12:58","\"GOD HAS NOT FORGOTTEN YOU\"",[["12:10","grace","i",1],["12:31","","w",0]]]]}
```

- `bx`: always `1` (it is how the app finds the plan inside other text).
- `t` (optional): the title type for every clip. `"f"` = **fixed title on top** (a dark
  band with the title on a card from start to end, video below); `"a"` = **animated
  title** (pops in and disappears after a few seconds). Without `t`, the page's choice
  stays.
- `l` (optional): the small line above the fixed title, the same for every clip
  (speaker, podcast, series or episode name), up to 80 characters. Without `l`, the
  page's line stays.
- `c`: the list of clips. Each clip is `[start, end, title, effects]`.
  - **start** and **end**: times in the original video, the same as in the `.srt`, as
    `mm:ss`, `hh:mm:ss`, with tenths (`12:03.5` or `12:03,5`) or in seconds (`723.5`).
    Each clip must be 1 second to 10 minutes long; 20 clips at most.
  - **title**: the clip's title (may be `""`). With an animated title, keep it short
    (2 to 4 words, up to 20 characters) so it fits one line. A fixed title fits more: up
    to 3 lines on the card (3 to 8 words, about 45 characters); the font shrinks by
    itself when it is long, and a striking quote in quotation marks (`\"…\"` inside the
    JSON) works well in this format.
  - **effects**: a list of points (may be `[]`). Each point is
    `[time, word, sound, zoom]`:
    - **time**: when it happens, in `.srt` time;
    - **word**: the word (or short phrase) being said at that moment, as it appears in
      the transcript. Optional, but it is what makes it precise: the `.srt` only has
      the sentence time, so the app looks for this word up to 6 seconds around it and
      uses the exact moment it is spoken;
    - **sound**: one letter, or `""` for zoom only:

      | Letter | Sound | When to use it |
      | --- | --- | --- |
      | `w` | whoosh | change of topic or idea |
      | `p` | pop | highlight a word or a number |
      | `i` | impact | strong sentence, climax, reveal |
      | `d` | ding | key idea, conclusion, "aha" |
      | `s` | riser | building tension; the sound ends on the point |

      The full names (`whoosh`, `pop`, `impacto`, `ding`, `subida`) also work.
    - **zoom**: `1` for a quick punch-in at that point, `0` for none.

What the app does with each point:

- converts the time to the final video, after the removed pauses;
- a **whoosh** near a cut (within 1.5 s) moves to the cut, with its peak right on it;
  with no cut nearby the whoosh is dropped (there would be no transition on screen);
- the **riser** ends exactly on the point; the other sounds start on it;
- every sound other than the whoosh gets the quick punch-in at that point, so something
  happens on screen with it; with **Zoom on emphasis** off, only the whoosh remains;
- two sounds stay at least 3 s apart (a riser ending on an impact counts as one effect);
  anything closer is dropped;
- each sound's volume is measured and set a few dB below the clip's voice;
- points outside their own clip, unreadable times and unknown sounds are ignored (an
  unknown sound with `zoom` 1 becomes zoom only); the rest of the plan still applies.

Without a plan, the app uses a simple audio rule (a whoosh on long pauses that were cut
and a pop on words said much louder).

## Ready-made text for your AI

Add it to the end of your AI's instructions (or your request) without changing the rest:

```
At the very end of your answer, after everything else, output a single line of compact
JSON, with no line breaks and no comments, in this format:
{"bx":1,"t":"f","l":"TOP LINE","c":[["START","END","TITLE",[["TIME","WORD","SOUND",ZOOM]]]]}
- "t" is the title type: "f" (fixed on top, on a card, the whole clip) or "a" (animated,
  shows at the start and disappears). Use "f" unless I ask for an animated title.
- "l" is a short line above the fixed title, the same for every clip (speaker and show,
  series or episode name, up to 40 characters). If you don't know it, leave "l" out.
- One item in "c" per suggested clip (20 at most), with START and END taken from the SRT
  (mm:ss or hh:mm:ss) and the clip's title: with "f", 3 to 8 words and up to 45
  characters (a strong quote from the speaker may go in quotation marks, written as \");
  with "a", 2 to 4 words and up to 20 characters.
- In each clip, 1 to 3 effects, only where they reinforce the speech: TIME from the SRT;
  WORD exactly as spoken at that moment; SOUND = w (topic change), p (word highlight),
  i (strong sentence or climax), d (key idea), s (tension that ends on the point) or ""
  (no sound); ZOOM = 1 to punch in at that point, 0 for none.
- Leave at least 4 seconds between two sounds and do not put effects in the first
  2 seconds of a clip. Use w only on a pause or topic change. Prefer a few well-placed
  effects over many.
```

## Your own sounds

The five default sounds are generated by the app itself. To use others (from a library
you have the rights to use), create a folder with files named `whoosh`, `pop`,
`impacto`, `ding` and `subida` (WAV, MP3, OGG, M4A, FLAC, AAC or Opus) and pick it under
**Clips → Pacing and effects → Your sounds (optional)**, which shows up when **Sound effects** is on. Anything missing from the folder keeps the default
sound.
