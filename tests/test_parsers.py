
from click.testing import CliRunner

from midtown.cli import cli
from midtown.credentials import load_session
from midtown.parsers import parse_order_detail, parse_orders, parse_wishlist


def test_parse_orders_extracts_order_summary_and_items():
    html = """
    <html><body>
      <div class="order" data-order-number="10042">
        <a href="/order-detail?order=10042">Order #10042</a>
        <span class="date">2026-02-15</span>
        <span class="status">Shipped</span>
        <span class="total">$24.97</span>
        <div class="item" data-product-id="2587261">
          <a href="/p/2587261-example/">Batman Example</a>
          <span class="quantity">2</span>
          <span class="price">$9.99</span>
        </div>
      </div>
    </body></html>
    """

    result = parse_orders(html, "https://www.midtowncomics.com")

    assert result == [
        {
            "order_number": "10042",
            "date": "2026-02-15",
            "status": "Shipped",
            "total": 24.97,
            "currency": "USD",
            "detail_url": "https://www.midtowncomics.com/order-detail?order=10042",
            "items": [
                {
                    "product_id": "2587261",
                    "title": "Batman Example",
                    "quantity": 2,
                    "unit_price": 9.99,
                    "product_url": "https://www.midtowncomics.com/p/2587261-example/",
                }
            ],
        }
    ]


def test_parse_wishlist_extracts_product_cards():
    html = """
    <div class="product-card" data-product-id="123">
      <a class="product-title" href="/p/123-example/">Example Comic</a>
      <span class="price">$4.99</span>
    </div>
    """

    assert parse_wishlist(html, "https://www.midtowncomics.com") == [
        {
            "product_id": "123",
            "title": "Example Comic",
            "price": 4.99,
            "product_url": "https://www.midtowncomics.com/p/123-example/",
        }
    ]



def test_load_session_reads_browser_cookie_json_and_filters_domains(tmp_path, monkeypatch):
    import json

    from midtown import credentials

    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(json.dumps([
        {"domain": "www.midtowncomics.com", "path": "/", "name": "MTSessionID", "value": "session-value"},
        {"domain": "www.midtowncomics.com", "path": "/", "name": "MTLGInfo", "value": "login-value"},
        {"domain": "other.example", "path": "/", "name": "secret", "value": "must-not-load"},
    ]))
    monkeypatch.setattr(credentials, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(credentials, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(credentials, "COOKIES_FILE", cookie_file)

    assert load_session() == {"MTSessionID": "session-value", "MTLGInfo": "login-value"}


def test_load_session_merges_imported_and_refreshed_session_cookies(tmp_path, monkeypatch):
    import json

    from midtown import credentials

    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(json.dumps([
        {"domain": "www.midtowncomics.com", "path": "/", "name": "MTSessionID", "value": "imported"},
    ]))
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps({"cookies": {"MTSessionID": "refreshed", "MTLGInfo": "login"}}))
    monkeypatch.setattr(credentials, "COOKIES_FILE", cookie_file)
    monkeypatch.setattr(credentials, "SESSION_FILE", session_file)

    assert credentials.load_session() == {
        "MTSessionID": "refreshed",
        "MTLGInfo": "login",
    }


def test_load_session_cookie_objects_preserve_scope_and_security_attributes(tmp_path, monkeypatch):
    import json

    from midtown import credentials

    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps({"cookies": [{
        "name": "MTSessionID",
        "value": "session-value",
        "domain": "www.midtowncomics.com",
        "path": "/account",
        "expires": 1790000000,
        "httpOnly": True,
        "secure": True,
        "sameSite": "Lax",
    }]}))
    monkeypatch.setattr(credentials, "COOKIES_FILE", tmp_path / "missing-cookies.json")
    monkeypatch.setattr(credentials, "SESSION_FILE", session_file)

    assert credentials.load_session_cookies() == [{
        "name": "MTSessionID",
        "value": "session-value",
        "domain": "www.midtowncomics.com",
        "path": "/account",
        "expires": 1790000000,
        "httpOnly": True,
        "secure": True,
        "sameSite": "Lax",
    }]


