---
name: site-change-alert
description: >
  Set up an independent, daily webpage-change alert for a single site. Use when
  the user wants to "watch", "monitor", or "be notified/alerted when a page
  changes" — e.g. when tickets go on sale, a price drops, a date/line on a
  calendar changes, or a status/word appears or disappears. Each invocation
  scaffolds a fully self-contained monitor (its own script, config, state file,
  and GitHub Actions workflow) with NO dependency on any other monitor. Uses
  Playwright/Chromium so it works on JS-rendered or bot-blocking sites, and
  emails the alert. Trigger phrases: "alert me when", "notify me when tickets go
  on sale", "watch this page", "monitor this URL".
---

# Site change alert

Scaffold a **self-contained daily monitor** for one URL. Each monitor is
isolated: its own folder under `monitors/<slug>/`, its own workflow at
`.github/workflows/monitor-<slug>.yml`, its own `state.json` baseline. Adding or
deleting one never affects the others. Runs on GitHub Actions cron (open
internet — important, since some sites block non-browser requests and Actions
runners can reach them where a sandbox may not).

## What each monitor does

1. Loads the page in real Chromium via Playwright (defeats JS rendering + 403
   bot blocks that plain `requests`/`curl` hit).
2. Finds the smallest element matching the user's `match_patterns` (e.g. a
   date), then climbs to the enclosing **single-event card** so it captures the
   date line *plus* its ticket link / status — but not neighboring events.
3. Hashes that card's text + links, compares to the committed baseline, and
   **emails on any change**. First run only establishes the baseline.

## Procedure to add a new monitor

Assets live in `.claude/skills/site-change-alert/assets/`.

1. **Pick a slug** — short, kebab-case, unique (e.g. `portland-aug21`).

2. **Scrape once to find the target.** Load the URL in Playwright and print the
   `body` innerText near what the user cares about, so you choose good
   `match_patterns`. If a sandbox egress proxy blocks the host (403 at the
   proxy), skip the live scrape — pick patterns from the user's description and
   note that the first CI run's logs will confirm what was captured.
   - Local Playwright needs Chromium at `$PLAYWRIGHT_CHROMIUM_PATH` and, behind
     an inspecting proxy, `HTTPS_PROXY` + `--ignore-certificate-errors`
     (monitor.py already reads both env vars).

3. **Create the monitor folder** `monitors/<slug>/`:
   - Copy `assets/monitor.py`            → `monitors/<slug>/monitor.py` (verbatim, self-contained).
   - Copy `assets/requirements.txt`      → `monitors/<slug>/requirements.txt`.
   - Fill `assets/config.template.json`  → `monitors/<slug>/config.json`:
     - `url` — the page.
     - `match_patterns` — strings that identify the line/section (include a few
       spellings, e.g. `["August 21","Aug 21","8/21"]`). Matching is
       case-insensitive substring.
     - `label`, `alert_subject`, optional `settle_ms` (ms to wait after load).
   - Write `monitors/<slug>/state.json` as `{}` (baseline fills on first run).

4. **Create the workflow.** Copy `assets/workflow.template.yml` to
   `.github/workflows/monitor-<slug>.yml` and replace every `<SLUG>` with the
   slug. Set the `cron` (default daily `0 13 * * *` ≈ 6am PT).

5. **Verify locally if reachable** (see `references/testing.md`): run once to
   baseline, mutate a local fixture, run again, confirm it alerts.

6. **Commit & push.** The workflow commits `state.json` back after each run.

7. **Tell the user the one-time setup:** add the email secrets
   (`MAIL_USERNAME`, `MAIL_PASSWORD`, optional `MAIL_TO`) in the repo's GitHub
   Settings → Secrets and variables → Actions. See `references/setup-email.md`.
   Until secrets exist, runs still succeed and log the alert instead of emailing,
   so the baseline is safe to establish first.

## Notes

- **Change vs. word-watch:** default watches a whole event card for *any*
  change. That's ideal for "tickets go on sale" (a Buy button/link appears). If
  the user instead wants "alert when WORD disappears", narrow `match_patterns`
  and note the section will read as changed when the word's line changes.
- **Frequency:** GitHub Actions cron min interval is ~5 min but is best-effort;
  daily/hourly are reliable. One `cron` line per monitor keeps them independent.
- **Removing a monitor:** delete its `monitors/<slug>/` folder and its workflow
  file. Nothing else references it.
