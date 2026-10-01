"use strict";

// O HTML já vem em português (funciona sem JavaScript); aqui ficam só as traduções para inglês.
const EN = {
  skip: "Skip to content", nav: "Sections", theme: "Toggle light/dark theme",
  nav_features: "Features", nav_shots: "Screenshots", nav_download: "Download", nav_privacy: "Privacy",
  eyebrow: "Open source · MIT license",
  h1: "Download, transcribe and edit videos and audio.",
  lead: "A modern interface for yt-dlp, with Whisper transcription and video tools. Everything runs on your computer, GPU-accelerated, and nothing is sent to the cloud.",
  cta_download: "Download the app", cta_github: "View on GitHub",
  meta: "Windows 10/11 · macOS (Apple Silicon) · Linux x86_64 · Free",
  alt_hero_dark: "The Download page of Baixador YT-DLP in the dark theme",
  alt_hero_light: "The Tools page of Baixador YT-DLP in the light theme",
  l_features: "Why use it", h_features: "Fast, local and secure by default",
  s_features: "Built for people who download and process a lot of media and don't want to depend on outside services.",
  f1_t: "Genuinely fast", f1_p: "Parallel fragments, and clips from long videos downloaded in parallel parts joined without re-encoding: a 30-minute 1080p live stream in about 75 s.",
  f2_t: "All on your computer", f2_p: "Transcription, conversion and clipping run locally. No audio or video leaves your machine.",
  f3_t: "Uses your GPU", f3_p: "NVIDIA (NVENC and CUDA), AMD (AMF and VAAPI), Intel (Quick Sync) and Apple Silicon (VideoToolbox and MLX), with automatic fallback to the CPU.",
  f4_t: "Secure by default", f4_p: "yt-dlp, FFmpeg and Deno come from official sources with a verified SHA-256, and TLS certificate validation is never turned off.",
  f5_t: "Beyond YouTube", f5_p: "Instagram, X, TikTok, Facebook, Reddit, Vimeo, Twitch, SoundCloud and every other site yt-dlp covers.",
  f6_t: "Pleasant to use", f6_p: "Light and dark themes, Portuguese and English, a persistent queue with pause and resume, and unobtrusive notices.",
  l_does: "What it does", h_does: "Three areas, one app", s_does: "From link to finished file, without switching programs.",
  c1_t: "Download",
  c1_1: "Video, audio, playlists and clips, with quality and format choice",
  c1_2: "Preview with thumbnail, sizes, codecs, languages and subtitles",
  c1_3: "Many links at once and a persistent queue with resume",
  c1_4: "Cover art, metadata and chapters for audio too",
  c2_t: "Subtitles and transcription",
  c2_1: "Local Whisper up to Large v3 Turbo, with translation to English",
  c2_2: "SRT, VTT, ASS, karaoke, TXT and JSON outputs",
  c2_3: "Download and subtitle flow: the file joins the Whisper queue when it finishes",
  c2_4: "CUDA, MLX on Apple Silicon or optimized CPU",
  c3_t: "Video tools",
  c3_1: "16 tools: clip, speed, rotate, vertical version",
  c3_2: "Extract audio, normalize volume and remove audio",
  c3_3: "Convert to MP4 or WebM, shrink, and fit a size limit (Discord, WhatsApp, email)",
  c3_4: "The original file is never changed",
  l_shots: "Screenshots", h_shots: "See the app from the inside", shots_aria: "Screenshots",
  t_download: "Download", t_subs: "Subtitles", t_tools: "Tools", t_settings: "Settings",
  alt_s1: "Download page: link field, format, audio only, subtitle when done and clip",
  alt_s2: "Subtitles page, with local Whisper transcription",
  alt_s3: "Tools page in the light theme, with the video and audio tasks",
  alt_s4: "App settings page",
  l_download: "Download", h_download: "Choose your system",
  s_download: "The links always point to the latest published version.",
  rec: "Recommended", get: "Download",
  req_win: "Windows 10 or 11", req_mac: "Mac with Apple Silicon (M1, M2, M3 or M4)", req_linux: "Ubuntu 22.04+ or Debian 12+ (x86_64)",
  inst: "Installer", inst_win: "Shortcut and in-app updates", port: "Portable", port_desc: "No install, everything in the extracted folder",
  dmg: "Open and drag to Applications", port_mac: "Unzip and open the app", deb: "System-integrated install",
  port_linux: "Linux x86_64, everything in the extracted folder",
  note_sign: "<strong>Heads up:</strong> the distributed files are not yet code-signed. Windows, macOS or antivirus tools may show an unrecognized app warning. The official files are the ones published in this project's Releases section.",
  note_first: "<strong>First launch:</strong> the app downloads yt-dlp, FFmpeg and Deno from their official sources and only downloads them again when a newer version exists.",
  l_privacy: "Privacy and security", h_privacy: "Your files stay with you",
  p1_t: "No cloud", p1_p: "Nothing is sent to outside services beyond requests to the source site, GitHub releases and the components' official sources.",
  p2_t: "Verified components", p2_p: "They are only installed when the vendor publishes a valid SHA-256, and the hash is checked before every run.",
  p3_t: "Local data", p3_p: "Cookies, history and settings stay on your machine and are stripped from the exported diagnostics.",
  p4_t: "Nothing left behind", p4_p: "Canceling or closing the app ends the whole process tree (yt-dlp, FFmpeg, Deno).",
  footer_nav: "Project links", ft_guide: "User guide", ft_issues: "Report a problem", ft_sec: "Security", ft_license: "MIT license",
  ft_note: "Static site, no trackers or cookies.",
  cta_win: "Download for Windows", cta_mac: "Download for macOS", cta_linux: "Download for Linux",
};
const PT_CTA = { windows: "Baixar para Windows", mac: "Baixar para macOS", linux: "Baixar para Linux" };
const EN_CTA = { windows: EN.cta_win, mac: EN.cta_mac, linux: EN.cta_linux };

