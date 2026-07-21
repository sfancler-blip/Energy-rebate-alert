# Email setup (one time per repo)

Alerts are sent via SMTP from `monitor.py`, using GitHub Actions secrets. Do
this once; every monitor in the repo reuses it.

## Secrets to add

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret          | Value                                              | Required |
|-----------------|----------------------------------------------------|----------|
| `MAIL_USERNAME` | Sending Gmail address, e.g. `you@gmail.com`         | yes      |
| `MAIL_PASSWORD` | Gmail **App Password** (16 chars, not your login)  | yes      |
| `MAIL_TO`       | Recipient. Defaults to `MAIL_USERNAME` if omitted. | optional |

Optional overrides (repo variables or secrets), if not using Gmail:
`MAIL_HOST` (default `smtp.gmail.com`), `MAIL_PORT` (default `465` = SSL; use
`587` for STARTTLS).

## Creating a Gmail App Password

1. The account needs **2-Step Verification ON**
   (https://myaccount.google.com/security).
2. Go to **https://myaccount.google.com/apppasswords**.
3. Name it (e.g. "site-change-alert") and **Create**.
4. Copy the 16-character password (no spaces) into the `MAIL_PASSWORD` secret.

App passwords bypass interactive login, which is why plain account passwords do
not work for SMTP here.

## Before secrets are set

`monitor.py` degrades gracefully: with no `MAIL_USERNAME`/`MAIL_PASSWORD`, it
logs the alert body to the Actions log instead of emailing and still saves the
baseline. So you can let the first run establish the baseline, then add secrets.

## Testing the email path

Trigger the workflow manually (**Actions → Monitor \<slug\> → Run workflow**).
The first manual run baselines. To force an alert for a real test, temporarily
edit that monitor's `state.json` `fingerprint` to a wrong value and re-run — you
should receive an email; then let it re-baseline.

## Not using Gmail?

Any SMTP provider works. Common alternatives:
- **SendGrid:** `MAIL_HOST=smtp.sendgrid.net`, `MAIL_PORT=587`,
  `MAIL_USERNAME=apikey`, `MAIL_PASSWORD=<sendgrid api key>`.
- **Fastmail / others:** use their SMTP host/port and an app-specific password.
