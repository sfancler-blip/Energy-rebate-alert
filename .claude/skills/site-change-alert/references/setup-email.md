# Email setup (one time per repo)

`monitor.py` tries **Resend** first, then falls back to **SMTP** (e.g. Gmail)
if Resend isn't configured. Do this once; every monitor in the repo reuses it.

## Option A — Resend (recommended: no password, no 2FA, no burner Gmail)

1. Sign up at https://resend.com with any email address (verifying that one
   email is the only account step — no 2FA required).
2. **API Keys → Create API Key** and copy it.
3. In the repo → **Settings → Secrets and variables → Actions → New repository
   secret**, add:

   | Secret          | Value                                        | Required |
   |-----------------|-----------------------------------------------|----------|
   | `RESEND_API_KEY`| the API key from step 2                        | yes      |
   | `MAIL_TO`       | where alerts should land                       | yes      |
   | `MAIL_FROM`     | default `Site Alerts <onboarding@resend.dev>`  | optional |

**Sandbox limit to know:** without verifying your own sending domain in
Resend, you can only send *to the email address you signed up with*. That's
fine here — you're alerting yourself — but if `MAIL_TO` needs to be a
different address later, verify a domain in Resend first (Domains → Add
Domain, then a few DNS records).

## Option B — SMTP fallback (e.g. Gmail with an App Password)

Only used if `RESEND_API_KEY` is not set. Requires 2-Step Verification and an
App Password on the sending account — use a burner Gmail here if you don't
want to touch your primary account's login.

| Secret          | Value                                              | Required |
|-----------------|------------------------------------------------------|----------|
| `MAIL_USERNAME` | Sending Gmail address                                 | yes      |
| `MAIL_PASSWORD` | Gmail **App Password** (16 chars, not your login)    | yes      |
| `MAIL_TO`       | Recipient. Defaults to `MAIL_USERNAME` if omitted.   | optional |

Optional overrides: `MAIL_HOST` (default `smtp.gmail.com`), `MAIL_PORT`
(default `465` = SSL; use `587` for STARTTLS).

App Password steps: enable 2-Step Verification
(https://myaccount.google.com/security) → **App Passwords**
(https://myaccount.google.com/apppasswords) → create → copy the 16-character
password into `MAIL_PASSWORD`.

## Before secrets are set

`monitor.py` degrades gracefully: with neither Resend nor SMTP configured, it
logs the alert body to the Actions log instead of emailing and still saves the
baseline. So you can let the first run establish the baseline, then add secrets.

## Testing the email path

Trigger the workflow manually (**Actions → Monitor \<slug\> → Run workflow**).
The first manual run baselines. To force an alert for a real test, temporarily
edit that monitor's `state.json` `fingerprint` to a wrong value and re-run — you
should receive an email; then let it re-baseline.
