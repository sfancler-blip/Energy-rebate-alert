# Testing a monitor locally

`monitor.py` is self-contained and reads `config.json` / `state.json` from its
own folder, so you can exercise the full pipeline offline against a fixture.

## Local Chromium + proxy env

- Point Playwright at the preinstalled browser:
  `export PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium-*/chrome-linux/chrome`
- Behind an inspecting HTTPS proxy, `monitor.py` auto-reads `HTTPS_PROXY` and
  adds `--ignore-certificate-errors`. For a `file://` fixture, `unset HTTPS_PROXY`.
- If the pip Playwright version wants a different browser build than what's
  installed, `PLAYWRIGHT_CHROMIUM_PATH` overrides it.

## Fixture-based test (recommended when the live site is blocked)

1. Save an HTML fixture resembling the target (one event card per event).
2. Point `config.json.url` at `file:///abs/path/page.html`.
3. Run once → baseline. Confirm the logged "Captured section" is the right card.
4. Mutate the fixture's target card (e.g. add a `Buy Tickets` link). Run again →
   must log `CHANGE DETECTED`.
5. Mutate a *different* event's card. Run again → must log `No change detected`
   (confirms scoping to one event).

## Live smoke test (when reachable)

Set `config.json.url` to the real URL, run once, and inspect the logged
"Captured section" to confirm `match_patterns` selected the intended block.
Tune `match_patterns` / `settle_ms` if the section is empty or wrong, then
delete the local `state.json` contents (`{}`) so CI baselines cleanly.
