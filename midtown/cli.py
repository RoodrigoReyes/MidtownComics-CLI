"""Midtown Comics command-line interface."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import click

from .client import MidtownClient


def emit(value, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(value, indent=2, ensure_ascii=False))
    elif isinstance(value, list):
        for row in value:
            click.echo(" | ".join(f"{key}: {val}" for key, val in row.items() if key != "items"))
            for item in row.get("items", []):
                click.echo(f"  - {item.get('quantity', 1)}x {item.get('title', '')} ({item.get('product_id', '')})")
    elif isinstance(value, dict):
        for key, val in value.items():
            if isinstance(val, dict):
                click.echo(f"{key}:")
                for sub_key, sub_val in val.items():
                    detail = " | ".join(f"{k}: {v}" for k, v in sub_val.items()) if isinstance(sub_val, dict) else sub_val
                    click.echo(f"  {sub_key}: {detail}")
            else:
                click.echo(f"{key}: {val}")
    else:
        click.echo(value)


def _client_data(method: str):
    try:
        return getattr(MidtownClient(), method)()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


def _unsupported(feature: str) -> None:
    raise click.ClickException(
        f"{feature} is not implemented yet because the corresponding Midtown endpoint has not been verified."
    )


def _write_export(value, output: str, format_name: str) -> None:
    if format_name == "json":
        content = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    else:
        if not isinstance(value, list):
            raise click.ClickException("CSV export requires a list result.")
        fields = ["order_number", "date", "status", "total"] if value and "order_number" in value[0] else [
            "product_id", "title", "price", "product_url"
        ]
        rows = [{field: row.get(field, "") for field in fields} for row in value]
        from io import StringIO

        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        content = stream.getvalue()

    if output == "-":
        click.echo(content, nl=False)
    else:
        Path(output).write_text(content, encoding="utf-8")
        click.echo(f"Exported {len(value)} records to {output}")


@click.group()
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON.")
@click.pass_context
def cli(ctx: click.Context, as_json: bool) -> None:
    """Headless CLI for your Midtown Comics account.

    Credentials are read from .env at the project root (MIDTOWN_EMAIL,
    MIDTOWN_PASSWORD). Commands that need your account log in automatically
    with headless Chromium when the saved session is missing or expired.

    \b
    Examples:
      midtown orders stats --by month
      midtown preorders list
      midtown --json wishlist list
      midtown search "absolute batman" --include-preorders --show-out-of-stock
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json


@cli.group()
def auth() -> None:
    """Log in, log out and inspect credentials/session files."""


@auth.command("configure")
def auth_configure() -> None:
    """Save credentials to ~/.config/midtown-comics/credentials.

    Used only when .env and the MIDTOWN_EMAIL/MIDTOWN_PASSWORD environment
    variables are not set.
    """
    from .credentials import save_credentials

    email = click.prompt("Email")
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    save_credentials(email.strip(), password)
    click.echo("Credentials saved in the local Midtown config.")


@auth.command("login")
def auth_login() -> None:
    """Log in now with the stored credentials (headless Chromium).

    Normally not needed: account commands log in automatically when the
    session expires.
    """
    try:
        MidtownClient().login()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("Login successful. Session saved locally.")


@auth.command("browser-login")
@click.option("--auto/--remote", "use_auto", default=True, show_default=True, help="Try local credentials first, then fall back to the remote browser link.")
@click.option("--timeout", type=click.IntRange(min=60, max=3600), default=900, show_default=True)
def auth_browser_login(use_auto: bool, timeout: int) -> None:
    """Log in automatically, or through a remote browser.

    If the automated login fails, prints a temporary noVNC/ngrok URL where you
    complete the Midtown login manually (needs Xvfb, x11vnc, novnc, ngrok).
    """
    from .remote_auth import run_browser_login

    try:
        run_browser_login(auto=use_auto, timeout=timeout)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


@auth.command("logout")
def auth_logout() -> None:
    """Remove the locally saved HTTP session."""
    from .credentials import SESSION_FILE

    SESSION_FILE.unlink(missing_ok=True)
    click.echo("Local Midtown session removed.")


@auth.command("status")
@click.pass_context
def auth_status(ctx: click.Context) -> None:
    """Show which credential, cookie and session files exist."""
    from .credentials import COOKIES_FILE, CREDENTIALS_FILE, ENV_FILE, SESSION_FILE
    from .remote_auth import PROFILE_DIR

    result = {
        "env_file": str(ENV_FILE),
        "env_file_present": ENV_FILE.exists(),
        "credentials_file": str(CREDENTIALS_FILE),
        "credentials_configured": CREDENTIALS_FILE.exists(),
        "cookies_file": str(COOKIES_FILE),
        "cookies_present": COOKIES_FILE.exists(),
        "session_file": str(SESSION_FILE),
        "session_present": SESSION_FILE.exists(),
        "browser_profile": str(PROFILE_DIR),
        "browser_profile_present": PROFILE_DIR.exists(),
    }
    emit(result, ctx.obj["json"])


