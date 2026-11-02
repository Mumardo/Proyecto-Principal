import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode, urljoin, urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "tiendas_mujer.json"
TRICOT_CATEGORY_URL = "https://www.tricot.cl/mujer"
TRICOT_GRID_URL = (
    "https://www.tricot.cl/on/demandware.store/Sites-TRICOT_CL-Site/"
    "default/Search-UpdateGrid"
)
PARIS_CATEGORY_URL = "https://www.paris.cl/mujer/moda/"
PARIS_SEARCH_URL = (
    "https://be-paris-backend-cl-ms-search.ccom.paris.cl/products/"
)
PAGE_SIZE = 60
PARIS_PAGE_SIZE = 100
PARIS_WORKERS = 4
USER_AGENT = "Mozilla/5.0 (compatible; CalceCatalog/1.0)"
FOOTWEAR_TERMS = re.compile(
    r"\b(?:calzad\w*|zapat\w*|sandali\w*|botin\w*|bota\w*|"
    r"mocasin\w*|alpargat\w*|pantufl\w*|tacon\w*|taco\w*|"
    r"stiletto\w*|oxford\w*|loafer\w*|sneaker\w*|shoe\w*|"
    r"boot\w*|heel\w*|sandal\w*|slipper\w*|chancl\w*|"
    r"chala\w*|ojota\w*)\b"
)
PRODUCT_TYPES = (
    ("sosten", "Ropa interior", None),
    ("pantaleta", "Ropa interior", None),
    ("colaless", "Ropa interior", None),
    ("calzon", "Ropa interior", None),
    ("bikini", "Ropa interior", None),
    ("tanga", "Ropa interior", None),
    ("bralette", "Ropa interior", None),
    ("baby doll", "Ropa interior", None),
    ("bustier", "Ropa interior", None),
    ("faja", "Ropa interior", None),
    ("culotte", "Ropa interior", None),
    ("extensor", "Ropa interior", None),
    ("pijama", "Pijama", None),
    ("camisola", "Camisola", None),
    ("bata", "Bata", None),
    ("pareo", "Ropa de playa", None),
    ("jeans", "Jeans", "Jeans"),
    ("pantalon", "Pantalón", "Pantalon"),
    ("falda", "Falda", "Pantalon"),
    ("short", "Shorts", "Pantalon"),
    ("vestido", "Vestido", "Vestido"),
    ("enterito", "Enterito", "Vestido"),
    ("blazer", "Blazer", "Blazer"),
    ("chaqueta", "Chaqueta", "Blazer"),
    ("parka", "Parka", "Blazer"),
    ("poleron", "Polerón", "Blazer"),
    ("cardigan", "Cardigan", "Blazer"),
    ("chaleco", "Chaleco", "Blazer"),
    ("sweater", "Sweater", "Blazer"),
    ("blusa", "Blusa", "Blusa"),
    ("camisa", "Camisa", "Blusa"),
    ("polera", "Polera", "Polera"),
    ("camiseta", "Polera", "Polera"),
    ("body", "Body", "Top Deportivo"),
    ("kimono", "Kimono", "Blazer"),
    ("gilet", "Chaleco", "Blazer"),
    ("capa", "Chaqueta", "Blazer"),
    ("abrigo", "Chaqueta", "Blazer"),
    ("bomber", "Chaqueta", "Blazer"),
    ("top", "Top", "Top Deportivo"),
    ("peto", "Peto", "Top Deportivo"),
    ("corset", "Corset", "Top Deportivo"),
    ("buzo", "Buzo", "Pantalon"),
    ("calza", "Calza", "Pantalon"),
    ("legging", "Calza", "Pantalon"),
    ("jogger", "Pantalón", "Pantalon"),
    ("calcetin", "Accesorio", None),
    ("banano", "Accesorio", None),
    ("guante", "Accesorio", None),
    ("lente", "Accesorio", None),
    ("aro", "Accesorio", None),
    ("collar", "Accesorio", None),
    ("pulsera", "Accesorio", None),
    ("anillo", "Accesorio", None),
    ("pinche", "Accesorio", None),
    ("sombrero", "Accesorio", None),
    ("jockey", "Accesorio", None),
    ("bolso", "Accesorio", None),
    ("mochila", "Accesorio", None),
    ("cartera", "Accesorio", None),
    ("billetera", "Accesorio", None),
    ("cinturon", "Accesorio", None),
    ("cintillo", "Accesorio", None),
    ("scrunchie", "Accesorio", None),
    ("bandolera", "Accesorio", None),
    ("tarjetero", "Accesorio", None),
    ("pañuelo", "Accesorio", None),
    ("panuelos", "Accesorio", None),
    ("bolsa", "Accesorio", None),
    ("toalla", "Accesorio", None),
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )


