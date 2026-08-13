# Incident: EMS crash-loop — root disk full on bems (2026-08-12)

Discovered while testing the new control-mode query: the lamp said EMS OFFLINE,
starting `bess-ems` didn't fix it, and the investigation found a disk-full outage
that had been latent since boot. Resolved same day.

## Symptom

- `bess-ems` in `activating (auto-restart)`, exit status 1, ~70 ms per attempt,
  restart counter ~955 (crash-looping since VM boot at ~14:50).
- `journalctl -u bess-ems`: only systemd start/stop lines — no app output.
- `ems.log` (the unit's StandardOutput/StandardError target): 0 bytes.
- `bess-api` down the same way (`api.log` also 0 bytes).

## Diagnosis chain

1. Ran `start_ems.sh` by hand (`bash -x`) — EMS starts and runs normally.
2. Replicated the systemd context with
   `systemd-run --wait --pipe -p User=fox -p WorkingDirectory=... start_ems.sh`
   — also runs normally. Same system manager, same user; only remaining
   difference from the real unit: output goes to a pipe, not to a file on disk.
3. Hypothesis: the service dies *because writing to disk fails* — Python's
   first `print()` raises on a full filesystem, the traceback also can't be
   written, process exits 1 having emitted zero bytes. Explains 70 ms + empty log.
4. `df -h /` → 16G disk, 100% used, 0 available. Confirmed.

## Root cause

Root filesystem full. Largest reclaimable weight: snapd (4.3G — old disabled
revisions, download cache, and a full desktop stack on an EMS server), journal
archives (~700M), apt caches. Application logrotate (July setup) was working
fine; app logs were kilobytes.

A subtlety that cost 20 minutes: after the first ~500M was freed, `df` still
showed Avail ≈ 0 — ext4 reserves ~5% (≈800M here) for root, and `Avail` reports
user-writable space. Freed space inside the reserve is invisible to the fox-run
services.

## Fix (all on bems)

- `snap remove` of 7 disabled old revisions, then the desktop snaps
  (firefox, snap-store, snapd-desktop-integration, gnome-42/46 runtimes,
  gtk-common-themes, mesa-2404).
- `snap set system refresh.retain=2` — keep current + one spare, not three.
- `journalctl --vacuum-size=100M` (freed 688M), snapd cache cleared, `apt clean`.
- `systemctl set-default multi-user.target` — bems now boots headless; the
  remaining apt desktop packages are dormant (deliberately NOT purged: on
  Ubuntu desktop installs the network stack ties into NetworkManager, and
  purging the GUI risks severing remote access).
- End state: 11G used / 3.6G available (76%). Both services recovered on
  systemd's automatic retry with no manual restart — Restart=always did its job.

## Prevention / follow-ups

- [ ] Disk usage panel + alert for the lab VMs (bmon/Grafana) — a disk at 95%
      should be a dashboard fact, not a surprise. Good future Grafana lesson.
- [x] snapd retention capped (refresh.retain=2).
- [x] bems headless (multi-user.target).
- [ ] Optional someday: purge dormant desktop packages carefully (~1–2G more).

## Lessons

- A service that works by hand but dies under systemd with *zero output*:
  suspect the output path itself. Reproduce the failing context with
  `systemd-run --pipe` to cut a window into it.
- `systemctl start` returning silently means "start attempted", not "running" —
  always follow with `status`.
- `df` Avail is user-space truth, not disk truth: the root reserve can hide
  freed space.
- Identify before deleting, and state the prediction before running the check.
