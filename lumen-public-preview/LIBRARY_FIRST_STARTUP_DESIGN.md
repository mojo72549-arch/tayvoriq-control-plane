# Project Lumen – Library-first startup

After a successful import, the normal product state is the library, not source setup or diagnostics.

Rules:
- a valid local library is restored automatically on every launch
- the last content area is remembered; default is Live-TV
- settings, source setup and diagnostics never become the next-launch destination
- while local restore runs, the UI shows a neutral loading state without making Systemstatus the primary action
- after restore, the app enters the remembered content area automatically
- after a successful first import, the app opens the library automatically; success details remain available under Systemstatus
- diagnostics become primary only when restore has actually failed or timed out
- the crash-safe active/previous generation design remains authoritative