def _is_footwear(*values: str) -> bool:
    return bool(FOOTWEAR_TERMS.search(_normalize(" ".join(values))))


def _classify(title: str) -> tuple[str, Optional[str]]:
    normalized = _normalize(title)
    for token, label, reference_category in PRODUCT_TYPES:
        if re.search(rf"\b{re.escape(token)}\w*\b", normalized):
            return label, reference_category
    return "Ropa", None


def _fetch(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=40) as response:
        if response.status != 200:
            raise RuntimeError(f"No se pudo consultar {url}: HTTP {response.status}")
        return response.read().decode("utf-8", "replace")


class TricotProductParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.products: List[Dict[str, object]] = []
        self.product_ids: List[str] = []
        self.current: Optional[Dict[str, object]] = None
        self.div_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attributes = dict(attrs)
        if tag == "div" and attributes.get("data-pid") and self.current is None:
            self.current = {
                "id": str(attributes["data-pid"]),
                "title": "",
                "url": "",
                "image_url": "",
                "brand": "",
                "price_clp": None,
            }
            self.div_depth = 1
            return
        if self.current is None:
            return
        if tag == "div":
            self.div_depth += 1
        if tag == "a" and not self.current["url"]:
            href = attributes.get("href", "")
            if href.endswith(".html"):
                self.current["url"] = urljoin("https://www.tricot.cl", href)
        if tag == "img":
            if not self.current["title"]:
                self.current["title"] = attributes.get("alt", "").strip()
            image_url = attributes.get("data-src", "")
            if image_url and not self.current["image_url"]:
                self.current["image_url"] = urljoin(
                    "https://www.tricot.cl", image_url
                )
            tracking = attributes.get("data-ga", "")
            if tracking:
                try:
                    items = json.loads(tracking)["ecommerce"]["items"]
                    if items:
                        item = items[0]
                        self.current["title"] = (
                            item.get("item_name") or self.current["title"]
                        )
                        self.current["brand"] = item.get("item_brand", "")
                        price = item.get("price")
                        if isinstance(price, (int, float)) and price > 0:
                            self.current["price_clp"] = int(price)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    pass

    def handle_endtag(self, tag: str) -> None:
        if self.current is None or tag != "div":
            return
        self.div_depth -= 1
        if self.div_depth == 0:
            product = self.current
            self.current = None
            self._append_product(product)

    def _append_product(self, product: Dict[str, object]) -> None:
        if not product["id"] or not product["title"] or not product["url"]:
            return
        url = urlparse(str(product["url"]))
        image_url = urlparse(str(product["image_url"]))
        if (
            url.scheme != "https"
            or url.netloc != "www.tricot.cl"
            or image_url.scheme != "https"
            or image_url.netloc != "www.tricot.cl"
        ):
            return
        self.product_ids.append(str(product["id"]))
        if _is_footwear(str(product["title"])):
            return
        product_type, reference_category = _classify(str(product["title"]))
        self.products.append(
            {
                "id": f"tricot-{product['id']}",
                "store": "Tricot",
                "title": product["title"],
                "catalog_categories": "Ropa de mujer",
                "type": product_type,
                "reference_category": reference_category,
                "brand": product["brand"] or "Tricot",
                "size": "",
                "price_clp": product["price_clp"],
                "url": product["url"],
                "image_url": product["image_url"],
            }
        )


def _tricot_total(html: str) -> int:
    match = re.search(
        r'class=["\'][^"\']*js-result-qty[^"\']*["\'][^>]*value=["\'](\d+)',
        html,
    )
    if not match:
        raise ValueError("Tricot no informó el total de prendas de mujer.")
    return int(match.group(1))


