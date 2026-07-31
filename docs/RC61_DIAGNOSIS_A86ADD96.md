# Project Lumen RC6.1 diagnosis A86ADD96

The installed app still reports `13.2.0-rc6-playback-persistence-ux` and the new session contains no `ROW-ACTIVATE`, `PLAYER-INTENT-START`, or `PLAYER-INTENT-SENT` events. The prior hotfix APK used the same version code and label as RC6, so the installed build could not be distinguished reliably from the previous package. RC6.1 raises the version code and visible version, keeps the row activation repair, and moves diagnostic file writes off the main thread to eliminate the observed `libcore.io.Linux.writeBytes` UI stall.
