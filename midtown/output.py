"""Render command results for terminals and machine consumers."""

import json
import shutil
import sys
import unicodedata
from collections.abc import Callable
from decimal import Decimal
from urllib.parse import urlsplit

import click

Column = tuple[str, Callable[[dict], object], str]


def _width(text: str) -> int:
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"${Decimal(str(value)):,.2f}"
    return str(value)


def _fit(text: str, width: int) -> str:
    if _width(text) <= width:
        return text
    result = ""
    for char in text:
        if _width(result + char) > width - 1:
            break
        result += char
    return result + "…" if width > 0 else ""


def _product_url(record: dict, base: str) -> object:
    original = record.get("product_url", "")
    product_id = record.get("product_id")
    try:
        parsed = urlsplit(base)
        if (parsed.scheme == "https" and parsed.netloc == "www.midtowncomics.com"
                and isinstance(product_id, (str, int)) and not isinstance(product_id, bool)
                and str(product_id).isascii() and str(product_id).isdigit() and int(product_id) > 0):
            return f"https://www.midtowncomics.com/product/{product_id}"
    except (ValueError, TypeError):
        pass
    return original


def _print_table(rows: list[dict], columns: list[Column]) -> None:
    headers = [header for header, _, _ in columns]
    cells = [[_cell(getter(row)) for _, getter, _ in columns] for row in rows]
    terminal = max(10, shutil.get_terminal_size((80, 24)).columns)

    def render(names: list[str], data: list[list[str]], aligns: list[str]) -> None:
        widths = [max([_width(name)] + [_width(row[i]) for row in data]) for i, name in enumerate(names)]
        available = terminal - 2 * (len(names) - 1)
        link = next((i for i, name in enumerate(names) if name in {"LINK", "URL"}), None)
        minimum = sum(_width(name) if name == "TITLE" else widths[i] for i, name in enumerate(names))
        if link is not None and minimum > available:
            for index, row in enumerate(data):
                if index:
                    click.echo()
                render([n for i, n in enumerate(names) if i != link],
                       [[v for i, v in enumerate(row) if i != link]],
                       [a for i, a in enumerate(aligns) if i != link])
                if row[link]:
                    click.echo(f"{names[link]}: {row[link]}")
            return
        while sum(widths) > available and "TITLE" in names:
            i = names.index("TITLE")
            if widths[i] <= _width(names[i]):
                break
            widths[i] -= 1
        if sum(widths) > available and names != ["Field", "Value"]:
            for index, row in enumerate(data):
                if index:
                    click.echo()
                render(["Field", "Value"], [[name, value] for name, value in zip(names, row)], ["<", "<"])
            return
        if names == ["Field", "Value"] and sum(widths) > available:
            click.echo("Field  Value")
            for name, value in data:
                click.echo(f"{name}: {value}")
            return

        def line(values: list[str]) -> str:
            parts = []
            for value, width, align in zip(values, widths, aligns):
                fitted = _fit(value, width)
                padding = " " * max(0, width - _width(fitted))
                parts.append(fitted + padding if align == "<" else padding + fitted)
            return "  ".join(parts).rstrip()

        click.echo(line(names))
        for row in data:
            click.echo(line(row))

    render(headers, cells, [align for _, _, align in columns])


def _print_mapping(value: dict) -> None:
    for key, val in value.items():
        if isinstance(val, dict):
            click.echo(f"{key}:")
            for sub_key, sub_val in val.items():
                detail = " | ".join(f"{k}: {v}" for k, v in sub_val.items()) if isinstance(sub_val, dict) else sub_val
                click.echo(f"  {sub_key}: {detail}")
        else:
            click.echo(f"{key}: {val}")


def output(ctx: click.Context, value: list[dict] | dict, columns: list[Column] | None = None,
           empty: str = "", footer: str = "") -> None:
    opts = ctx.find_root().obj or {}
    if opts.get("json") or opts.get("quiet") or not sys.stdout.isatty():
        click.echo(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, dict):
        _print_mapping(value)
    elif not value:
        click.echo(empty)
    else:
        _print_table(value, columns or [])
        if footer:
            click.echo(footer)