def _fetch_tricot_products() -> tuple[List[Dict[str, object]], int]:
    products: List[Dict[str, object]] = []
    seen_ids = set()
    total = 0
    for start in range(0, 100000, PAGE_SIZE):
        parameters = urlencode(
            {
                "cgid": "34",
                "srule": "best-matches",
                "start": start,
                "sz": PAGE_SIZE,
            }
        )
        page = _fetch(f"{TRICOT_GRID_URL}?{parameters}")
        if start == 0:
            total = _tricot_total(_fetch(TRICOT_CATEGORY_URL))
        parser = TricotProductParser()
        parser.feed(page)
        new_products = [
            product
            for product in parser.products
            if product["id"] not in seen_ids
        ]
        seen_ids.update(parser.product_ids)
        products.extend(new_products)
        if start + PAGE_SIZE >= total:
            break
        if not parser.products:
            raise RuntimeError(f"Tricot devolvió una página vacía desde {start}.")
        time.sleep(0.15)
    if len(seen_ids) < total:
        raise RuntimeError(
            f"Tricot informó {total} resultados, pero se procesaron "
            f"{len(seen_ids)} fichas con enlace e imagen."
        )
    return products, total


def _paris_search_configuration(page: str) -> tuple[str, str]:
    query_position = page.find("searchQueryArgs")
    if query_position < 0:
        raise ValueError("Paris no publicó los parámetros de búsqueda de moda.")
    query_end = page.find("facetsSearchQueryArgs", query_position)
    query = page[query_position : query_end if query_end >= 0 else query_position + 2000]
    group_position = query.find("group_id")
    group_match = re.search(r"muj[A-Za-z]+", query[group_position:]) if group_position >= 0 else None
    application_position = query.find("applicationId")
    application_match = (
        re.search(r"[a-f0-9]{64}", query[application_position:])
        if application_position >= 0
        else None
    )
    if not group_match or not application_match:
        raise ValueError("No se pudieron leer los parámetros públicos de búsqueda de Paris.")
    return group_match.group(0), application_match.group(0)


def _paris_localized(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("es-CL") or next(iter(value.values()), "")
    return str(value or "").strip()


def _paris_product(item: Dict[str, object]) -> Optional[Dict[str, object]]:
    title = _paris_localized(item.get("name"))
    slug = _paris_localized(item.get("slug"))
    product_id = str(item.get("id") or "").strip()
    categories = item.get("categories")
    category_tokens = (
        [
            re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(category.get("id", "")))
            for category in categories
            if isinstance(category, dict)
        ]
        if isinstance(categories, list)
        else []
    )
    variant = item.get("masterVariant")
    if not isinstance(variant, dict):
        return None
    images = variant.get("images")
    image_url = ""
    if isinstance(images, list):
        image_url = next(
            (
                str(image.get("url", ""))
                for image in images
                if isinstance(image, dict)
                and urlparse(str(image.get("url", ""))).scheme == "https"
            ),
            "",
        )
    product_url = (
        f"https://www.paris.cl/{slug}.html"
        if slug and not slug.endswith(".html")
        else f"https://www.paris.cl/{slug}"
        if slug
        else ""
    )
    parsed_url = urlparse(product_url)
    parsed_image = urlparse(image_url)
    if (
        not title
        or not product_id
        or parsed_url.scheme != "https"
        or parsed_url.netloc != "www.paris.cl"
        or parsed_image.scheme != "https"
        or not parsed_image.netloc
        or _is_footwear(title, *category_tokens)
    ):
        return None
    prices = variant.get("prices")
    prices = prices if isinstance(prices, dict) else {}
    price = None
    for key in ("offer", "regular"):
        price_data = prices.get(key)
        amount = (
            price_data.get("value", {}).get("centAmount")
            if isinstance(price_data, dict)
            and isinstance(price_data.get("value"), dict)
            else None
        )
        if isinstance(amount, (int, float)) and amount > 0:
            price = int(amount)
            break
    product_type, reference_category = _classify(title)
    return {
        "id": f"paris-{product_id}",
        "store": "Paris",
        "title": title,
        "catalog_categories": "Ropa de mujer",
        "type": product_type,
        "reference_category": reference_category,
        "brand": _paris_localized(item.get("brand")) or "Paris",
        "size": "",
        "price_clp": price,
        "url": product_url,
        "image_url": image_url,
    }