def test_parse_midtown_account_order_tables():
    html = """
    <div id="my-orders">
      <div aria-label="In Processed Orders">
        <h3>Orders in Process</h3>
        <table id="tbl-orders"><tbody>
          <tr><td class="tbl-date">10/1/2026</td><td class="tbl-order"><a href="javascript:ord_info(4349113,'0');">4349113</a></td><td class="tbl-total">$19.43</td></tr>
        </tbody></table>
      </div>
      <br>
      <div aria-label="Processed and Shipped Orders">
        <h3>Orders Processed / Shipped &amp; Completed</h3>
        <table id="tbl-processed"><tbody>
          <tr><td class="tbl-date">9/30/2026</td><td class="tbl-order"><a href="javascript:ord_info(4347572,'0');">4347572</a></td><td class="tbl-total">$27.01</td><td class="tbl-track"></td></tr>
        </tbody></table>
      </div>
    </div>
    """

    result = parse_orders(html, "https://www.midtowncomics.com")

    assert result == [
        {"order_number": "4349113", "date": "10/1/2026", "status": "In Process", "total": 19.43, "currency": "USD", "detail_url": "", "items": []},
        {"order_number": "4347572", "date": "9/30/2026", "status": "Processed / Shipped & Completed", "total": 27.01, "currency": "USD", "detail_url": "", "items": []},
    ]


def test_parse_midtown_wishlist_cards():
    html = """
    <div id="divWL"><ul id="sortable">
      <li><div class="wish-card">
        <a href="https://www.midtowncomics.com/product/2576768"><h4>Example Comic</h4></a>
        <p class="strike regular">$4.99</p><p class="bold discount">$3.99</p>
        <button id="btnRemove_2576768">REMOVE</button>
      </div></li>
    </ul></div>
    """

    assert parse_wishlist(html, "https://www.midtowncomics.com") == [
        {"product_id": "2576768", "title": "Example Comic", "price": 3.99, "product_url": "https://www.midtowncomics.com/product/2576768"}
    ]


def test_remote_auth_ignores_non_midtown_pages_and_finds_authenticated_tab():
    from midtown.remote_auth import _authenticated_page

    class Locator:
        def __init__(self, count):
            self._count = count

        def count(self):
            return self._count

    class Page:
        def __init__(self, url, password_fields):
            self.url = url
            self.password_fields = password_fields

        def locator(self, _selector):
            return Locator(self.password_fields)

    class Context:
        pages = [
            Page("about:blank", 0),
            Page("https://www.midtowncomics.com/login", 1),
            Page("https://www.midtowncomics.com/account-settings", 0),
        ]

    assert _authenticated_page(Context()).url.endswith("/account-settings")


def test_remote_auth_does_not_treat_unrelated_page_as_authenticated():
    from midtown.remote_auth import _is_authenticated

    class Locator:
        def count(self):
            return 0

    class Page:
        url = "about:blank"

        def locator(self, _selector):
            return Locator()

    assert _is_authenticated(Page()) is False