const root = document.documentElement;
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } },
};

// ------------------------------------------------------------------ idioma
let lang = "pt";
let detectedOs = null;

function applyLang(next) {
  lang = next;
  root.lang = lang === "en" ? "en" : "pt-BR";
  const dict = lang === "en" ? EN : null;
  for (const el of $$("[data-i18n]")) {
    if (el.dataset.pt === undefined) el.dataset.pt = el.innerHTML;
    el.innerHTML = dict && dict[el.dataset.i18n] !== undefined ? dict[el.dataset.i18n] : el.dataset.pt;
  }
  for (const attr of ["alt", "aria"]) {
    for (const el of $$(`[data-i18n-${attr}]`)) {
      const name = attr === "aria" ? "aria-label" : "alt";
      const key = el.getAttribute(`data-i18n-${attr}`);
      if (el.dataset[`pt${attr}`] === undefined) el.dataset[`pt${attr}`] = el.getAttribute(name) || "";
      el.setAttribute(name, dict && dict[key] !== undefined ? dict[key] : el.dataset[`pt${attr}`]);
    }
  }
  const btn = $("#lang");
  btn.textContent = lang === "en" ? "PT" : "EN";
  btn.setAttribute("aria-label", lang === "en" ? "Mudar para português" : "Switch to English");
  btn.title = lang === "en" ? "Português" : "English";
  store.set("lang", lang);
  updateCta();
}

function updateCta() {
  const label = $("#cta-label");
  if (detectedOs) label.textContent = (lang === "en" ? EN_CTA : PT_CTA)[detectedOs];
  else label.textContent = lang === "en" ? EN.cta_download : label.dataset.pt || "Baixar o app";
}

$("#lang").addEventListener("click", () => applyLang(lang === "en" ? "pt" : "en"));

// -------------------------------------------------------------------- tema
$("#theme").addEventListener("click", () => {
  const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  store.set("theme", next);
});

// ------------------------------------------------------------------- abas
const tabs = $$('[role="tab"]');
function selectTab(tab, focus) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    $("#" + t.getAttribute("aria-controls")).hidden = !on;
  }
  if (focus) tab.focus();
}
for (const [i, tab] of tabs.entries()) {
  tab.addEventListener("click", () => selectTab(tab, false));
  tab.addEventListener("keydown", (ev) => {
    const move = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
    if (move) { ev.preventDefault(); selectTab(tabs[(i + move + tabs.length) % tabs.length], true); }
    if (ev.key === "Home") { ev.preventDefault(); selectTab(tabs[0], true); }
    if (ev.key === "End") { ev.preventDefault(); selectTab(tabs[tabs.length - 1], true); }
  });
}

// ------------------------------------------------- sistema do visitante
function detectOs() {
  const ua = navigator.userAgent || "";
  if (/Android|iPhone|iPad|iPod|CrOS/i.test(ua)) return null; // o app é só para desktop
  const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  const hint = `${platform} ${ua}`;
  if (/Win/i.test(hint)) return "windows";
  if (/Mac/i.test(hint)) return "mac";
  if (/Linux|X11/i.test(hint)) return "linux";
  return null;
}

detectedOs = detectOs();
if (detectedOs) {
  const card = $(`.os[data-os="${detectedOs}"]`);
  card.classList.add("recommended");
  $(".badge", card).hidden = false;
  $("#cta-main").href = $(".btn.primary", card).href;
}

// ------------------------------------------------ versão e tamanhos (API)
function formatSize(bytes) {
  const gb = bytes / 1e9;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

function applyRelease(release) {
  if (!release || !release.tag_name) return;
  const version = $("#version");
  version.textContent = release.tag_name.replace(/^v/, "");
  version.hidden = false;
  const sizes = new Map((release.assets || []).map((a) => [a.name, a.size]));
  for (const el of $$("[data-size]")) {
    const size = sizes.get(el.dataset.size);
    if (size) el.textContent = `· ${formatSize(size)}`;
  }
}

async function loadRelease() {
  const key = "release-cache";
  try {
    const cached = JSON.parse(sessionStorage.getItem(key) || "null");
    if (cached) return applyRelease(cached);
  } catch (e) { /* cache indisponível */ }
  try {
    const res = await fetch("https://api.github.com/repos/NoThinkpls/baixador-ytdlp/releases/latest", {
      headers: { Accept: "application/vnd.github+json" },
    });
    if (!res.ok) return;
    const data = await res.json();
    const slim = { tag_name: data.tag_name, assets: (data.assets || []).map((a) => ({ name: a.name, size: a.size })) };
    try { sessionStorage.setItem(key, JSON.stringify(slim)); } catch (e) { /* ok */ }
    applyRelease(slim);
  } catch (e) { /* offline ou limite da API: a página funciona sem versão e sem tamanhos */ }
}

// ------------------------------------------------------------------ início
const saved = store.get("lang");
const initial = saved === "en" || saved === "pt" ? saved : (navigator.language || "pt").toLowerCase().startsWith("pt") ? "pt" : "en";
$("#cta-label").dataset.pt = $("#cta-label").textContent;
applyLang(initial);
loadRelease();
