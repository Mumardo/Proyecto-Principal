import json
import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

from .producto_vestua import ProductoVestua


TIPOS_REFERENCIA = (
    ("crop top", "Crop top", "Top Deportivo"),
    ("cortavientos", "Cortavientos", "Blazer"),
    ("pantalon", "Pantalón", "Pantalon"),
    ("poleron", "Polerón", "Blazer"),
    ("zapatillas", "Zapatillas", None),
    ("sandalias", "Sandalias", None),
    ("vestido", "Vestido", "Vestido"),
    ("enterito", "Enterito", "Vestido"),
    ("chaqueta", "Chaqueta", "Blazer"),
    ("cardigan", "Cardigan", "Blazer"),
    ("chaleco", "Chaleco", "Blazer"),
    ("corset", "Corset", "Top Deportivo"),
    ("shorts", "Shorts", "Pantalon"),
    ("blazer", "Blazer", "Blazer"),
    ("falda", "Falda", "Pantalon"),
    ("jeans", "Jeans", "Jeans"),
    ("calza", "Calza", "Pantalon"),
    ("kimono", "Kimono", "Blazer"),
    ("parka", "Parka", "Blazer"),
    ("camisa", "Camisa", "Blusa"),
    ("blusa", "Blusa", "Blusa"),
    ("polera", "Polera", "Polera"),
    ("peto", "Peto", "Top Deportivo"),
    ("crop", "Crop", "Top Deportivo"),
    ("buzo", "Buzo", "Pantalon"),
    ("top", "Top", "Top Deportivo"),
)
PRODUCT_URL = re.compile(r"^/store/product/(\d+)/[^/]+/?$")


def _normalizar(texto: str) -> str:
    normalizado = unicodedata.normalize("NFD", texto.casefold())
    return "".join(character for character in normalizado if not unicodedata.combining(character))


class RepositorioVestua:
    """Carga fichas deduplicadas del catálogo descargado de Vestua."""

    def __init__(self, ruta_archivo: Path) -> None:
        self.ruta_archivo = Path(ruta_archivo)

    def cargar(self) -> Tuple[ProductoVestua, ...]:
        if not self.ruta_archivo.is_file():
            raise FileNotFoundError(
                f"No se encontró el catálogo de Vestua: {self.ruta_archivo}"
            )
        with self.ruta_archivo.open(encoding="utf-8") as catalog_file:
            data = json.load(catalog_file)

        products = data.get("products")
        checked_at = data.get("checked_at")
        if not isinstance(products, list) or not checked_at:
            raise ValueError("El archivo del catálogo de Vestua tiene un formato inválido.")

        parsed_products = []
        seen_ids = set()
        seen_urls = set()
        for item in products:
            product_id = str(item.get("id", "")).strip()
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            parsed_url = urlparse(url)
            path_match = PRODUCT_URL.fullmatch(parsed_url.path)
            if (
                not product_id
                or not title
                or parsed_url.scheme != "https"
                or parsed_url.netloc != "www.vestua.cl"
                or path_match is None
                or path_match.group(1) != product_id
            ):
                raise ValueError(
                    f"Ficha inválida en el catálogo de Vestua: {product_id!r}"
                )
            # Vestua puede devolver la misma ficha en más de una página o con
            # una URL repetida. Se conserva la primera aparición.
            if product_id in seen_ids or url in seen_urls:
                continue
            seen_ids.add(product_id)
            seen_urls.add(url)

            tipo, marca, categoria_referencia = self._clasificar(title)
            price = item.get("price_clp")
            if price is not None and (not isinstance(price, int) or price <= 0):
                raise ValueError(
                    f"Precio inválido en la ficha de Vestua {product_id}."
                )
            parsed_products.append(
                ProductoVestua(
                    id=product_id,
                    titulo=title,
                    categorias_catalogo=str(item.get("catalog_categories", "")),
                    tipo_prenda=tipo,
                    marca=marca,
                    categoria_referencia=categoria_referencia,
                    talla=str(item.get("size", "")),
                    precio_clp=price,
                    url=url,
                    fecha_consulta=str(item.get("checked_at", checked_at)),
                )
            )
        if not parsed_products:
            raise ValueError("El catálogo de Vestua no contiene prendas.")
        return tuple(parsed_products)

    @staticmethod
    def _clasificar(title: str) -> Tuple[str, str, Optional[str]]:
        normalized_title = _normalizar(title)
        for normalized_type, display_type, reference_category in TIPOS_REFERENCIA:
            if normalized_title == normalized_type:
                return display_type, "Sin marca", reference_category
            if normalized_title.startswith(normalized_type + " "):
                brand = title[len(display_type):].strip()
                return display_type, brand or "Sin marca", reference_category
        categories = {
            "chaquetas": ("Chaqueta", "Blazer"),
            "blazers": ("Blazer", "Blazer"),
            "vestidos": ("Vestido", "Vestido"),
            "faldas": ("Falda", "Pantalon"),
            "pantalones": ("Pantalón", "Pantalon"),
            "shorts": ("Shorts", "Pantalon"),
            "jeans": ("Jeans", "Jeans"),
            "blusas y camisas": ("Blusa", "Blusa"),
            "tops y poleras": ("Top", "Top Deportivo"),
            "sweaters y cardigans": ("Sweater/cardigan", "Blazer"),
            "ropa deportiva": ("Ropa deportiva", "Pantalon"),
        }
        category = _normalizar(title)
        for candidate, (display_type, reference_category) in categories.items():
            if category.startswith(candidate):
                return display_type, title, reference_category
        return title, "Sin marca", None