def test_remote_auth_saves_complete_playwright_cookie_objects(tmp_path, monkeypatch):
    import json

    from midtown import credentials
    from midtown.remote_auth import _save_context_cookies

    session_file = tmp_path / "session.json"
    monkeypatch.setattr(credentials, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(credentials, "SESSION_FILE", session_file)

    class Context:
        def cookies(self, urls=None):
            assert urls == ["https://www.midtowncomics.com/ord-contents"]
            return [
                {
                    "name": "MTSessionID",
                    "value": "session-value",
                    "domain": "www.midtowncomics.com",
                    "path": "/",
                    "expires": -1,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                },
                {
                    "name": "unrelated",
                    "value": "must-not-save",
                    "domain": "other.example",
                    "path": "/",
                },
            ]

    _save_context_cookies(Context())
    saved = json.loads(session_file.read_text())
    assert saved["cookies"] == [
        {
            "name": "MTSessionID",
            "value": "session-value",
            "domain": "www.midtowncomics.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }
    ]
    assert oct(session_file.stat().st_mode & 0o777) == "0o600"


def test_remote_auth_saves_cookies_only_after_orders_endpoint_validation(monkeypatch):
    from midtown import remote_auth

    class Response:
        def __init__(self, url, text):
            self.url = url
            self._text = text

        def text(self):
            return self._text

    class Request:
        def __init__(self, response):
            self.response = response

        def post(self, url, timeout):
            assert url == "https://www.midtowncomics.com/ord-contents"
            assert timeout == 30_000
            return self.response

    class Context:
        def __init__(self, response):
            self.request = Request(response)

    saved = []
    monkeypatch.setattr(remote_auth, "_save_context_cookies", lambda context: saved.append(context))

    stale = Context(Response("https://www.midtowncomics.com/login", '<input name="txtPassword">'))
    assert remote_auth._save_validated_context_cookies(stale) is False
    assert saved == []

    authenticated = Context(Response("https://www.midtowncomics.com/ord-contents", "<div id='tbl-orders'>orders</div>"))
    assert remote_auth._save_validated_context_cookies(authenticated) is True
    assert saved == [authenticated]


def test_cli_exposes_logical_command_groups():
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0, result.output
    commands = result.output.split("Commands:")[1].split()
    for command in ("account", "auth", "orders", "preorders", "search", "wishlist"):
        assert command in commands
    for removed in ("collection", "doctor", "product"):
        assert removed not in commands


def test_orders_stats_reports_order_comic_and_spend_totals(monkeypatch):
    import midtown.cli as cli_module

    monkeypatch.setattr(
        cli_module.MidtownClient,
        "orders",
        lambda self: [
            {"order_number": "1", "status": "Shipped", "total": 10.50, "items": [{"quantity": 2}]},
            {"order_number": "2", "status": "In Process", "total": 5.25, "items": [{"quantity": 1}, {"quantity": 3}]},
        ],
    )

    result = CliRunner().invoke(cli, ["orders", "stats", "--json"])

    assert result.exit_code == 0, result.output
    import json

    assert json.loads(result.output) == {
        "orders": 2,
        "comics": 6,
        "total_spent": 15.75,
        "currency": "USD",
        "distinct_products": 0,
        "by_status": {
            "Shipped": {"orders": 1, "comics": 2, "total": 10.5},
            "In Process": {"orders": 1, "comics": 4, "total": 5.25},
        },
    }


def test_orders_stats_by_month_groups_spend_chronologically(monkeypatch):
    import json

    import midtown.cli as cli_module

    monkeypatch.setattr(
        cli_module.MidtownClient,
        "orders",
        lambda self: [
            {"order_number": "3", "date": "10/1/2026", "status": "Shipped", "total": 19.43, "items": [{"quantity": 6}]},
            {"order_number": "2", "date": "9/30/2026", "status": "In Process", "total": 11.98, "items": [{"quantity": 2}]},
            {"order_number": "1", "date": "9/20/2026", "status": "Shipped", "total": 10.47, "items": [{"quantity": 3}]},
        ],
    )

    result = CliRunner().invoke(cli, ["--json", "orders", "stats", "--by-month"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {"month": "2026-09", "orders": 2, "comics": 5, "total": 22.45},
        {"month": "2026-10", "orders": 1, "comics": 6, "total": 19.43},
    ]


def test_orders_export_writes_csv(monkeypatch, tmp_path):
    import midtown.cli as cli_module

    monkeypatch.setattr(
        cli_module.MidtownClient,
        "orders",
        lambda self: [{"order_number": "1", "date": "2026-01-01", "status": "Shipped", "total": 10.50, "items": []}],
    )

    output = tmp_path / "orders.csv"
    result = CliRunner().invoke(cli, ["orders", "export", "--format", "csv", "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert "order_number,date,status,total" in output.read_text()
    assert "1,2026-01-01,Shipped,10.5" in output.read_text()


def _client_with_responses(monkeypatch, tmp_path, responses):
    import midtown.client as client_module
    from midtown import credentials

    monkeypatch.setattr(credentials, "COOKIES_FILE", tmp_path / "cookies.json")
    monkeypatch.setattr(credentials, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(client_module, "parse_orders", lambda html, base: [])
    client = client_module.MidtownClient()
    posted = []

    def fake_post(url, timeout, **kwargs):
        posted.append(url)
        response = responses.pop(0)
        response.raise_for_status = lambda: None
        return response

    monkeypatch.setattr(client.session, "post", fake_post)
    return client, posted


def test_client_logs_in_automatically_and_retries_when_session_expired(monkeypatch, tmp_path):
    from types import SimpleNamespace

    login_page = SimpleNamespace(url="https://www.midtowncomics.com/login", text='<input name="txtPassword">')
    orders_page = SimpleNamespace(url="https://www.midtowncomics.com/ord-contents", text="<table></table>")
    client, posted = _client_with_responses(monkeypatch, tmp_path, [login_page, orders_page])
    logins = []
    monkeypatch.setattr(client, "login", lambda: logins.append(True))

    assert client.orders() == []
    assert logins == [True]
    assert posted == ["https://www.midtowncomics.com/ord-contents"] * 2


def test_client_reports_error_when_session_still_invalid_after_login(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import pytest

    login_page = SimpleNamespace(url="https://www.midtowncomics.com/login", text='<input name="txtPassword">')
    client, _ = _client_with_responses(monkeypatch, tmp_path, [login_page, login_page])
    monkeypatch.setattr(client, "login", lambda: None)

    with pytest.raises(RuntimeError, match="not authenticated"):
        client.orders()


def test_client_persists_cookie_objects_with_domain(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace

    orders_page = SimpleNamespace(url="https://www.midtowncomics.com/ord-contents", text="<table></table>")
    client, _ = _client_with_responses(monkeypatch, tmp_path, [orders_page])
    client.session.cookies.set("MTSessionID", "abc", domain="www.midtowncomics.com", path="/", secure=True)

    client.orders()

    saved = json.loads((tmp_path / "session.json").read_text())["cookies"]
    assert saved == [{
        "name": "MTSessionID", "value": "abc", "domain": "www.midtowncomics.com",
        "path": "/", "secure": True, "expires": -1,
    }]



def test_parse_midtown_order_detail_items():
    html = """
    <div id="info-header"><h2>Order # 4349113</h2></div>
    <div class="order-item">
      <img src="/images/PRODUCT/FUL/1726540_ful.jpg" />
      <div aria-label="Amazing Spider-Man Example" class="col-10">
        <h3>Amazing Spider-Man Example</h3><h3>Marvel</h3>
        <p><span>Each:</span> $2.63</p>
        <div><p><span>Total:</span> $2.63</p><p><span>QTY:</span> 1</p></div>
        <p><span>Condition:</span> Near Mint</p>
        <h3>Status: Pending</h3>
      </div>
    </div>
    """

    assert parse_order_detail(html, "https://www.midtowncomics.com") == [
        {
            "product_id": "1726540",
            "title": "Amazing Spider-Man Example",
            "quantity": 1,
            "unit_price": 2.63,
            "product_url": "https://www.midtowncomics.com/product/1726540",
            "status": "Pending",
        }
    ]


def test_read_credentials_from_env_file(tmp_path, monkeypatch):
    from midtown import credentials

    env_file = tmp_path / ".env"
    env_file.write_text('# Midtown\nMIDTOWN_EMAIL=reader@example.com\nMIDTOWN_PASSWORD="p@ss=word"\n')
    monkeypatch.delenv("MIDTOWN_EMAIL", raising=False)
    monkeypatch.delenv("MIDTOWN_PASSWORD", raising=False)
    monkeypatch.setattr(credentials, "ENV_FILE", env_file)

    assert credentials.read_credentials() == ("reader@example.com", "p@ss=word")


def test_parse_release_date_from_product_page():
    from midtown.parsers import parse_release_date

    html = """<dl><dt>Art  by</dt><dd>X</dd>
        <dt>Release Date</dt>
        <dd><a href="/search?sd=10/7/2026"><span id="artist">10/7/2026</span></a></dd></dl>
        <p>* Release Date and Covers are subject to change</p>"""

    assert parse_release_date(html) == "10/7/2026"
    assert parse_release_date("<html>no date</html>") == ""


def test_parse_preview_items_reads_rows_by_section_and_skips_empty_tables():
    from midtown.parsers import parse_preview_items

    header = """<thead><tr><th>Order Date</th><th>Order #</th><th>Title</th><th>QTY</th>
        <th>Release Date</th><th>Price Each</th></tr></thead>"""
    html = f"""<div id="my-orders">
        <div><h3 class="blue">Pending Items</h3><table>{header}<tbody>
            <tr><td>9/1/2026</td><td>900001</td><td><a href="/product/2600001">Batman #200</a></td>
            <td>2</td><td>12/2/2026</td><td>$4.99</td></tr></tbody></table></div>
        <div><h3 class="blue">Cancelled Items</h3><table>{header}<tbody>
            <tr><td colspan="6">No data found.</td></tr></tbody></table></div></div>"""

    assert parse_preview_items(html, "https://www.midtowncomics.com") == [{
        "source": "previews",
        "order_number": "900001",
        "order_date": "9/1/2026",
        "product_id": "2600001",
        "title": "Batman #200",
        "quantity": 2,
        "unit_price": 4.99,
        "release_date": "12/2/2026",
        "status": "Pending",
        "product_url": "https://www.midtowncomics.com/product/2600001",
    }]


def test_client_preorders_combines_pending_order_items_and_previews(monkeypatch):
    from types import SimpleNamespace

    import midtown.client as client_module

    client = client_module.MidtownClient.__new__(client_module.MidtownClient)
    client.base_url = "https://www.midtowncomics.com"
    monkeypatch.setattr(client, "orders", lambda: [
        {"order_number": "1", "date": "9/30/2026", "items": [
            {"product_id": "10", "title": "Pending Comic", "quantity": 1, "unit_price": 5.99,
             "product_url": "https://www.midtowncomics.com/product/10", "status": "Pending"},
            {"product_id": "11", "title": "Shipped Comic", "quantity": 1, "unit_price": 3.99,
             "product_url": "https://www.midtowncomics.com/product/11", "status": "Shipped"},
        ]},
    ])
    monkeypatch.setattr(client, "_post_authenticated", lambda path: SimpleNamespace(text="<html></html>"))
    monkeypatch.setattr(client, "_release_date", lambda product_id: "10/7/2026")

    assert client.preorders() == [{
        "source": "order",
        "order_number": "1",
        "order_date": "9/30/2026",
        "product_id": "10",
        "title": "Pending Comic",
        "quantity": 1,
        "unit_price": 5.99,
        "release_date": "10/7/2026",
        "status": "Pending",
        "product_url": "https://www.midtowncomics.com/product/10",
    }]



def test_parse_search_reports_availability_and_release_date():
    from midtown.parsers import parse_search

    def card(product_id, select_label):
        return f"""<div id="main-record-{product_id}" class="product-card">
            <div class="product-title"><a href="/p/{product_id}-x/"><h3>Comic {product_id}</h3></a></div>
            <div class="product-publisher"><dl><dt>By</dt><dd><span class="pc-publisher">DC</span></dd>
            <dt>Release Date</dt><dd><a href="/search?sd=01/06/2027"><span class="blue">01/06/2027*</span></a></dd></dl></div>
            <p class="pc-discounted">$4.79</p>
            <select aria-label="{select_label}" class="qty"></select></div>"""

    html = card(1, "Pre Order") + card(2, "Add to Cart") + card(3, "Wishlist")
    results = parse_search(html, "https://www.midtowncomics.com")

    assert [(r["product_id"], r["availability"], r["release_date"]) for r in results] == [
        ("1", "pre-order", "01/06/2027"),
        ("2", "in stock", "01/06/2027"),
        ("3", "out of stock", "01/06/2027"),
    ]


def test_search_sends_filters_only_when_enabled(monkeypatch):
    import midtown.client as client_module

    sent = []

    class Response:
        text = ""

        def raise_for_status(self):
            return None

    client = client_module.MidtownClient.__new__(client_module.MidtownClient)
    client.base_url = "https://www.midtowncomics.com"
    client.session = type("S", (), {"get": lambda self, url, params, timeout: sent.append(params) or Response()})()

    client.search("batman")
    client.search("batman", include_preorders=True, show_out_of_stock=True)

    assert sent == [
        {"q": "batman", "pp": 100, "pj": 1},
        {"q": "batman", "pp": 100, "pj": 1, "rel": 1, "os": 1},
    ]


def test_search_completes_lazy_loaded_cards_with_product_body(monkeypatch):
    import midtown.client as client_module

    lazy_card = """<div id="main-record-77" class="product-card">
        <div class="product-title"><a href="/p/77-x/"><h3>Lazy Comic</h3></a></div>
        <div class="cart-container"><img src="/images/ajax-loader-small.gif"></div></div>"""
    body = """<p class="pc-discounted">$4.95</p><select aria-label="Pre Order" class="qty"></select>"""
    calls = []

    class Response:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class Session:
        def get(self, url, params, timeout):
            return Response(lazy_card)

        def post(self, url, data, timeout):
            calls.append((url, data))
            return Response(body)

    client = client_module.MidtownClient.__new__(client_module.MidtownClient)
    client.base_url = "https://www.midtowncomics.com"
    client.session = Session()

    [product] = client.search("lazy")

    assert calls == [("https://www.midtowncomics.com/search-load-product-body", {"pr_parentid": "77", "pr_id": "77"})]
    assert (product["price"], product["availability"]) == (4.95, "pre-order")


def test_parse_account_profile_reads_fields_and_never_password():
    from midtown.parsers import parse_account_profile

    html = """<div class="account-details" id="act-profile"><table>
        <tr><td><p>Name:</p></td><td><p><span id="account-name">Peter Parker</span></p></td></tr>
        <tr><td><p>Date of Birth:</p></td><td><p><span id="account-dob">08/10/2001</span></p></td></tr>
        <tr><td><p>E-mail:</p></td><td><p><span id="account-email">peter@example.com</span></p></td></tr>
        <tr><td><p>Password:</p></td><td><p><span id="account-pass">**********</span></p></td></tr>
    </table></div>"""

    assert parse_account_profile(html) == {
        "name": "Peter Parker",
        "date_of_birth": "08/10/2001",
        "email": "peter@example.com",
    }


def test_account_show_cli_uses_authenticated_settings_endpoint(monkeypatch):
    import json

    import midtown.cli as cli_module

    monkeypatch.setattr(
        cli_module.MidtownClient,
        "account",
        lambda self: {"name": "Peter Parker", "date_of_birth": "08/10/2001", "email": "peter@example.com"},
    )

    result = CliRunner().invoke(cli, ["account", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["email"] == "peter@example.com"


def _fake_client(monkeypatch, **methods):
    import midtown.cli as cli_module

    monkeypatch.setattr(cli_module, "MidtownClient", lambda: type("FakeClient", (), {
        name: (lambda self, *args, _value=value, **kwargs: _value(*args, **kwargs) if callable(_value) else _value)
        for name, value in methods.items()
    })())


def test_preorders_prints_table_with_total_footer(monkeypatch):
    _fake_client(monkeypatch, preorders=[
        {"title": "Midnight Spider-Man #1", "quantity": 2, "unit_price": 5.99, "release_date": "10/7/2026", "order_number": "4347877"},
        {"title": "Midnight X-Men #1", "quantity": 1, "unit_price": 3.99, "release_date": "10/14/2026", "order_number": "4347877"},
    ])

    result = CliRunner().invoke(cli, ["preorders"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].split() == ["RELEASE", "TITLE", "QTY", "PRICE", "ORDER"]
    assert lines[1].split()[0] == "10/7/2026"
    assert "Midnight Spider-Man #1" in lines[1]
    assert lines[-1] == "Total: 3 items · $15.97"


def test_list_commands_say_when_there_is_nothing(monkeypatch):
    _fake_client(monkeypatch, preorders=[], wishlist=[], orders=[])

    assert CliRunner().invoke(cli, ["preorders"]).output.strip() == "No pending pre-orders."
    assert CliRunner().invoke(cli, ["wishlist"]).output.strip() == "Your wishlist is empty."
    assert CliRunner().invoke(cli, ["orders", "duplicates"]).output.strip() == "No product was bought in more than one order."


def test_orders_duplicates_counts_products_across_orders(monkeypatch):
    import json

    _fake_client(monkeypatch, orders=[
        {"order_number": "1", "items": [{"product_id": "10", "title": "Batman #1", "quantity": 1}]},
        {"order_number": "2", "items": [{"product_id": "10", "title": "Batman #1", "quantity": 2},
                                         {"product_id": "11", "title": "Robin #1", "quantity": 1}]},
    ])

    result = CliRunner().invoke(cli, ["orders", "duplicates", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [{"product_id": "10", "title": "Batman #1", "quantity": 3, "orders": 2}]


def test_orders_show_fetches_only_the_requested_order(monkeypatch):
    calls = []
    order = {"order_number": "7", "date": "9/30/2026", "status": "In Process", "total": 5.99,
             "items": [{"title": "Batman #1", "quantity": 1, "unit_price": 5.99, "status": "Pending"}]}
    _fake_client(monkeypatch, order=lambda number: calls.append(number) or order)

    result = CliRunner().invoke(cli, ["orders", "show", "7"])

    assert result.exit_code == 0, result.output
    assert calls == ["7"]
    assert "Order 7 · 9/30/2026 · In Process · $5.99" in result.output
    assert "Batman #1" in result.output


def test_client_order_requests_detail_of_one_order(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import midtown.client as client_module

    client = client_module.MidtownClient.__new__(client_module.MidtownClient)
    client.base_url = "https://www.midtowncomics.com"
    posted = []
    monkeypatch.setattr(client, "_post_authenticated", lambda path: SimpleNamespace(text="list"))
    monkeypatch.setattr(client_module, "parse_orders", lambda html, base: [{"order_number": "1"}, {"order_number": "2"}])
    monkeypatch.setattr(client, "_order_items", lambda number: posted.append(number) or [])
    monkeypatch.setattr(client, "_save_cookies", lambda: None)

    assert client.order("2") == {"order_number": "2", "items": []}
    assert posted == ["2"]
    import pytest

    with pytest.raises(RuntimeError, match="Order not found: 9"):
        client.order("9")


def test_auth_logout_removes_session_and_browser_profile(tmp_path, monkeypatch):
    from midtown import credentials, remote_auth

    session = tmp_path / "session.json"
    session.write_text("{}")
    profile = tmp_path / "browser-profile"
    (profile / "Default").mkdir(parents=True)
    monkeypatch.setattr(credentials, "SESSION_FILE", session)
    monkeypatch.setattr(remote_auth, "PROFILE_DIR", profile)

    result = CliRunner().invoke(cli, ["auth", "logout"])

    assert result.exit_code == 0, result.output
    assert not session.exists()
    assert not profile.exists()


def test_auth_login_remote_uses_remote_browser(monkeypatch):
    from midtown import remote_auth

    calls = []
    monkeypatch.setattr(remote_auth, "run_remote_login", lambda timeout: calls.append(timeout))

    result = CliRunner().invoke(cli, ["auth", "login", "--remote"])

    assert result.exit_code == 0, result.output
    assert calls == [900]


def test_search_short_filter_flags(monkeypatch):
    calls = []
    _fake_client(monkeypatch, search=lambda *args: calls.append(args) or [])

    result = CliRunner().invoke(cli, ["search", "batman", "--preorders", "--out-of-stock"])

    assert result.exit_code == 0, result.output
    assert calls == [("batman", 100, 1, True, True)]
    assert result.output.strip() == "No results."


def test_client_warns_before_automatic_login(monkeypatch, tmp_path, caplog):
    from types import SimpleNamespace

    login_page = SimpleNamespace(url="https://www.midtowncomics.com/login", text='<input name="txtPassword">')
    orders_page = SimpleNamespace(url="https://www.midtowncomics.com/ord-contents", text="<table></table>")
    client, _ = _client_with_responses(monkeypatch, tmp_path, [login_page, orders_page])
    monkeypatch.setattr(client, "login", lambda: None)

    client.orders()

    assert "Logging in to Midtown" in caplog.text


def test_help_command_shows_root_and_nested_help():
    root = CliRunner().invoke(cli, ["help"])
    assert root.exit_code == 0, root.output
    assert root.output == CliRunner().invoke(cli, ["--help"]).output

    nested = CliRunner().invoke(cli, ["help", "orders", "stats"], prog_name="midtown")
    assert nested.exit_code == 0, nested.output
    assert nested.output.startswith("Usage: midtown orders stats [OPTIONS]")
    assert "--by-month" in nested.output

    unknown = CliRunner().invoke(cli, ["help", "orders", "nope"])
    assert unknown.exit_code != 0
    assert "No such command: orders nope" in unknown.output


def test_comics_lists_every_purchased_comic_newest_first(monkeypatch):
    import json

    _fake_client(monkeypatch, orders=[
        {"order_number": "1", "date": "9/20/2026", "items": [
            {"product_id": "10", "title": "Batman #1", "quantity": 1, "unit_price": 3.99, "status": "Shipped"}]},
        {"order_number": "2", "date": "10/1/2026", "items": [
            {"product_id": "10", "title": "Batman #1", "quantity": 1, "unit_price": 3.99, "status": "Shipped"},
            {"product_id": "11", "title": "Robin #1", "quantity": 2, "unit_price": 4.99, "status": "Pending"}]},
    ])

    text = CliRunner().invoke(cli, ["comics"])
    assert text.exit_code == 0, text.output
    lines = text.output.splitlines()
    assert lines[0].split() == ["DATE", "QTY", "TITLE", "PRICE", "STATUS", "ORDER"]
    assert lines[1].split()[:2] == ["10/1/2026", "1"]
    assert lines[3].split()[0] == "9/20/2026"
    assert lines[-1] == "Total: 4 comics · 2 distinct"

    data = json.loads(CliRunner().invoke(cli, ["comics", "--json"]).output)
    assert data[2] == {"order_number": "1", "order_date": "9/20/2026", "product_id": "10",
                       "title": "Batman #1", "quantity": 1, "unit_price": 3.99, "status": "Shipped"}


def test_comics_says_when_there_are_none(monkeypatch):
    _fake_client(monkeypatch, orders=[])

    assert CliRunner().invoke(cli, ["comics"]).output.strip() == "No comics yet."


PERIOD_ORDERS = [
    {"order_number": "3", "date": "10/1/2026", "status": "Shipped", "total": 19.43, "items": [
        {"product_id": "30", "title": "Hulk #1", "quantity": 2, "unit_price": 4.00, "status": "Shipped"}]},
    {"order_number": "2", "date": "9/30/2026", "status": "In Process", "total": 11.98, "items": [
        {"product_id": "20", "title": "Thor #1", "quantity": 1, "unit_price": 5.99, "status": "Pending"}]},
    {"order_number": "1", "date": "9/20/2026", "status": "Shipped", "total": 10.47, "items": [
        {"product_id": "10", "title": "Batman #1", "quantity": 3, "unit_price": 2.99, "status": "Shipped"}]},
]


def test_orders_by_month_works_on_list_and_stats(monkeypatch):
    import json

    _fake_client(monkeypatch, orders=PERIOD_ORDERS)
    expected = [
        {"month": "2026-09", "orders": 2, "comics": 4, "total": 22.45},
        {"month": "2026-10", "orders": 1, "comics": 2, "total": 19.43},
    ]

    for args in (["orders", "--by-month", "--json"], ["orders", "stats", "--by-month", "--json"]):
        result = CliRunner().invoke(cli, args)
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == expected


def test_comics_by_month_summarises_items(monkeypatch):
    import json

    _fake_client(monkeypatch, orders=PERIOD_ORDERS)

    result = CliRunner().invoke(cli, ["comics", "--by-month", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {"month": "2026-09", "comics": 4, "distinct": 2, "subtotal": 14.96},
        {"month": "2026-10", "comics": 2, "distinct": 1, "subtotal": 8.0},
    ]
    text = CliRunner().invoke(cli, ["comics", "--by-month"]).output.splitlines()
    assert text[0].split() == ["MONTH", "COMICS", "DISTINCT", "SUBTOTAL"]


def test_date_range_filters_orders_stats_and_comics_inclusively(monkeypatch):
    import json

    _fake_client(monkeypatch, orders=PERIOD_ORDERS)
    period = ["--from", "2026-09-30", "--to", "2026-10-01", "--json"]

    listed = json.loads(CliRunner().invoke(cli, ["orders", *period]).output)
    assert [order["order_number"] for order in listed] == ["3", "2"]

    stats = json.loads(CliRunner().invoke(cli, ["orders", "stats", *period]).output)
    assert (stats["orders"], stats["total_spent"]) == (2, 31.41)

    comics = json.loads(CliRunner().invoke(cli, ["comics", "--from", "2026-10-01", "--json"]).output)
    assert [item["title"] for item in comics] == ["Hulk #1"]

    before = json.loads(CliRunner().invoke(cli, ["comics", "--to", "2026-09-20", "--json"]).output)
    assert [item["title"] for item in before] == ["Batman #1"]

    monthly = json.loads(CliRunner().invoke(cli, ["orders", "--by-month", "--from", "2026-09-25", "--json"]).output)
    assert monthly == [
        {"month": "2026-09", "orders": 1, "comics": 1, "total": 11.98},
        {"month": "2026-10", "orders": 1, "comics": 2, "total": 19.43},
    ]


def test_date_range_rejects_bad_input(monkeypatch):
    _fake_client(monkeypatch, orders=PERIOD_ORDERS)

    bad_format = CliRunner().invoke(cli, ["orders", "--from", "30/09/2026"])
    assert bad_format.exit_code != 0
    assert "YYYY-MM-DD" in bad_format.output

    reversed_range = CliRunner().invoke(cli, ["comics", "--from", "2026-10-01", "--to", "2026-09-01"])
    assert reversed_range.exit_code != 0
    assert "--from must be on or before --to" in reversed_range.output
