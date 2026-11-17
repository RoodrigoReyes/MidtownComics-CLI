import click

from midtown.cli import _wants_json
from midtown.output import _fit, _print_table, _product_url, _width


def test_display_width():
    assert _width('e\u0301界') == 3
    assert _fit('é界a', 3) == 'é…'
    assert _width(_fit('界界', 3)) == 3


def test_narrow_table_preserves_values(monkeypatch, capsys):
    monkeypatch.setattr('midtown.output.shutil.get_terminal_size', lambda *_: __import__('os').terminal_size((15, 24)))
    _print_table([{'status': 'Awaiting shipment', 'title': 'A comic'}], [
        ('TITLE', lambda row: row['title'], '<'), ('STATUS', lambda row: row['status'], '<')])
    text = capsys.readouterr().out
    assert 'Field  Value' in text and 'TITLE' in text and 'Awaiting shipment' in text


def test_redirected_stdout_is_json(monkeypatch):
    monkeypatch.setattr('sys.stdout.isatty', lambda: False)
    assert _wants_json(click.Context(click.Command('test')))


def test_product_url():
    record = {'product_id': '42', 'product_url': 'original'}
    assert _product_url(record, 'https://www.midtowncomics.com') == 'https://www.midtowncomics.com/product/42'
    assert _product_url(record, 'https://example.com') == 'original'
    assert _product_url({**record, 'product_id': 0}, 'https://www.midtowncomics.com') == 'original'
