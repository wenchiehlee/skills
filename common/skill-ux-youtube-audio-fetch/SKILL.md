---
name: skill-ux-youtube-audio-fetch
description: >-
  UX styling, player components, and tactile media controls for YoutubeAudio.Fetch (GitHub Pages web player & extractor).
  Use this skill when developing or improving the audio player interface, download progress visualizers,
  track queues, and dark atmospheric media aesthetics for YoutubeAudio.Fetch.
---

# UX Skill: YoutubeAudio.Fetch (Atmospheric Media Dark)

This skill provides UI components, visual styling, and tactile media controls for **YoutubeAudio.Fetch**, delivering a modern, high-fidelity music & podcast listening and downloading experience.

## UX Identity & Design System

1. **Obsidian Media Shell**: Ultra-deep background (`#0f0f13`) with subtle card elevations (`#18181f`) to make album artwork and visualizers pop.
2. **Neon Soundwave Accents**: Electric violet (`#8b5cf6`) combined with soundwave cyan (`#06b6d4`) for playheads, active states, and frequency ripples.
3. **Tactile Playback Controls**: Responsive audio scrubbers, smooth volume dials, and distinct hover/active tactile feedback.
4. **Download & Transcoding Feedback**: Multi-stage progress indicators (Fetching metadata &rarr; Downloading stream &rarr; Extracting audio &rarr; Ready).
5. **Animal Mascot (聲波座頭鯨 Soundwave Singing Whale 🐋)**:
   - **Symbol**: `#icon-whale-sonic` (from [animal-icons.svg](../../tokens/icons/animal-icons.svg)).
   - **Purpose**: Represents deep acoustic resonance, oceanic immersive listening, and rich audio spectrum harmonics.
   - **Application**: Placed on player dock quality badge, audio stream visualizer, and download completion indicator.

---

## Key Components

### 1. Sticky Floating Player Bar
Stays docked at the bottom of the screen with album art, track title, scrubber bar, play/pause toggle, volume slider, and queue button.

### 2. Audio Track & Download Card
Displays track thumbnail, title, channel name, audio quality badge (`320 kbps MP3` / `Opus`), and a download action button with a built-in circular or linear progress bar.

### 3. Usage & Assets
- CSS Theme: [media-player-theme.css](./resources/media-player-theme.css)
- Mockup Markup: [player-interface.html](./examples/player-interface.html)