def _fetch_paris_page(
    page_number: int,
    group_id: str,
    application_id: str,
) -> Dict[str, object]:
    payload = {
        "filters": [{"key": "group_id", "stringValues": [group_id]}],
        "pagination": {"page": page_number, "pageSize": PARIS_PAGE_SIZE},
        "sortBy": "relevance",
        "storeIds": None,
        "serviceAbility": {
            "sameDayDelivery": False,
            "nextDayDelivery": False,
            "storePickUp": False,
        },
        "sponsoredProducts": True,
        "slotId": ["mid"],
        "applicationId": application_id,
    }
    request = Request(
        PARIS_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Origin": "https://www.paris.cl",
            "Referer": PARIS_CATEGORY_URL,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Paris respondió HTTP {response.status} en la página "
                        f"{page_number}."
                    )
                data = json.loads(response.read())
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise ValueError(
                    f"Paris devolvió una respuesta inválida en la página {page_number}."
                )
            return data
        except (
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            RuntimeError,
            ValueError,
        ) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(
        f"No se pudo consultar la página {page_number} de Paris tras 3 intentos: "
        f"{last_error}"
    ) from last_error


def _paris_products_from_page(
    page_data: Dict[str, object],
) -> List[Dict[str, object]]:
    products = []
    for item in page_data["results"]:
        product = _paris_product(item)
        if product:
            products.append(product)
    return products


def _fetch_paris_page_products(
    page_number: int,
    group_id: str,
    application_id: str,
) -> List[Dict[str, object]]:
    return _paris_products_from_page(
        _fetch_paris_page(page_number, group_id, application_id)
    )


def _append_paris_products(
    page_products: List[Dict[str, object]],
    products: List[Dict[str, object]],
    seen_ids: set,
) -> None:
    for product in page_products:
        if product["id"] not in seen_ids:
            seen_ids.add(product["id"])
            products.append(product)


def _fetch_paris_products() -> tuple[List[Dict[str, object]], int]:
    group_id, application_id = _paris_search_configuration(
        _fetch(PARIS_CATEGORY_URL)
    )
    first_page = _fetch_paris_page(1, group_id, application_id)
    total = int(first_page.get("total", 0))
    if total < 1:
        raise ValueError("Paris no informó resultados en su categoría de moda mujer.")
    page_count = (total + PARIS_PAGE_SIZE - 1) // PARIS_PAGE_SIZE
    products = []
    seen_ids = set()
    _append_paris_products(_paris_products_from_page(first_page), products, seen_ids)
    with ThreadPoolExecutor(max_workers=PARIS_WORKERS) as executor:
        futures = [
            executor.submit(
                _fetch_paris_page_products, page_number, group_id, application_id
            )
            for page_number in range(2, page_count + 1)
        ]
        for completed, future in enumerate(as_completed(futures), start=2):
            _append_paris_products(future.result(), products, seen_ids)
            if completed % 20 == 0 or completed == page_count:
                print(
                    f"Paris: {completed}/{page_count} páginas consultadas.",
                    flush=True,
                )
    if not products:
        raise ValueError("Paris no devolvió prendas con imágenes utilizables.")
    return products, total


def main() -> None:
    tricot_products, tricot_total = _fetch_tricot_products()
    time.sleep(0.5)
    paris_products, paris_total = _fetch_paris_products()
    products = tricot_products + paris_products
    products.sort(key=lambda product: (str(product["store"]), str(product["id"])))
    data = {
        "checked_at": date.today().isoformat(),
        "stores": {
            "Tricot": {
                "category_url": TRICOT_CATEGORY_URL,
                "results_reported": tricot_total,
                "products_collected": len(tricot_products),
            },
            "Paris": {
                "category_url": PARIS_CATEGORY_URL,
                "results_reported": paris_total,
                "products_collected": len(paris_products),
                "note": (
                    "Productos recopilados mediante todas las páginas de la "
                    "categoría pública de moda mujer."
                ),
            },
        },
        "products": products,
    }
    OUTPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Guardadas {len(products)} prendas: "
        f"{len(tricot_products)} de Tricot y {len(paris_products)} de Paris "
        f"en {OUTPUT}"
    )


if __name__ == "__main__":
    main()
