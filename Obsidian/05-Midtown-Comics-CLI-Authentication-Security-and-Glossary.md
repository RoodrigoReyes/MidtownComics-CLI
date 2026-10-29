# Midtown Comics CLI — Authentication, Security, and Glossary

## Authentication architecture

### Credential sources

Credentials are read from environment variables first and from the project-root `.env` file as a fallback. The `.env` file is local configuration and must remain git-ignored with restrictive permissions.

### Saved session

The CLI stores authenticated cookie objects in the configured Midtown user directory, normally `~/.config/midtown-comics/session.json`. An optional `cookies.json` can provide imported browser cookies. Cookies are filtered so only domains containing `midtowncomics.com` are accepted.

Cookie domain, path, expiry, secure, and related scope metadata are preserved where available. This reduces the risk of sending a cookie outside its intended web scope.

### Automated browser login

Automated login uses a persistent Playwright Chromium profile. The browser loads Midtown's login page, fills credentials, keeps the remember-me context, and validates the result against an authenticated account endpoint before saving cookies.

The authentication result is accepted only after the account context is validated. A browser redirect alone is not treated as sufficient evidence of a valid session.

### Remote login

The manual fallback creates temporary local display and browser-access infrastructure through Xvfb, x11vnc, noVNC, and ngrok. It exposes a temporary HTTPS link so the user can complete login interactively. Processes are terminated after authentication or timeout.

This mode has a higher operational risk because it temporarily exposes a browser interface. It should be used only when required, with a bounded timeout, and the link should be treated as sensitive.

## Security boundaries

- Never include `.env` in a project archive.
- Never expose session cookies, browser profiles, or cookie exports in chat or documentation.
- Never include credentials in Obsidian notes.
- Do not upload order exports or account data to external services without explicit authorization.
- Keep the CLI read-only; do not turn account-reading access into purchase or cart mutation behavior.
- Treat order history, wishlist contents, cart contents, and account profile data as confidential personal information.
- Treat remote-login links as temporary credentials while active.
- Do not interpret a successful HTTP request as proof of an authenticated or complete account response; validate the returned context.

## Test and change boundary

Parser tests use local HTML fixtures and do not contact Midtown. When the external markup changes, the expected maintenance process is to capture a sanitized fixture, update the parser contract, and preserve coverage for the affected record type.

The CLI should report a normal login or parsing failure rather than attempting to bypass Midtown protections. CAPTCHA behavior and private endpoints remain external dependencies.

## Glossary

### Account

The authenticated Midtown customer context used to retrieve orders, wishlist, cart, profile, and preorder information.

### Session

The local collection of cookies and browser state used to authenticate HTTP or browser requests.

### Order

A Midtown purchase context identified by an order number and associated with date, status, total, and items.

### Order item

A product entry inside an order, including quantity, price, title, product identity, and fulfillment status when exposed.

### Purchased comic

A comic observed inside an order. This is evidence of an account purchase, not independent proof of physical possession.

### Preorder

An item expected before release. The CLI can derive it from pending order items or the Midtown Previews preorder section.

### Wishlist

A saved product target maintained by the Midtown account.

### Cart

The current set of products staged for possible checkout. Cart presence does not equal purchase.

### Product

A catalog item identified by a Midtown product identifier and product URL.

### Availability

The catalog observation normalized as in stock, pre-order, or out of stock where the source markup supports that interpretation.

### Release date

The date presented by Midtown for a product's release, used especially to enrich preorder records.

### Snapshot

A point-in-time result returned by a command or export. It can become stale as Midtown data changes.

### Parser contract

The expected mapping between a Midtown HTML structure and a normalized record shape.

### Read-only integration

An integration that retrieves and transforms external data without changing the external account or commerce state.

## Open modeling decisions

- Whether long-term historical snapshots should be persisted outside the CLI.
- Whether product identity needs additional edition or variant fields for collection integration.
- Whether receipt and ownership confirmation should be linked automatically to LongBox or remain a manual step.
- How to handle future Midtown authentication changes without weakening the read-only and security boundaries.
