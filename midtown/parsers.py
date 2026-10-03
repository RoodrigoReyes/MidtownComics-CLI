"""HTML parsers for the Midtown Comics account pages."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def _text(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _money(value: str):
    match = re.search(r"[-+]?\$?\s*([0-9][0-9,]*(?:\.\d{1,2})?)", value or "")
    return float(match.group(1).replace(",", "")) if match else None


def _first_text(parent, selectors: list[str]) -> str:
    for selector in selectors:
        node = parent.select_one(selector)
        if node:
            return _text(node)
    return ""


def _parse_midtown_order_tables(soup: BeautifulSoup) -> list[dict]:
    orders = []
    for table_id, status in (
        ("tbl-orders", "In Process"),
        ("tbl-processed", "Processed / Shipped & Completed"),
    ):
        table = soup.select_one(f"#{table_id}")
        if not table:
            continue
        for row in table.select("tbody tr"):
            cells = row.select("td")
            if len(cells) < 3:
                continue
            order_link = row.select_one(".tbl-order a")
            order_number = _text(order_link) if order_link else _text(cells[1])
            if not order_number:
                continue
            orders.append(
                {
                    "order_number": order_number,
                    "date": _text(row.select_one(".tbl-date")) or _text(cells[0]),
                    "status": status,
                    "total": _money(_text(row.select_one(".tbl-total")) or _text(cells[2])),
                    "currency": "USD",
                    "detail_url": "",
                    "items": [],
                }
            )
    return orders


def parse_orders(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("#tbl-orders, #tbl-processed"):
        return _parse_midtown_order_tables(soup)
    cards = soup.select("[data-order-number], .order, .order-card, .order-summary")
    orders = []
    for card in cards:
        order_number = card.get("data-order-number") or _first_text(
            card, [".order-number", "[class*=order-number]"]
        )
        if not order_number:
            match = re.search(r"(?:order\s*#?\s*)([A-Z0-9-]+)", _text(card), re.IGNORECASE)
            order_number = match.group(1) if match else ""
        if not order_number:
            continue

        detail = card.select_one("a[href]")
        items = []
        for item in card.select(".item, .order-item, [data-product-id]"):
            link = item.select_one("a[href]")
            product_id = item.get("data-product-id") or ""
            quantity_text = _first_text(item, [".quantity", "[class*=quantity]"])
            quantity_match = re.search(r"\d+", quantity_text)
            items.append(
                {
                    "product_id": product_id,
                    "title": _text(link) if link else _first_text(item, [".title", "[class*=title]"]),
                    "quantity": int(quantity_match.group()) if quantity_match else 1,
                    "unit_price": _money(_first_text(item, [".price", "[class*=price]"])),
                    "product_url": urljoin(base_url, link.get("href")) if link else "",
                }
            )

        orders.append(
            {
                "order_number": order_number,
                "date": _first_text(card, [".date", "[class*=date]"]),
                "status": _first_text(card, [".status", "[class*=status]"]),
                "total": _money(_first_text(card, [".total", "[class*=total]"])),
                "currency": "USD",
                "detail_url": urljoin(base_url, detail.get("href")) if detail else "",
                "items": items,
            }
        )
    return orders


def parse_order_detail(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select(".order-item"):
        image = card.select_one("img[src]")
        image_url = image.get("src", "") if image else ""
        match = re.search(r"/(\d+)_ful\.", image_url)
        detail = card.select_one("[aria-label]") or card
        title = _text(detail.select_one("h3"))
        each_text = next(
            (_text(p) for p in detail.find_all("p") if "Each:" in _text(p)),
            "",
        )
        qty_text = next(
            (_text(p) for p in detail.find_all("p") if "QTY:" in _text(p)),
            "",
        )
        qty_match = re.search(r"QTY:\s*(\d+)", qty_text, re.IGNORECASE)
        status_text = next(
            (_text(h) for h in detail.find_all(["h2", "h3"]) if "Status:" in _text(h)),
            "",
        )
        status = re.sub(r"^.*Status:\s*", "", status_text, flags=re.IGNORECASE).strip()
        if title:
            product_id = match.group(1) if match else ""
            items.append(
                {
                    "product_id": product_id,
                    "title": title,
                    "quantity": int(qty_match.group(1)) if qty_match else 1,
                    "unit_price": _money(each_text),
                    "product_url": urljoin(base_url, f"/product/{product_id}") if product_id else "",
                    "status": status,
                }
            )
    return items


def parse_search(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for card in soup.select('div[id^="main-record-"]'):
        record_id = card.get("id", "")
        match = re.search(r"main-record-(\d+)$", record_id)
        link = card.select_one('.product-title a[href]')
        title_node = card.select_one('.product-title h3')
        publisher_node = card.select_one('.pc-publisher')
        if not match or not title_node or not link:
            continue
        price_node = card.select_one('.pc-discounted, .price2')
        release_label = card.find("dt", string=lambda text: text and text.strip() == "Release Date")
        release_node = release_label.find_next_sibling("dd") if release_label else None
        products.append({
            "product_id": match.group(1),
            "title": _text(title_node),
            "publisher": _text(publisher_node),
            "price": _money(_text(price_node)),
            "release_date": _text(release_node).rstrip("*"),
            "availability": _search_availability(card),
            "product_url": urljoin(base_url, link.get("href", "")),
        })
    return products


def parse_product_body(html: str) -> dict:
    """Parse the price/cart block that search lazy-loads for some cards."""
    soup = BeautifulSoup(html, "html.parser")
    return {
        "price": _money(_text(soup.select_one(".pc-discounted, .price2"))),
        "availability": _search_availability(soup),
    }


def _search_availability(card) -> str:
    """Read availability from the quantity selector the card offers."""
    labels = {select.get("aria-label", "").lower() for select in card.select("select.qty[aria-label]")}
    if "pre order" in labels:
        return "pre-order"
    if "add to cart" in labels:
        return "in stock"
    if "wishlist" in labels:
        return "out of stock"
    return ""


def parse_wishlist(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("#divWL #sortable .wish-card"):
        products = []
        for card in soup.select("#divWL #sortable .wish-card"):
            link = card.select_one("a[href*='/product/']")
            if not link:
                continue
            product_url = urljoin(base_url, link.get("href"))
            match = re.search(r"/product/(\d+)", product_url)
            title = _text(card.select_one("h4")) or _text(link)
            price = _money(_text(card.select_one(".discount")))
            if price is None:
                price = _money(_text(card.select_one(".price")))
            if title:
                products.append({"product_id": match.group(1) if match else "", "title": title, "price": price, "product_url": product_url})
        return products
    cards = soup.select(".product-card, [data-product-id]")
    products = []
    for card in cards:
        link = card.select_one("a.product-title[href], a[href]")
        product_id = card.get("data-product-id", "")
        if not product_id and link:
            match = re.search(r"/p/(\d+)", link.get("href", ""))
            product_id = match.group(1) if match else ""
        title = _text(link) if link else _first_text(card, [".title", "[class*=title]"])
        if not title:
            continue
        products.append(
            {
                "product_id": product_id,
                "title": title,
                "price": _money(_first_text(card, [".price", "[class*=price]"])),
                "product_url": urljoin(base_url, link.get("href")) if link else "",
            }
        )
    return products


def parse_release_date(html: str) -> str:
    """Return the release date shown on a product page, or "" if absent."""
    soup = BeautifulSoup(html, "html.parser")
    label = soup.find("dt", string=lambda text: text and text.strip() == "Release Date")
    value = label.find_next_sibling("dd") if label else None
    return _text(value)


def parse_preview_items(html: str, base_url: str) -> list[dict]:
    """Parse the "My Pre-Order Items" (Previews program) section tables.

    ponytail: columns are mapped from the table headers; written against an
    account with empty tables, so adjust if real rows carry extra markup.
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for table in soup.find_all("table"):
        heading = table.find_previous("h3")
        status = _text(heading).replace(" Items", "") if heading else ""
        headers = [_text(th) for th in table.select("thead th")]
        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) != len(headers):
                continue
            values = dict(zip(headers, cells))
            link = values["Title"].find("a", href=True)
            match = re.search(r"/product/(\d+)", str(link["href"])) if link else None
            product_id = match.group(1) if match else ""
            quantity = re.search(r"\d+", _text(values["QTY"]))
            items.append(
                {
                    "source": "previews",
                    "order_number": _text(values["Order #"]),
                    "order_date": _text(values["Order Date"]),
                    "product_id": product_id,
                    "title": _text(values["Title"]),
                    "quantity": int(quantity.group()) if quantity else 1,
                    "unit_price": _money(_text(values["Price Each"])),
                    "release_date": _text(values["Release Date"]),
                    "status": status,
                    "product_url": urljoin(base_url, f"/product/{product_id}") if product_id else "",
                }
            )
    return items
