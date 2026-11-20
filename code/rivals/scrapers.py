"""
scrapers.py — Part 1, Step 2: one scraper per rival café.

Each scraper is handed a Playwright `page` (an open browser tab) and returns a
list of dicts, one per menu item *and size*, all with the same keys:

    {"cafe": ..., "category": ..., "item": ..., "size": ..., "price": ...}

Every café names its drink sizes S, M and L — Lakeshore pours only S and L — and
food has one price, "Each".

The three sites are built differently on purpose, so each scraper uses a
different technique from Unit 5. Before you write one, open the café in Chrome
(settings.cafe_url) and right-click → Inspect the parts you need.

The steps are described in words. You write the code.
"""

from io import StringIO
from urllib.parse import urljoin

import pandas as pd

from .cleaning import card_rows, clean_price
from .settings import CANAL_SHOP, cafe_url


def scrape_lakeshore(page) -> list[dict]:
    """Lakeshore Lattes: section headings, each followed by a grid of menu cards.

    Returns card_rows() for every card — one row per size.

    The page, simplified:

        <h2 class="menu-section__title">Tea & More</h2>
        <p class="menu-section__note">Swap in oat milk for 60¢.</p>
        <div class="menu-grid">
            <article class="menu-card"> ... </article>
            ...

    How to build it:

    - `page.goto(cafe_url("Lakeshore Lattes"))`.
    - For each heading in `page.query_selector_all("h2.menu-section__title")`:
        - its `inner_text()` is the category.
        - the grid is a *later sibling* of the heading — `heading.query_selector("~
          div.menu-grid")` (lesson 5-2's `~` selector; `~ *` would find the note).
        - for each `article.menu-card` in the grid: `card_rows("Lakeshore Lattes",
          category, card.inner_text())` — add its rows to your list.
    - Return all the rows in one list. (The cards have photos; you don't need them.)
    """
    page.goto(cafe_url("Lakeshore Lattes"))

    rows = []

    headings = page.query_selector_all("h2.menu-section__title")

    for heading in headings:
        category = heading.inner_text().strip()

        # Walk forward through the siblings until we reach the menu grid
        grid_handle = heading.evaluate_handle("""
            h => {
                let el = h.nextElementSibling;
                while (el && !el.matches('div.menu-grid')) {
                    el = el.nextElementSibling;
                }
                return el;
            }
        """)
        grid = grid_handle.as_element()

        if grid is None:
            continue

        for card in grid.query_selector_all("article.menu-card"):
            rows.extend(
                card_rows("Lakeshore Lattes", category, card.inner_text())
            )

    return rows


def scrape_hilltop(page) -> list[dict]:
    """Hilltop Grind: inside `<div id="menu">`, an `<h2>` and a `<table>` per category.

    Drink tables have a column per size; food tables have one "Each" column:

        Item           Description                  S      M      L
        Drip Coffee    Our rotating single-origin…  $2.15  $2.60  $3.05

        Item           Description                  Each
        Avocado Toast  Smashed avocado, lemon…      $7.95

    How to build it:

    - `page.goto(cafe_url("Hilltop Grind"))`.
    - The categories: the `inner_text()` of every `#menu h2` (an id selector), in order.
    - The tables: `pd.read_html(StringIO(page.content()))` reads every `<table>` on
      the page into a list of DataFrames, in the same order as the headings.
    - For each (category, table) pair (`zip()`): drop the "Description" column, then
      `.melt()` the table so each size column becomes rows — `id_vars="Item",
      var_name="size", value_name="price"`.
    - Turn each melted row into a dict with the five keys; `clean_price()` the price.
    """
    page.goto(cafe_url("Hilltop Grind"))

    categories = [
        heading.inner_text().strip()
        for heading in page.query_selector_all("#menu h2")
    ]
    tables = pd.read_html(StringIO(page.content()))

    rows = []
    for category, table in zip(categories, tables):
        table = table.drop(columns=["Description"])
        melted = table.melt(id_vars="Item", var_name="size", value_name="price")

        for item in melted.itertuples(index=False):
            rows.append({
                "cafe": "Hilltop Grind",
                "category": category,
                "item": item.Item,
                "size": item.size,
                "price": clean_price(item.price),
            })

    return rows


def scrape_canal(page, shop: str = CANAL_SHOP) -> list[dict]:
    """Canal Street Coffee: an order-ahead app. The menu is not in the HTML.

    A person has to choose a shop, ask for the menu, and click "Show more" until
    every item is listed. The list shows only names — each item's sizes and
    prices are on its own page. The page's JavaScript draws all of it, slowly,
    so your code has to wait for it.

    How to build it (`playwright codegen <the url>` will write the first three
    steps for you — click through the page and copy what it records):

    - `page.goto(cafe_url("Canal Street Coffee"))`.
    - Choose the shop: `page.get_by_label("Choose your shop").select_option(shop)`.
    - Click the "Show full menu" button (`page.get_by_role("button", name=...)`),
      then `page.wait_for_selector("a.result-card")` — the cards appear after a delay.
    - While the "Show more" button `is_visible()`: count the cards
      (`page.locator("a.result-card").count()`), click it, and wait until there
      are more — `page.wait_for_function(f"document.querySelectorAll(
      'a.result-card').length > {count}")`.
    - Collect every card's `get_attribute("href")` — the link to its item page.
    - For each link: `page.goto(urljoin(cafe_url("Canal Street Coffee"), href))`,
      `page.wait_for_selector("#sizes")`, then read `#item-name`, the category
      (the text of `#item-category` before " · "), and one row per
      `#sizes tbody tr` — its two `td` cells are the size and the price.
    """
    base_url = cafe_url("Canal Street Coffee")

    page.goto(base_url)

    page.get_by_label("Choose your shop").select_option(shop)

    page.get_by_role("button", name="Show full menu").click()

    page.wait_for_selector("a.result-card")

    show_more = page.get_by_role("button", name="Show more")

    while show_more.is_visible():
        count = page.locator("a.result-card").count()

        show_more.click()

        page.wait_for_function(
            f"document.querySelectorAll('a.result-card').length > {count}"
        )

    # Collect all item page links
    hrefs = [
        card.get_attribute("href")
        for card in page.locator("a.result-card").all()
    ]

    rows = []

    for href in hrefs:
        page.goto(urljoin(base_url, href))

        page.wait_for_selector("#sizes")

        item = page.locator("#item-name").inner_text().strip()

        category = (
            page.locator("#item-category")
            .inner_text()
            .split(" · ")[0]
            .strip()
        )

        size_rows = page.locator("#sizes tbody tr").all()

        for row in size_rows:
            cells = row.locator("td").all()

            size = cells[0].inner_text().strip()
            price = cells[1].inner_text().strip()

            rows.append({
                "cafe": "Canal Street Coffee",
                "category": category,
                "item": item,
                "size": size,
                "price": clean_price(price)
            })

    return rows