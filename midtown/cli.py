"""Midtown Comics command-line interface."""

from __future__ import annotations

import csv
import json
import re
import shutil
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path

import click

from .client import MidtownClient

# (header, value getter, alignment "<" left / ">" right)
Column = tuple[str, Callable[[dict], object], str]
COLUMN_GAP = "  "
MIN_TITLE_WIDTH = 20


def _set_json(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if value:
        ctx.ensure_object(dict)["json"] = True


# --json is accepted before or after any command: `midtown --json orders` == `midtown orders --json`.
json_option = click.option(
    "--json", is_flag=True, expose_value=False, callback=_set_json, help="Output machine-readable JSON."
)


def _store(key: str):
    """Option callback that stores the value in ctx.obj, so it works on a group or its subcommands."""

    def callback(ctx: click.Context, _param: click.Parameter, value: object) -> None:
        if value not in (None, False):
            ctx.ensure_object(dict)[key] = value

    return callback


class IsoDate(click.ParamType):
    name = "YYYY-MM-DD"

    def convert(self, value, param, ctx) -> date:
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()  # noqa: DTZ007 - date only
        except ValueError:
            self.fail(f"{value!r} is not a date in YYYY-MM-DD format.", param, ctx)


ALL_MONTHS = "*"


class YearMonth(click.ParamType):
    name = "YYYY-MM"

    def convert(self, value, param, ctx) -> str:
        if value == ALL_MONTHS or re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
            return value
        self.fail(f"{value!r} is not a month in YYYY-MM format.", param, ctx)


period_options = [
    click.option("--by-month", type=YearMonth(), is_flag=False, flag_value=ALL_MONTHS, expose_value=False,
                 callback=_store("by_month"),
                 help="Alone: totals per month. With YYYY-MM: only that month."),
    click.option("--from", "date_from", type=IsoDate(), expose_value=False, callback=_store("date_from"),
                 help="Only orders placed on or after this date."),
    click.option("--to", "date_to", type=IsoDate(), expose_value=False, callback=_store("date_to"),
                 help="Only orders placed on or before this date."),
]


def _with_options(options: list):
    def decorate(command):
        for option in reversed(options):
            command = option(command)
        return command

    return decorate


def _wants_json(ctx: click.Context) -> bool:
    return bool((ctx.obj or {}).get("json"))


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _print_table(rows: list[dict], columns: list[Column]) -> None:
    """Print aligned columns; a TITLE column shrinks to fit the terminal width."""
    headers = [header for header, _, _ in columns]
    cells = [[_cell(getter(row)) for _, getter, _ in columns] for row in rows]
    widths = [max([len(header)] + [len(row[index]) for row in cells]) for index, header in enumerate(headers)]
    if "TITLE" in headers:
        index = headers.index("TITLE")
        others = sum(widths) - widths[index] + len(COLUMN_GAP) * (len(widths) - 1)
        widths[index] = max(MIN_TITLE_WIDTH, min(widths[index], shutil.get_terminal_size().columns - others))

    def line(values: list[str]) -> str:
        return COLUMN_GAP.join(
            _fit(value, width).ljust(width) if align == "<" else value.rjust(width)
            for value, width, (_, _, align) in zip(values, widths, columns)
        ).rstrip()

    click.echo(line(headers))
    for row in cells:
        click.echo(line(row))


def _print_mapping(value: dict) -> None:
    for key, val in value.items():
        if isinstance(val, dict):
            click.echo(f"{key}:")
            for sub_key, sub_val in val.items():
                detail = " | ".join(f"{k}: {v}" for k, v in sub_val.items()) if isinstance(sub_val, dict) else sub_val
                click.echo(f"  {sub_key}: {detail}")
        else:
            click.echo(f"{key}: {val}")


def output(
    ctx: click.Context,
    value: list[dict] | dict,
    columns: list[Column] | None = None,
    empty: str = "",
    footer: str = "",
) -> None:
    """Print JSON with --json, otherwise a table (lists) or key: value lines (dicts)."""
    if _wants_json(ctx):
        click.echo(json.dumps(value, indent=2, ensure_ascii=False))
    elif isinstance(value, dict):
        _print_mapping(value)
    elif not value:
        click.echo(empty)
    else:
        _print_table(value, columns or [])
        if footer:
            click.echo(footer)


def _client_call(method: str, *args):
    try:
        return getattr(MidtownClient(), method)(*args)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


def _money(value: object) -> str:
    return f"${value:.2f}" if isinstance(value, (int, float)) else ""


def _comics(order: dict) -> int:
    return sum(item.get("quantity", 1) for item in order.get("items", []))


def _write_export(value: list[dict], output_path: str, format_name: str) -> None:
    if format_name == "json":
        content = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    else:
        fields = ["order_number", "date", "status", "total"] if value and "order_number" in value[0] else [
            "product_id", "title", "price", "product_url"
        ]
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in value)
        content = stream.getvalue()

    if output_path == "-":
        click.echo(content, nl=False)
    else:
        Path(output_path).write_text(content, encoding="utf-8")
        click.echo(f"Exported {len(value)} records to {output_path}")


