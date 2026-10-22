# M2 self-hosted GitHub runner connectivity watchdog — source

This source file is the tested, portable copy of the existing **single**
user-scoped M2 Studio watchdog, installed at:

    ~/.local/share/mastermind-runtime/runner-watchdog/runner_connectivity_watchdog.py

This repository artifact is **not** a second service, new scheduler,
installer, deployment trigger, or independent recovery controller.
The existing M2 LaunchAgent remains the sole scheduled owner.

The observer reads GitHub runner status, launchd service presence, and local
Runner.Worker processes. It restarts **at most one** runner, only after two
authenticated GitHub *offline + not busy* observations, a confirmation gap,
a loaded launchd service, and absence of a live worker. GitHub API blindness,
an unknown launchd state, or an unknown worker state never grants restart.

The bounded diagnostic observes up to 64 KiB of each of the two most recent
Runner_*.log files per runner and reports recent broker HTTP timeout/shutdown
events, plus two or more BrokerServer ResponseEnded failures, within a
20-minute clock window. A single short-lived ResponseEnded does not count as
degraded by itself. An offline/busy runner is explicitly
degraded even when the timeout event is stale. These readings never expand
restart eligibility or cancel running jobs.

Hermetic test:

    python3 -m pytest tests/test_runner_connectivity_watchdog.py -q

Read-only dry-run preflight on M2:

    python3 ops/runner_connectivity_watchdog.py --dry-run

Source publication, installation, loaded service selection, and production
proof are separate. A PR does not update the installed script. Do not
restart a busy runner, reuse an uncertain effect, or rerun a failed nightly
merely because this source copy exists.

The GitHub Actions runner v2.337.0 timeout mitigation is independently
staged on M2. This watcher is not a substitute for genuine full-duration
runner and data-publisher acceptance.
