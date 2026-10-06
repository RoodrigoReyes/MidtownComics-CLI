# Midtown Comics CLI

A command-line client for your [Midtown Comics](https://www.midtowncomics.com) account. Check orders, pre-orders, your cart and wishlist, track what you spend, and search the catalog without opening a browser. It runs fine on a headless Linux server.

> Unofficial project, not affiliated with Midtown Comics. It reads the same pages your browser does and never places orders or changes your cart.

```console
$ midtown orders stats --by-month
MONTH    ORDERS  COMICS   TOTAL
2026-08       3      11   64.27
2026-09       4      15   81.90
```

## Installation

Requires Python 3.10 or newer.

```bash
git clone https://github.com/RoodrigoReyes/MidtownComics-CLI.git
cd MidtownComics-CLI
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[browser]'
playwright install chromium
```

Then add your login:

```bash
cp .env.example .env
chmod 600 .env
# edit .env and set MIDTOWN_EMAIL and MIDTOWN_PASSWORD
```

The `browser` extra installs Playwright, which is needed to log in (see [How login works](#how-login-works)). Without it, the CLI can still use an existing session but can't create a new one.

## Usage

```text
midtown
├── orders                list orders
│   ├── show <number>     one order and its comics
│   ├── stats             spending totals, by status or by month
│   ├── duplicates        comics bought in more than one order
│   └── export            save to JSON or CSV
├── comics                every comic you've bought, newest first
├── preorders             pre-ordered comics that haven't shipped yet
├── cart                  current cart (read-only)
├── wishlist              wishlist with current prices
│   └── export            save to JSON or CSV
├── search <text>         search the catalog
├── account               name, date of birth and email
├── auth                  login, logout, status
└── help [command]
```

Some examples:

```bash
midtown orders show 4349113
midtown comics --from 2026-09-01 --to 2026-09-30
midtown comics --by-month 2026-09
midtown orders stats --with-cart
midtown orders export --format csv -o orders.csv
midtown search "absolute batman" --preorders --out-of-stock
midtown wishlist --json
```

Every command accepts `--json`. Run `midtown help <command>` for the full list of options.

### Notes on specific commands

**Date filters.** `orders`, `orders stats` and `comics` take `--from` and `--to` (`YYYY-MM-DD`, inclusive) and `--by-month`. On its own, `--by-month` groups results by month; with a value like `--by-month 2026-09` it limits them to that month. Put it after the subcommand (`midtown orders stats --by-month`), otherwise Click reads the subcommand name as its value.

**`orders stats --with-cart`** adds the current cart to your total spent. Cart prices don't include shipping or tax. It can't be combined with the per-month summary.

**`preorders`** combines two sources: items still marked *Pending* in your regular orders, and Midtown Previews pre-orders. Release dates come from each product page, so it makes one extra request per item.

**`search`** behaves like the website: pre-orders and sold-out comics are hidden unless you pass `--preorders` or `--out-of-stock`. The site loads prices for some results lazily, so a full page of 100 results takes a few seconds. Use `--per-page` and `--page` to paginate.

## How login works

Midtown's login form is protected by reCAPTCHA v3, so a plain HTTP request can't sign in. When a command finds that the session is missing or expired, the CLI opens headless Chromium, signs in with the credentials from `.env`, saves the session cookies and retries the request. You don't need to log in by hand.

If the automatic login keeps failing (for example, because reCAPTCHA scores the server too low), run:

```bash
midtown auth login --remote
```

It starts a virtual display and prints a temporary noVNC link (through ngrok) where you can sign in yourself. Everything shuts down once you're logged in or after `--timeout` seconds (900 by default). This needs some system packages:

```bash
sudo apt install xvfb x11vnc novnc
ngrok config add-authtoken <your-token>
```

It uses local ports 5900, 6080 and 4040.

Other auth commands:

- `midtown auth status` shows which credential and session files exist.
- `midtown auth logout` removes the saved session and browser profile.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MIDTOWN_EMAIL`, `MIDTOWN_PASSWORD` | | Credentials. Take precedence over `.env`. |
| `MIDTOWN_ENV_FILE` | `.env` in the project root | Load credentials from another file. |
| `MIDTOWN_CONFIG_DIR` | `~/.config/midtown-comics` | Where the session and browser profile are stored. |

The config directory holds `session.json` (cookies), `browser-profile/` (Chromium profile) and, optionally, `cookies.json`: a cookie export from your own browser that the CLI loads if present. Treat all of them like passwords.

## Development

```bash
pip install -e '.[browser,test]'
pytest
```

```text
midtown/
├── cli.py           commands, filters and output formatting
├── client.py        HTTP client and automatic re-login
├── parsers.py       HTML parsers for each page
├── credentials.py   credentials and session storage
└── remote_auth.py   Playwright login, automatic and --remote
tests/
└── test_parsers.py
```

The tests run against saved HTML fixtures and never touch the live site. If Midtown changes its markup and a command breaks, save the new HTML as a fixture, update the test, then fix the parser.

## Limitations

This tool depends on Midtown's private pages and endpoints, which can change without notice. It doesn't try to get around the CAPTCHA or any other protection: if a login fails, it reports the error.