@cli.group(invoke_without_command=True)
@click.pass_context
def orders(ctx: click.Context) -> None:
    """List and inspect orders."""
    if ctx.invoked_subcommand is None:
        _orders_list(ctx)


def _orders_list(ctx: click.Context) -> None:
    emit(_client_data("orders"), ctx.obj["json"])


@orders.command("list")
@click.pass_context
def orders_list(ctx: click.Context) -> None:
    """List orders and their purchased items."""
    _orders_list(ctx)


@orders.command("show")
@click.argument("order_number")
@click.pass_context
def orders_show(ctx: click.Context, order_number: str) -> None:
    """Show one order by order number."""
    result = next(
        (order for order in _client_data("orders") if str(order.get("order_number")) == order_number),
        None,
    )
    if result is None:
        raise click.ClickException(f"Order not found: {order_number}")
    emit(result, ctx.obj["json"])


def _order_totals(orders_result: list[dict]) -> dict:
    total = sum(
        (Decimal(str(order["total"])) for order in orders_result if order.get("total") is not None),
        Decimal(0),
    )
    comics = sum(item.get("quantity", 1) for order in orders_result for item in order.get("items", []))
    return {"orders": len(orders_result), "comics": comics, "total": float(total)}


def _order_month(order: dict) -> str:
    try:
        return datetime.strptime(order.get("date", ""), "%m/%d/%Y").strftime("%Y-%m")
    except ValueError:
        return "unknown"


@orders.command("stats")
@click.option("--by", "group_by", type=click.Choice(["month"]), help="Break spending down by month.")
@click.pass_context
def orders_stats(ctx: click.Context, group_by: str | None) -> None:
    """Show total spent, orders and comics, by status.

    With --by month, show the same totals for each month.
    """
    result = _client_data("orders")
    if group_by == "month":
        months = sorted({_order_month(order) for order in result})
        rows = [
            {"month": month, **_order_totals([order for order in result if _order_month(order) == month])}
            for month in months
        ]
        emit(rows, ctx.obj["json"])
        return
    totals = _order_totals(result)
    statuses = dict.fromkeys(order.get("status", "") for order in result)
    stats = {
        "orders": totals["orders"],
        "comics": totals["comics"],
        "total_spent": totals["total"],
        "currency": "USD",
        "by_status": {
            status: _order_totals([order for order in result if order.get("status", "") == status])
            for status in statuses
        },
    }
    emit(stats, ctx.obj["json"])


@orders.command("export")
@click.option("--format", "format_name", type=click.Choice(["json", "csv"]), default="json", show_default=True)
@click.option("--output", type=click.Path(dir_okay=False, path_type=str), default="-", show_default=True)
def orders_export(format_name: str, output: str) -> None:
    """Export orders as JSON or CSV."""
    _write_export(_client_data("orders"), output, format_name)


@cli.group(invoke_without_command=True)
@click.pass_context
def wishlist(ctx: click.Context) -> None:
    """List and manage wishlist products."""
    if ctx.invoked_subcommand is None:
        _wishlist_list(ctx)


def _wishlist_list(ctx: click.Context) -> None:
    emit(_client_data("wishlist"), ctx.obj["json"])


@wishlist.command("list")
@click.pass_context
def wishlist_list(ctx: click.Context) -> None:
    """List products in the authenticated wishlist."""
    _wishlist_list(ctx)


@wishlist.command("export")
@click.option("--format", "format_name", type=click.Choice(["json", "csv"]), default="json", show_default=True)
@click.option("--output", type=click.Path(dir_okay=False, path_type=str), default="-", show_default=True)
def wishlist_export(format_name: str, output: str) -> None:
    """Export wishlist products as JSON or CSV."""
    _write_export(_client_data("wishlist"), output, format_name)


@wishlist.command("add")
@click.argument("product_id")
def wishlist_add(product_id: str) -> None:
    """[not implemented] Add a product to the wishlist."""
    del product_id
    _unsupported("Wishlist additions")


@wishlist.command("remove")
@click.argument("product_id")
def wishlist_remove(product_id: str) -> None:
    """[not implemented] Remove a product from the wishlist."""
    del product_id
    _unsupported("Wishlist removals")


@wishlist.command("prices")
@click.pass_context
def wishlist_prices(ctx: click.Context) -> None:
    """Show current prices for wishlist products (same as list)."""
    _wishlist_list(ctx)