export_options = [
    click.option("--format", "format_name", type=click.Choice(["json", "csv"]), default="json", show_default=True),
    click.option("--output", "-o", "output_path", type=click.Path(dir_okay=False), default="-", show_default=True,
                 help="File to write; - prints to the terminal."),
]


_with_export_options = _with_options(export_options)


@click.group()
@json_option
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Headless CLI for your Midtown Comics account.

    Credentials are read from .env at the project root (MIDTOWN_EMAIL,
    MIDTOWN_PASSWORD). Commands log in automatically when the saved session
    is missing or expired. Add --json to any command for JSON output.
    Run `midtown help <command>` for details, e.g. `midtown help search`.

    \b
    Examples:
      midtown orders
      midtown comics
      midtown orders stats --by-month
      midtown comics --from 2026-09-01 --to 2026-09-30
      midtown preorders
      midtown cart
      midtown search "absolute batman" --preorders --out-of-stock
      midtown wishlist --json
    """
    ctx.ensure_object(dict)


@cli.command("help")
@click.argument("command", nargs=-1)
@click.pass_context
def help_command(ctx: click.Context, command: tuple[str, ...]) -> None:
    """Show help for midtown or a command: midtown help orders stats"""
    root = ctx.find_root()
    target: click.Command = root.command
    path = [root.info_name or "midtown"]
    for name in command:
        sub = target.get_command(ctx, name) if isinstance(target, click.Group) else None
        if sub is None:
            raise click.UsageError(f"No such command: {' '.join([*path[1:], name])}")
        target = sub
        path.append(name)
    with click.Context(target, info_name=" ".join(path)) as target_ctx:
        click.echo(target.get_help(target_ctx))


# ---------------------------------------------------------------- auth


@cli.group()
def auth() -> None:
    """Log in, log out and check the saved session."""


@auth.command("login")
@click.option("--remote", is_flag=True, help="Log in yourself through a temporary browser link (noVNC/ngrok).")
@click.option("--timeout", type=click.IntRange(min=60, max=3600), default=900, show_default=True,
              help="Seconds to wait for the --remote login.")
def auth_login(remote: bool, timeout: int) -> None:
    """Log in now with the credentials in .env.

    Usually not needed: commands log in automatically when the session
    expires. Use --remote only if the automated login keeps failing
    (needs Xvfb, x11vnc, novnc and ngrok).
    """
    try:
        if remote:
            from .remote_auth import run_remote_login

            run_remote_login(timeout=timeout)
        else:
            click.echo("Logging in to Midtown...", err=True)
            MidtownClient().login()
    except Exception as exc:
        hint = "" if remote else "\nIf it keeps failing, run: midtown auth login --remote"
        raise click.ClickException(f"{exc}{hint}") from exc
    click.echo("Logged in. Session saved.")


@auth.command("logout")
def auth_logout() -> None:
    """Delete the saved session and the browser profile."""
    from . import remote_auth
    from .credentials import SESSION_FILE

    SESSION_FILE.unlink(missing_ok=True)
    if remote_auth.PROFILE_DIR.exists():
        shutil.rmtree(remote_auth.PROFILE_DIR)
    click.echo("Logged out. The next command will log in again with .env.")


@auth.command("status")
@json_option
@click.pass_context
def auth_status(ctx: click.Context) -> None:
    """Show which credential and session files exist."""
    from . import remote_auth
    from .credentials import COOKIES_FILE, ENV_FILE, SESSION_FILE

    output(ctx, {
        "env_file": str(ENV_FILE),
        "env_file_present": ENV_FILE.exists(),
        "session_file": str(SESSION_FILE),
        "session_present": SESSION_FILE.exists(),
        "browser_profile": str(remote_auth.PROFILE_DIR),
        "browser_profile_present": remote_auth.PROFILE_DIR.exists(),
        "imported_cookies_file": str(COOKIES_FILE),
        "imported_cookies_present": COOKIES_FILE.exists(),
    })


# ---------------------------------------------------------------- orders

ORDER_COLUMNS: list[Column] = [
    ("DATE", lambda order: order.get("date"), "<"),
    ("ORDER", lambda order: order.get("order_number"), "<"),
    ("STATUS", lambda order: order.get("status"), "<"),
    ("COMICS", _comics, ">"),
    ("TOTAL", lambda order: order.get("total"), ">"),
]
ITEM_COLUMNS: list[Column] = [
    ("QTY", lambda item: item.get("quantity", 1), ">"),
    ("TITLE", lambda item: item.get("title"), "<"),
    ("PRICE", lambda item: item.get("unit_price"), ">"),
    ("STATUS", lambda item: item.get("status"), "<"),
]


@cli.group(invoke_without_command=True)
@_with_options(period_options)
@json_option
@click.pass_context
def orders(ctx: click.Context) -> None:
    """List your orders (date, number, status, comics, total).

    Filter with --from/--to (YYYY-MM-DD) or summarise with --by-month.
    """
    if ctx.invoked_subcommand is not None:
        return
    result = _orders_in_period(ctx)
    if _grouped_by_month(ctx):
        _output_orders_by_month(ctx, result)
    else:
        output(ctx, result, ORDER_COLUMNS, empty=_empty("No orders", ctx))


@orders.command("show")
@click.argument("order_number")
@json_option
@click.pass_context
def orders_show(ctx: click.Context, order_number: str) -> None:
    """Show one order and its comics."""
    order = _client_call("order", order_number)
    if _wants_json(ctx):
        output(ctx, order)
        return
    click.echo(f"Order {order['order_number']} · {order.get('date', '')} · {order.get('status', '')} · {_money(order.get('total'))}")
    click.echo()
    output(ctx, order.get("items", []), ITEM_COLUMNS, empty="No items found for this order.")


def _order_totals(orders_result: list[dict]) -> dict:
    total = sum(
        (Decimal(str(order["total"])) for order in orders_result if order.get("total") is not None),
        Decimal(0),
    )
    return {"orders": len(orders_result), "comics": sum(map(_comics, orders_result)), "total": float(total)}


def _order_date(order: dict) -> datetime | None:
    try:
        return datetime.strptime(order.get("date", ""), "%m/%d/%Y")  # noqa: DTZ007 - date only
    except ValueError:
        return None


def _order_month(order: dict) -> str:
    placed = _order_date(order)
    return placed.strftime("%Y-%m") if placed else "unknown"


def _option(ctx: click.Context, key: str):
    return (ctx.obj or {}).get(key)


def _empty(subject: str, ctx: click.Context) -> str:
    month = _option(ctx, "by_month") and not _grouped_by_month(ctx)
    filtered = _option(ctx, "date_from") or _option(ctx, "date_to") or month
    return f"{subject} in that date range." if filtered else f"{subject} yet."


def _grouped_by_month(ctx: click.Context) -> bool:
    return _option(ctx, "by_month") == ALL_MONTHS


def _orders_in_period(ctx: click.Context) -> list[dict]:
    """Fetch orders placed between --from and --to (inclusive) and in --by-month YYYY-MM."""
    start, end = _option(ctx, "date_from"), _option(ctx, "date_to")
    month = None if _grouped_by_month(ctx) else _option(ctx, "by_month")
    if start and end and start > end:
        raise click.UsageError("--from must be on or before --to.")
    if not (start or end or month):
        return _client_call("orders")

    def in_period(order: dict) -> bool:
        placed = _order_date(order)
        return (
            placed is not None
            and (not start or placed.date() >= start)
            and (not end or placed.date() <= end)
            and (not month or placed.strftime("%Y-%m") == month)
        )

    return [order for order in _client_call("orders") if in_period(order)]


def _by_month(orders_result: list[dict]) -> list[tuple[str, list[dict]]]:
    months = sorted({_order_month(order) for order in orders_result})
    return [(month, [order for order in orders_result if _order_month(order) == month]) for month in months]


def _output_orders_by_month(ctx: click.Context, orders_result: list[dict]) -> None:
    rows = [{"month": month, **_order_totals(group)} for month, group in _by_month(orders_result)]
    output(ctx, rows, [
        ("MONTH", lambda row: row["month"], "<"),
        ("ORDERS", lambda row: row["orders"], ">"),
        ("COMICS", lambda row: row["comics"], ">"),
        ("TOTAL", lambda row: row["total"], ">"),
    ], empty=_empty("No orders", ctx))


@orders.command("stats")
@_with_options(period_options)
@json_option
@click.pass_context
def orders_stats(ctx: click.Context) -> None:
    """Show how much you have spent, by order status or --by-month.

    Filter with --from/--to (YYYY-MM-DD).
    """
    result = _orders_in_period(ctx)
    if _grouped_by_month(ctx):
        _output_orders_by_month(ctx, result)
        return
    totals = _order_totals(result)
    products = {item.get("product_id") for order in result for item in order.get("items", []) if item.get("product_id")}
    statuses = dict.fromkeys(order.get("status", "") for order in result)
    output(ctx, {
        "orders": totals["orders"],
        "comics": totals["comics"],
        "total_spent": totals["total"],
        "currency": "USD",
        "distinct_products": len(products),
        "by_status": {
            status: _order_totals([order for order in result if order.get("status", "") == status])
            for status in statuses
        },
    })


@orders.command("duplicates")
@json_option
@click.pass_context
def orders_duplicates(ctx: click.Context) -> None:
    """Show comics you bought in more than one order."""
    counts: dict[str, dict] = {}
    for order in _client_call("orders"):
        for item in order.get("items", []):
            key = item.get("product_id") or item.get("title")
            if key:
                seen = counts.get(key, {"product_id": item.get("product_id", ""), "title": item.get("title", ""), "quantity": 0, "orders": 0})
                counts[key] = {**seen, "quantity": seen["quantity"] + item.get("quantity", 1), "orders": seen["orders"] + 1}
    output(ctx, [item for item in counts.values() if item["orders"] > 1], [
        ("TITLE", lambda row: row["title"], "<"),
        ("QTY", lambda row: row["quantity"], ">"),
        ("ORDERS", lambda row: row["orders"], ">"),
    ], empty="No product was bought in more than one order.")


@orders.command("export")
@_with_export_options
def orders_export(format_name: str, output_path: str) -> None:
    """Save your orders to a JSON or CSV file: -o orders.csv --format csv"""
    _write_export(_client_call("orders"), output_path, format_name)


def _comic_items(orders_result: list[dict]) -> list[dict]:
    ordered = sorted(orders_result, key=lambda order: _order_date(order) or datetime.min, reverse=True)  # noqa: DTZ901
    return [
        {"order_number": order.get("order_number", ""), "order_date": order.get("date", ""), **item}
        for order in ordered
        for item in order.get("items", [])
    ]


def _comics_summary(items: list[dict]) -> dict:
    subtotal = sum(
        (Decimal(str(item["unit_price"])) * item.get("quantity", 1) for item in items if item.get("unit_price") is not None),
        Decimal(0),
    )
    return {
        "comics": sum(item.get("quantity", 1) for item in items),
        "distinct": len({item.get("product_id") or item.get("title") for item in items}),
        "subtotal": float(subtotal),
    }


@cli.command()
@_with_options(period_options)
@json_option
@click.pass_context
def comics(ctx: click.Context) -> None:
    """List every comic you have bought, newest first.

    Filter with --from/--to (YYYY-MM-DD) or summarise with --by-month
    (SUBTOTAL is the sum of comic prices, without shipping or tax).
    """
    result = _orders_in_period(ctx)
    if _grouped_by_month(ctx):
        rows = [{"month": month, **_comics_summary(_comic_items(group))} for month, group in _by_month(result)]
        output(ctx, rows, [
            ("MONTH", lambda row: row["month"], "<"),
            ("COMICS", lambda row: row["comics"], ">"),
            ("DISTINCT", lambda row: row["distinct"], ">"),
            ("SUBTOTAL", lambda row: row["subtotal"], ">"),
        ], empty=_empty("No comics", ctx))
        return
    items = _comic_items(result)
    summary = _comics_summary(items)
    output(ctx, items, [
        ("DATE", lambda item: item["order_date"], "<"),
        ("QTY", lambda item: item.get("quantity", 1), ">"),
        ("TITLE", lambda item: item.get("title"), "<"),
        ("PRICE", lambda item: item.get("unit_price"), ">"),
        ("STATUS", lambda item: item.get("status"), "<"),
        ("ORDER", lambda item: item["order_number"], "<"),
    ], empty=_empty("No comics", ctx), footer=f"Total: {summary['comics']} comics · {summary['distinct']} distinct")


# ---------------------------------------------------------------- preorders, wishlist, account


@cli.command()
@json_option
@click.pass_context
def preorders(ctx: click.Context) -> None:
    """List pre-ordered comics not released yet, with release dates.

    Includes pending items of your orders and Midtown Previews pre-orders.
    """
    items = _client_call("preorders")
    quantity = sum(item.get("quantity", 1) for item in items)
    total = sum(
        (Decimal(str(item["unit_price"])) * item.get("quantity", 1) for item in items if item.get("unit_price") is not None),
        Decimal(0),
    )
    output(ctx, items, [
        ("RELEASE", lambda item: item.get("release_date"), "<"),
        ("TITLE", lambda item: item.get("title"), "<"),
        ("QTY", lambda item: item.get("quantity", 1), ">"),
        ("PRICE", lambda item: item.get("unit_price"), ">"),
        ("ORDER", lambda item: item.get("order_number"), "<"),
    ], empty="No pending pre-orders.", footer=f"Total: {quantity} items · ${total:.2f}")


@cli.command()
@json_option
@click.pass_context
def cart(ctx: click.Context) -> None:
    """Show your shopping cart (read-only)."""
    result = _client_call("cart")
    if _wants_json(ctx) or not result["items"]:
        output(ctx, result if _wants_json(ctx) else [], empty="Your cart is empty.")
        return
    output(ctx, result["items"], [
        ("QTY", lambda item: item.get("quantity", 1), ">"),
        ("TITLE", lambda item: item.get("title"), "<"),
        ("PRICE", lambda item: item.get("unit_price"), ">"),
        ("SUBTOTAL", lambda item: round((item.get("unit_price") or 0) * item.get("quantity", 1), 2), ">"),
    ], footer=f"Total: {result['count']} items · {_money(result['total'])}")
    if result.get("free_shipping_remaining"):
        click.echo(f"Spend {_money(result['free_shipping_remaining'])} more for free shipping on comics.")


@cli.group(invoke_without_command=True)
@json_option
@click.pass_context
def wishlist(ctx: click.Context) -> None:
    """List your wishlist with current prices."""
    if ctx.invoked_subcommand is None:
        output(ctx, _client_call("wishlist"), [
            ("TITLE", lambda item: item.get("title"), "<"),
            ("PRICE", lambda item: item.get("price"), ">"),
        ], empty="Your wishlist is empty.")


@wishlist.command("export")
@_with_export_options
def wishlist_export(format_name: str, output_path: str) -> None:
    """Save your wishlist to a JSON or CSV file: -o wishlist.csv --format csv"""
    _write_export(_client_call("wishlist"), output_path, format_name)


@cli.command()
@json_option
@click.pass_context
def account(ctx: click.Context) -> None:
    """Show your profile: name, date of birth and email."""
    output(ctx, _client_call("account"))


# ---------------------------------------------------------------- search


@cli.command()
@click.argument("query")
@click.option("--preorders", is_flag=True, help='Include comics not released yet (site: "Include Pre-orders").')
@click.option("--out-of-stock", is_flag=True, help='Include sold-out comics (site: "Show out of stock").')
@click.option("--per-page", type=click.IntRange(min=1, max=100), default=100, show_default=True,
              help="Results per page (fewer is faster).")
@click.option("--page", type=click.IntRange(min=1), default=1, show_default=True, help="Results page number.")
@json_option
@click.pass_context
def search(ctx: click.Context, query: str, preorders: bool, out_of_stock: bool, per_page: int, page: int) -> None:
    """Search the Midtown Comics catalog.

    Like the website, pre-orders and sold-out comics are hidden unless you add
    --preorders or --out-of-stock.

    \b
    Examples:
      midtown search "spider-man"
      midtown search "absolute batman" --preorders --out-of-stock
      midtown search "x-men" --per-page 20 --page 2
    """
    output(ctx, _client_call("search", query, per_page, page, preorders, out_of_stock), [
        ("TITLE", lambda item: item.get("title"), "<"),
        ("PRICE", lambda item: item.get("price"), ">"),
        ("AVAILABILITY", lambda item: item.get("availability"), "<"),
        ("RELEASE", lambda item: item.get("release_date"), "<"),
    ], empty="No results.")


if __name__ == "__main__":
    cli()
