# Midtown Comics CLI — Overview

## Purpose

Midtown Comics CLI is a headless, read-only command-line client for retrieving account and catalog information from Midtown Comics. It provides a terminal-oriented view of orders, purchased comics, preorders, wishlist items, cart contents, account profile data, and catalog search results.

The project is designed for use from a local machine or Linux server where a graphical browser may not be available. It turns Midtown web responses into stable, machine-readable or human-readable records without attempting to purchase items or modify the cart and wishlist.

## Scope

The project currently covers:

- Reading account orders and order details.
- Reading comics contained in orders.
- Reading preorder information from regular orders and the Midtown Previews section.
- Reading the current shopping cart without modifying it.
- Reading wishlist entries and their current prices.
- Searching the Midtown catalog by text.
- Including or excluding preorders and out-of-stock products in search results.
- Reading basic account profile fields.
- Exporting selected order and wishlist data to JSON or CSV.
- Automated login with a headless browser when the saved session expires.
- Optional manual remote login through a temporary browser-access link.
- Persisting authenticated session cookies outside the project directory.

## Read-only boundary

The CLI is an observation and extraction tool. It does not complete purchases, add or remove cart items, change wishlist entries, or update account information. The cart is explicitly read-only, and account access is used to establish an authenticated session for permitted reads.

## Source of truth

Midtown Comics remains the source of truth for account, order, inventory, price, and wishlist state. The CLI does not maintain a local transactional database or attempt to become a second system of record.

The project stores only supporting local state required for authentication, principally session cookies and a browser profile under the configured user directory. Exported JSON or CSV files are snapshots and should not be interpreted as live account state.

## Main conceptual areas

1. **Account access** — authentication and session continuity.
2. **Order history** — order summaries, order details, status, dates, totals, and items.
3. **Acquisition state** — purchased comics, pending items, and preorders.
4. **Planning state** — wishlist and current shopping-cart contents.
5. **Catalog discovery** — search results, price, availability, and release dates.
6. **Data presentation** — terminal tables, JSON output, and CSV/JSON exports.
7. **Operational security** — credential isolation, cookie filtering, and temporary remote-login infrastructure.

## Documentation map

- [[01-Midtown-Comics-CLI-Technical-Architecture]] — system boundaries and information flow.
- [[02-Midtown-Comics-CLI-Data-Model]] — conceptual records and relationships.
- [[03-Midtown-Comics-CLI-Acquisition-Lifecycle]] — order, preorder, wishlist, cart, and fulfillment interpretations.
- [[04-Midtown-Comics-CLI-Command-and-Output-Model]] — command groups and output contracts.
- [[05-Midtown-Comics-CLI-Authentication-Security-and-Glossary]] — authentication, local state, security boundaries, and vocabulary.

## Important limitations

- Midtown may change private HTML endpoints or page markup.
- Login depends on Midtown's current browser and CAPTCHA behavior.
- Search and account records are snapshots taken at query time.
- The CLI does not provide an independent ownership ledger.
- An order being visible does not necessarily mean every item has been delivered or physically received.
