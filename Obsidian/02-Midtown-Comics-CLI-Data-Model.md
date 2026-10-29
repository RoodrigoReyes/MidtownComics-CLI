# Midtown Comics CLI — Conceptual Data Model

## Model overview

Midtown Comics CLI does not persist a normalized local database. Instead, it creates short-lived normalized records from Midtown responses. The following model describes the records exchanged between the client, parsers, command layer, and exports.

```mermaid
erDiagram
    ACCOUNT ||--o{ ORDER : owns
    ACCOUNT ||--o{ WISHLIST_ITEM : saves
    ACCOUNT ||--|| CART : has
    ORDER ||--o{ ORDER_ITEM : contains
    ORDER_ITEM }o--|| PRODUCT : references
    WISHLIST_ITEM }o--|| PRODUCT : references
    CART ||--o{ CART_ITEM : contains
    CART_ITEM }o--|| PRODUCT : references
    PRODUCT ||--o| SEARCH_RESULT : discovered_as
    PRODUCT ||--o| RELEASE_INFO : enriches
    SESSION ||--o{ REQUEST : authenticates

    ACCOUNT { string name; string email; string date_of_birth }
    ORDER { string order_number; string date; string status; number total; string currency }
    ORDER_ITEM { string product_id; string title; integer quantity; number unit_price; string status }
    PRODUCT { string product_id; string title; string product_url; number price }
    WISHLIST_ITEM { string product_id; string title; number current_price; string product_url }
    CART { number total; number free_shipping_remaining }
    CART_ITEM { string product_id; string title; integer quantity; number unit_price; number subtotal }
    SEARCH_RESULT { string availability; string release_date; string publisher }
    RELEASE_INFO { string release_date }
    SESSION { string cookie_set; string browser_profile }
    REQUEST { string endpoint; string retrieval_time }
```

## Record types

### Account profile

The account profile contains a limited set of user-facing fields: name, date of birth, and email. The masked password is intentionally not modeled as an output record.

### Order

An order is a purchase-context record containing order number, date, status, total, currency, and its item list. Orders are retrieved from the account's order pages and may be grouped into in-process or processed/shipped/completed categories.

### Order item

An order item represents a comic or product associated with an order. It can contain product identifier, title, quantity, unit price, product URL, and fulfillment status. Pending order items are also used as one source of preorder information.

### Product

A product is a catalog item identified by a Midtown product identifier and URL. Product information may appear in order details, wishlist entries, cart items, or search results. The same product can therefore be observed in multiple contexts.

### Preorder item

A preorder item is an acquisition record expected before release. It may originate from a pending item inside a regular order or from the Midtown Previews preorder section. The CLI combines both sources into a common record with source, order context, product data, quantity, price, release date, and status.

### Wishlist item

A wishlist item represents a saved catalog target and its current displayed price. It is a planning record, not a confirmed purchase.

### Cart and cart item

The cart is a current planning or checkout state read from Midtown. A cart item includes quantity, title, unit price, subtotal, and product reference. Cart data is deliberately read-only and is not treated as a completed purchase.

### Search result

A search result represents a catalog discovery at query time. It may contain product identifier, title, publisher, price, release date, availability, and product URL. Availability is normalized to `in stock`, `pre-order`, or `out of stock` when the website exposes a recognizable state.

### Session

A session is the locally persisted authentication context used to make account requests. It is composed of domain-scoped cookies and, for browser authentication, a persistent browser profile. Session records are sensitive operational state and are not exported as business data.

## Relationships and identity

- `product_id` is the principal external identity for a Midtown product when available.
- `order_number` identifies an external order context.
- An order can contain multiple order items.
- A product can occur in an order, wishlist, cart, and search result without becoming multiple products.
- A preorder item can be linked to an order or to the Previews source.
- A search result is an observation, not an ownership or purchase record.
- A session authenticates requests but is not part of comic or order identity.

## Data lifecycle

Records are created when a command retrieves them and normally disappear after the command completes unless exported by the user. JSON and CSV outputs are snapshots with retrieval-time meaning.

This architecture avoids stale local duplication but means that historical comparisons, ownership status, and long-term purchase analytics require an external persistence layer such as LongBox or a user-managed export archive.

## Normalization principles

Although there is no local relational schema, the in-memory record shapes follow practical normalization principles:

- Shared product identity is represented through `product_id` and `product_url` rather than repeated database rows.
- Order-level totals and status are kept at the order level.
- Item quantity and unit price remain item-level facts.
- Search availability and release date remain observations from catalog context.
- Authentication cookies remain outside business records.
