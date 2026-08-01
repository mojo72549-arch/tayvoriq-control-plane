# Project Lumen RC6.2 – Clean Picture-in-Picture

Basis: RC6.1 row activation and persistence recovery.

Observed on Samsung SM-G980F / Android 13:
- Video and audio continue correctly in Picture-in-Picture.
- The in-player title, audio selector and status text remain visible inside the small PiP window and cover the video.

Required behavior:
- Before entering PiP, hide all Project Lumen overlays and the Media3 controller.
- PiP must show only the stream image.
- Native Android PiP controls remain available when the user taps the window, including close and pause/stop behavior.
- Restore the full Project Lumen player UI when returning from PiP.
- Keep Fire TV behavior unchanged.

Target version: 13.2.0-rc6.2-clean-pip / versionCode 1320620 / label Project Lumen RC6.2.