@wishlist.command("price-drops")
def wishlist_price_drops() -> None:
    """[not implemented] Show wishlist products whose price dropped."""
    _unsupported("Wishlist price history")


@cli.group(invoke_without_command=True)
@click.pass_context
def preorders(ctx: click.Context) -> None:
    """Pre-ordered items not released yet."""
    if ctx.invoked_subcommand is None:
        emit(_client_data("preorders"), ctx.obj["json"])


@preorders.command("list")
@click.pass_context
def preorders_list(ctx: click.Context) -> None:
    """List pending pre-orders with release dates.

    Includes pending items of regular orders and Midtown Previews pre-orders.
    """
    emit(_client_data("preorders"), ctx.obj["json"])


@preorders.command("total")
@click.pass_context
def preorders_total(ctx: click.Context) -> None:
    """Show pending pre-order count and their combined price."""
    items = _client_data("preorders")
    total = sum(
        (Decimal(str(item["unit_price"])) * item.get("quantity", 1) for item in items if item.get("unit_price") is not None),
        Decimal(0),
    )
    emit({"items": sum(item.get("quantity", 1) for item in items), "total": float(total), "currency": "USD"}, ctx.obj["json"])


@cli.group()
def account() -> None:
    """Inspect account information."""


@account.command("show")
@click.pass_context
def account_show(ctx: click.Context) -> None:
    """Show your profile: name, date of birth and email."""
    emit(_client_data("account"), ctx.obj["json"])


@cli.group()
def product() -> None:
    """Inspect catalog products."""


@product.command("show")
@click.argument("product_id")
def product_show(product_id: str) -> None:
    """[not implemented] Show one catalog product."""
    del product_id
    _unsupported("Product lookup")


@cli.command("search")
@click.argument("query")
@click.option("--per-page", type=click.IntRange(min=1, max=100), default=100, show_default=True, help="Results per page (fewer is faster).")
@click.option("--page", type=click.IntRange(min=1), default=1, show_default=True, help="Results page number.")
@click.option("--include-preorders/--exclude-preorders", default=False, show_default=True, help='Include items not released yet (site: "Include Pre-orders").')
@click.option("--show-out-of-stock/--hide-out-of-stock", default=False, show_default=True, help='Include sold-out items (site: "Show out of stock").')
@click.pass_context
def search(ctx: click.Context, query: str, per_page: int, page: int, include_preorders: bool, show_out_of_stock: bool) -> None:
    """Search the Midtown Comics catalog.

    Results include price, release_date and availability (in stock,
    pre-order, out of stock). Like the website, pre-orders and sold-out items
    are hidden unless you enable their filters.

    \b
    Examples:
      midtown search "spider-man"
      midtown search "absolute batman" --include-preorders --show-out-of-stock
      midtown --json search "x-men" --per-page 20 --page 2
    """
    try:
        result = MidtownClient().search(query, per_page, page, include_preorders, show_out_of_stock)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    emit(result, ctx.obj["json"])


@cli.group()
def collection() -> None:
    """Analyze purchased items from orders."""


@collection.command("stats")
@click.pass_context
def collection_stats(ctx: click.Context) -> None:
    """Show collection statistics based on order items."""
    orders_result = _client_data("orders")
    items = [item for order in orders_result for item in order.get("items", [])]
    result = {
        "orders": len(orders_result),
        "distinct_products": len({item.get("product_id") for item in items if item.get("product_id")}),
        "comics": sum(item.get("quantity", 1) for item in items),
    }
    emit(result, ctx.obj["json"])


@collection.command("duplicates")
@click.pass_context
def collection_duplicates(ctx: click.Context) -> None:
    """Show products purchased in more than one order."""
    orders_result = _client_data("orders")
    counts = {}
    for order in orders_result:
        for item in order.get("items", []):
            key = item.get("product_id") or item.get("title")
            if key:
                counts.setdefault(key, {"product_id": item.get("product_id", ""), "title": item.get("title", ""), "quantity": 0, "orders": 0})
                counts[key]["quantity"] += item.get("quantity", 1)
                counts[key]["orders"] += 1
    emit([item for item in counts.values() if item["orders"] > 1], ctx.obj["json"])


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check local configuration and session files."""
    from .credentials import COOKIES_FILE, CREDENTIALS_FILE, SESSION_FILE

    result = {
        "config_directory": str(CREDENTIALS_FILE.parent),
        "credentials_file": CREDENTIALS_FILE.exists(),
        "cookies_file": COOKIES_FILE.exists(),
        "session_file": SESSION_FILE.exists(),
    }
    emit(result, ctx.obj["json"])


if __name__ == "__main__":
    cli()
