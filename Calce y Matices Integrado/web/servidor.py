from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from dataclasses import replace
from functools import lru_cache
import gzip
import json
from math import isfinite
import os
import re
from statistics import median
import subprocess
import sys
from typing import Dict, MutableMapping, Optional, Tuple
import unicodedata
from urllib.parse import parse_qs, urlencode, urlparse
import webbrowser

from medidas.perfil_medidas import PerfilMedidas
from medidas.tallas import RepositorioTallasEstandar, recomendar_tallas
from metricas.calculadora_calce import CalculadoraCalce
from metricas.resultado_calce import ResultadoCalce
from prendas import (
    CatalogoPrendas,
    Prenda,
    ProductoVestua,
    RepositorioExcelPrendas,
    RepositorioVestua,
)


ROOT = Path(__file__).resolve().parents[1]
WEB_DIRECTORY = Path(__file__).resolve().parent


def _load_environment_file(
    path: Path,
    environment: Optional[MutableMapping[str, str]] = None,
) -> None:
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except OSError as error:
        raise RuntimeError(f"No se pudo leer la configuración local {path}.") from error

    target_environment = os.environ if environment is None else environment
    for line in contents.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("export "):
            entry = entry[len("export "):].lstrip()
        key, separator, value = entry.partition("=")
        key = key.strip()
        if not separator or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        target_environment.setdefault(key, value)


_load_environment_file(ROOT / ".env")
MATRIX_PATH = ROOT / "data" / "Matriz_Medidas_Marcas_Vestua.xlsx"
SIZE_CHART_PATH = ROOT / "data" / "Tabla_estandar.xlsx"
HOST = "127.0.0.1"
PORT = 4173
IS_RENDER = os.environ.get("RENDER", "").lower() == "true"
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://twhszjxhmimqlzthlbgy.supabase.co"
).rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
REPOSITORY = RepositorioExcelPrendas(MATRIX_PATH)
VARIABLES = REPOSITORY.cargar_variables()
STANDARD_SIZES = RepositorioTallasEstandar(SIZE_CHART_PATH).cargar()
VESTUA_IMAGES_PATH = ROOT / "data" / "vestua_images.json"
with VESTUA_IMAGES_PATH.open(encoding="utf-8") as image_file:
    VESTUA_IMAGES = json.load(image_file)
VESTUA_CATALOG_PATH = ROOT / "data" / "vestua_catalog.json"
VESTUA_PRODUCTS = RepositorioVestua(VESTUA_CATALOG_PATH).cargar()
VESTUA_IMAGES_BY_URL = {
    reference["product_url"]: reference
    for brand_references in VESTUA_IMAGES.values()
    for reference in brand_references.values()
    if reference.get("product_url")
}
WOMENSWEAR_CATALOG_PATH = ROOT / "data" / "tiendas_mujer.json"
with WOMENSWEAR_CATALOG_PATH.open(encoding="utf-8") as catalog_file:
    WOMENSWEAR_DATA = json.load(catalog_file)
WOMENSWEAR_PRODUCTS = tuple(
    ProductoVestua(
        id=item["id"],
        titulo=item["title"],
        categorias_catalogo=item["catalog_categories"],
        tipo_prenda=item["type"],
        marca=item["brand"],
        categoria_referencia=item["reference_category"],
        talla=item["size"],
        precio_clp=item["price_clp"],
        url=item["url"],
        fecha_consulta=WOMENSWEAR_DATA["checked_at"],
    )
    for item in WOMENSWEAR_DATA["products"]
)
WOMENSWEAR_IMAGES_BY_URL = {
    item["url"]: item["image_url"] for item in WOMENSWEAR_DATA["products"]
}
WOMENSWEAR_STORES_BY_URL = {
    item["url"]: item["store"] for item in WOMENSWEAR_DATA["products"]
}
CATALOG_IMAGES_BY_URL = {
    **{
        url: reference["image_url"]
        for url, reference in VESTUA_IMAGES_BY_URL.items()
    },
    **WOMENSWEAR_IMAGES_BY_URL,
}
CATALOG_STORES_BY_URL = {
    **{url: "Vestua" for url in VESTUA_IMAGES_BY_URL},
    **WOMENSWEAR_STORES_BY_URL,
}


def _is_footwear(product: ProductoVestua) -> bool:
    product_details = " ".join(
        (product.titulo, product.tipo_prenda, product.categorias_catalogo)
    )
    normalized_details = _normalize_search_text(product_details)
    return bool(
        re.search(
            r"\b(?:calzad\w*|zapat\w*|sandali\w*|botin\w*|bota\w*|"
            r"mocasin\w*|alpargat\w*|pantufl\w*|tacon\w*|taco\w*|"
            r"stiletto\w*|oxford\w*|loafer\w*|sneaker\w*|shoe\w*|"
            r"boot\w*|heel\w*|sandal\w*|slipper\w*|chancl\w*|"
            r"chala\w*|ojota\w*)\b",
            normalized_details,
        )
    )


def _normalize_search_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(character) != "Mn"
    )


CATALOG_PRODUCTS = tuple(
    product
    for product in (*VESTUA_PRODUCTS, *WOMENSWEAR_PRODUCTS)
    if not _is_footwear(product)
    and (
        (image_url := CATALOG_IMAGES_BY_URL.get(product.url))
        and urlparse(image_url).scheme == "https"
        and urlparse(image_url).netloc
    )
)
CATALOG_SEARCH_TEXT_BY_URL = {
    product.url: _normalize_search_text(
        " ".join(
            (
                CATALOG_STORES_BY_URL.get(product.url, "Vestua"),
                product.titulo,
                product.marca,
                product.categorias_catalogo,
            )
        )
    )
    for product in CATALOG_PRODUCTS
}
WOMENSWEAR_STORES = (
    ("Paris", "https://www.paris.cl/mujer/"),
    ("Tricot", "https://www.tricot.cl/mujer"),
)
CATALOG_PAGE_SIZE = 9
CATALOG_SORT_OPTIONS = (
    ("fit-asc", "Mejor calce"),
    ("fit-desc", "Peor calce"),
    ("price-asc", "Precio: menor a mayor"),
    ("price-desc", "Precio: mayor a menor"),
)


def _has_vestua_listing(prenda) -> bool:
    reference = VESTUA_IMAGES.get(prenda.marca, {}).get(prenda.categoria, {})
    product_url = urlparse(reference.get("product_url", ""))
    image_url = urlparse(reference.get("image_url", ""))
    path_parts = product_url.path.strip("/").split("/")
    return bool(
        reference.get("product_title")
        and product_url.scheme == "https"
        and product_url.netloc == "www.vestua.cl"
        and len(path_parts) >= 3
        and path_parts[:2] == ["store", "product"]
        and path_parts[2].isdigit()
        and image_url.scheme == "https"
        and reference.get("image_url")
    )


CATALOG = CatalogoPrendas(
    prenda for prenda in REPOSITORY.cargar_prendas() if _has_vestua_listing(prenda)
)
CALCULATOR = CalculadoraCalce()
_CATEGORY_REFERENCES = {}
for _category in CATALOG.categorias():
    _category_references = CATALOG.filtrar(categoria=_category)
    if _category_references:
        _representative = _category_references[0]
        _CATEGORY_REFERENCES[_category] = replace(
            _representative,
            cintura=median(item.cintura for item in _category_references),
            cadera=median(item.cadera for item in _category_references),
        )
_BRAND_CATEGORY_REFERENCES = {
    (prenda.marca, prenda.categoria): prenda
    for prenda in CATALOG.prendas
}
MEASUREMENT_FIELDS = (
    ("bust", "Busto / pecho", "40", "200", "0.5", "p. ej. 90"),
    ("waist", "Cintura", "40", "180", "0.5", "p. ej. 74"),
    ("hip", "Cadera", "40", "200", "0.5", "p. ej. 100"),
)
BRAND_MOLD_ORIGINS = {
    "Zara": "europeo / Inditex",
    "H&M": "europeo",
    "Mango": "europeo / Inditex",
    "ASOS": "europeo / británico",
    "Levi's": "americano",
    "Nike": "americano",
}
CATEGORY_GROUPS = {
    "__all__": CATALOG.categorias(),
    "__top__": ("Blusa", "Polera", "Top Deportivo", "Blazer", "Vestido"),
    "__bottom__": ("Pantalon", "Pantalón", "Jeans"),
}
IMPACT_PRIORITY = {"Muy Alto": 0, "Alto": 1, "Medio": 2, "Bajo": 3}
MEASUREMENT_HELP = {
    "bust": (
        "Mide alrededor de la parte más amplia del pecho, manteniendo la cinta "
        "horizontal y sin apretar."
    ),
    "waist": (
        "Mide alrededor de la parte más estrecha de la cintura "
        "(usualmente justo por encima del ombligo)"
    ),
    "hip": (
        "Junta los pies y mide alrededor de la parte más ancha de las "
        "caderas y glúteos."
    ),
}


def _reference_for_listing(
    product: ProductoVestua,
) -> Tuple[Optional[Prenda], str]:
    category = product.categoria_referencia
    if category is None:
        return None, ""
    reference = _BRAND_CATEGORY_REFERENCES.get((product.marca, category))
    if reference is not None:
        return reference, f"{category} · referencia de matriz para {product.marca}"
    reference = _CATEGORY_REFERENCES.get(category)
    if reference is None:
        return None, ""
    return reference, f"{category} · referencia promedio del catálogo"


@lru_cache(maxsize=512)
def _calculate_fit(
    prenda: Prenda,
    perfil: PerfilMedidas,
    preferencia: str,
) -> ResultadoCalce:
    return CALCULATOR.calcular(prenda, perfil, preferencia)


def _option(value: str, label: str, selected: str) -> str:
    selected_attribute = " selected" if value == selected else ""
    return (
        f'<option value="{escape(value, quote=True)}"'
        f'{selected_attribute}>{escape(label)}</option>'
    )


def _measurement_fields(query: Dict[str, str]) -> str:
    fields = []
    for key, label, minimum, maximum, step, placeholder in MEASUREMENT_FIELDS:
        optional = " <small>cm</small>"
        value = escape(query.get(key, ""), quote=True)
        help_text = MEASUREMENT_HELP.get(key)
        help_button = (
            f'<button class="measurement-help-trigger" type="button" '
            f'aria-label="Ayuda para {escape(label, quote=True)}" '
            f'aria-describedby="measurement-help-{key}">?</button>'
            f'<span class="measurement-tooltip" id="measurement-help-{key}" role="tooltip">'
            f'{escape(help_text)}</span>'
            if help_text
            else ""
        )
        fields.append(
            f'<div class="measurement-field"><div class="field-label">'
            f'<label for="measurement-{key}">{escape(label)}{optional}</label>'
            f'{help_button}</div>'
            f'<input class="measurement-input" id="measurement-{key}" name="{key}" '
            f'type="number" min="{minimum}" max="{maximum}" '
            f'step="{step}" placeholder="{placeholder}" inputmode="decimal" value="{value}">'
            '</div>'
        )
    return "".join(fields)


def _personal_recommendations(
    perfil: PerfilMedidas,
    preferencia: str,
    catalog_url: str = "/?view=catalog",
) -> str:
    coincidencias = []
    for prenda in CATALOG.prendas:
        resultado = CALCULATOR.calcular(prenda, perfil, preferencia)
        if not isfinite(resultado.puntuacion) or resultado.diagnostico.etiqueta == "Revisión parcial":
            continue
        coincidencias.append((prenda, resultado))

    tallas, coincide_todo = recomendar_tallas(perfil, STANDARD_SIZES)
    if not coincidencias:
        summary = (
            '<p class="sub">Completa medidas corporales para comparar las marcas '
            "y tipos de prenda que cuentan con datos suficientes.</p>"
        )
        brand = "Aún sin datos suficientes"
        category = "Aún sin datos suficientes"
        brand_origin = None
        brand_label = "Marca más recomendada"
        category_label = "Tipo de ropa recomendado"
    else:
        puntuacion_minima = min(
            resultado.puntuacion for _, resultado in coincidencias
        )
        mejores = tuple(
            (prenda, resultado)
            for prenda, resultado in coincidencias
            if abs(resultado.puntuacion - puntuacion_minima) < 1e-9
        )
        marcas = tuple(dict.fromkeys(prenda.marca for prenda, _ in mejores))
        categorias = tuple(dict.fromkeys(prenda.categoria for prenda, _ in mejores))
        brand = ", ".join(escape(marca) for marca in marcas)
        category = ", ".join(escape(tipo) for tipo in categorias)
        brand_origin = BRAND_MOLD_ORIGINS.get(marcas[0]) if len(marcas) == 1 else None
        brand_label = (
            "Marcas con mejor coincidencia"
            if len(marcas) > 1
            else "Marca más recomendada"
        )
        category_label = (
            "Tipos de ropa con mejor coincidencia"
            if len(categorias) > 1
            else "Tipo de ropa recomendado"
        )
        summary = (
            '<p class="sub">Las referencias mostradas tienen la menor diferencia '
            "respecto a tus medidas.</p>"
            if len(marcas) == 1
            else '<p class="sub">Hay un empate entre marcas. La matriz repite las '
            "mismas medidas por categoría, así que estos datos no permiten "
            "distinguir el calce entre ellas.</p>"
        )

    if not tallas:
        sizes = "Ingresa busto, cintura o cadera"
        size_note = ""
    else:
        sizes = ", ".join(
            escape(talla.etiqueta)
            + (
                f" (EU {escape(talla.europea)})"
                if talla.europea
                else ""
            )
            + (
                f" (EE.UU. {escape(talla.estadounidense)})"
                if talla.estadounidense
                else ""
            )
            for talla in tallas
        )
        size_note = (
            "Todas las medidas ingresadas están dentro de estos rangos."
            if coincide_todo
            else "Son las tallas más cercanas."
        )
    brand_origin_markup = (
        f'<small class="brand-mold-origin">Molde {escape(brand_origin)}</small>'
        if coincidencias and brand_origin
        else ""
    )

    return (
        '<section class="personal-recommendations" aria-label="Resumen de recomendaciones">'
        '<div class="help-heading"><h3>Recomendaciones según tus medidas</h3>'
        '<button class="measurement-help-trigger" type="button" '
        'aria-label="Ayuda sobre recomendaciones según tus medidas" '
        'aria-describedby="recommendations-help">?</button>'
        '<span class="measurement-tooltip" id="recommendations-help" role="tooltip">'
        "La tabla estándar usa busto/pecho, cintura y cadera. El cálculo de "
        "calce de las prendas considera cintura y cadera, ya que las fichas "
        "importadas de Vestua no publican medidas físicas exactas.</span></div>"
        f"{summary}"
        '<div class="recommendation-summary">'
        f'<div><span>{brand_label}</span><strong>{brand}</strong>'
        f'{brand_origin_markup}</div>'
        f'<div><span>{category_label}</span><strong>{category}</strong></div>'
        f'<div><span>Talla alfa</span><strong>{sizes}</strong>'
        f'<small>{escape(size_note)}</small></div>'
        "</div>"
        f'<a class="catalog-toggle" href="{escape(catalog_url, quote=True)}" '
        'aria-controls="catalog-panel">'
        "Ver catálogo completo</a>"
        "</section>"
    )


def _format_price(price: Optional[int]) -> str:
    if price is None:
        return "Precio no disponible"
    return f"${price:,}".replace(",", ".")


def _catalog_product_card(
    product: ProductoVestua,
    reference: Optional[object],
    result: Optional[ResultadoCalce],
    reference_label: str,
    indice: int,
    preferencia: str,
    perfil: PerfilMedidas,
) -> str:
    store = CATALOG_STORES_BY_URL.get(product.url, "Vestua")
    image_url = CATALOG_IMAGES_BY_URL.get(product.url, "")
    price_value = "" if product.precio_clp is None else str(product.precio_clp)
    image = (
        f'<img class="catalog-image" src="{escape(image_url, quote=True)}" '
        f'alt="Imagen referencial de {escape(product.titulo, quote=True)}" loading="lazy" '
        'referrerpolicy="no-referrer">'
        if image_url
        else '<span class="catalog-image-placeholder">Imagen no disponible</span>'
    )
    measures = (
        "".join(
            f'<li data-comparison-measure="{escape(measure.nombre, quote=True)}" '
            f'data-measure-garment="{escape(_format_measure(measure.prenda), quote=True)}" '
            f'data-measure-body="{escape(_format_measure(measure.cuerpo), quote=True)}" '
            f'data-measure-ease="{escape(_format_difference(measure.holgura), quote=True)}">'
            f'<strong>{escape(measure.nombre)}:</strong> '
            f'medida referencial {_format_measure(measure.prenda)}, '
            f'tu cuerpo {_format_measure(measure.cuerpo)}, '
            f'holgura estimada {_format_difference(measure.holgura)}</li>'
            for measure in result.medidas
        )
        if result
        else ""
    )
    fit_score = (
        f"{result.puntuacion:.6f}"
        if result and isfinite(result.puntuacion)
        else ""
    )
    fit_label = (
        f"Estimación: {result.diagnostico.etiqueta}"
        if result
        else "Sin referencia para comparar cintura y cadera"
    )
    fit_badge_label = (
        result.diagnostico.etiqueta
        if result
        else "Sin referencia de calce"
    )
    if result and result.diagnostico.etiqueta == "Ingresa tus medidas":
        fit_badge_label = "Ingresa tus medidas"
    elif result and result.diagnostico.etiqueta == "Revisión parcial":
        fit_badge_label = "Completa cintura y cadera"
    fit_badge_class = (
        result.diagnostico.clase_css
        if result and result.diagnostico.clase_css
        else "partial"
    )
    return f"""<article class="catalog-item" data-catalog-card
      data-catalog-id="{escape(product.id, quote=True)}"
      data-catalog-size="{escape(product.talla or 'No indicada', quote=True)}"
      data-catalog-bust="{escape(_format_measure(perfil.busto), quote=True)}"
      data-catalog-store="{escape(store, quote=True)}"
      data-catalog-brand="{escape(product.marca or 'No indicada', quote=True)}"
      data-catalog-fit-label="{escape(fit_label, quote=True)}"
      data-catalog-fit-badge="{escape(fit_badge_label, quote=True)}"
      data-catalog-reference="{escape(reference_label or 'Sin referencia', quote=True)}"
      data-catalog-price="{price_value}" data-catalog-fit-score="{fit_score}"
      data-catalog-index="{indice}" data-catalog-type="{escape(product.tipo_prenda, quote=True)}"
      data-catalog-searchable="{escape((store + ' ' + product.titulo + ' ' + product.marca + ' ' + product.categorias_catalogo).casefold(), quote=True)}">
      <label class="catalog-select">
        <input type="checkbox" data-catalog-select
          aria-label="Seleccionar {escape(product.titulo, quote=True)} para comparar">
        <span>Seleccionar</span>
      </label>
      <span class="catalog-fit-badge {escape(fit_badge_class, quote=True)}"
        title="{escape(fit_label, quote=True)}">{escape(fit_badge_label)}</span>
      <a class="catalog-product-link" href="{escape(product.url, quote=True)}"
        target="_blank" rel="noopener noreferrer">{image}</a>
      <div class="catalog-item-info">
        <span class="catalog-brand">{escape(store)} · {escape(product.marca)} · {escape(product.tipo_prenda)}</span>
        <h3>{escape(product.titulo)}</h3>
        <span class="catalog-product-size">Talla publicada: {escape(product.talla or "No indicada")}</span>
        <strong class="catalog-price">{_format_price(product.precio_clp)}</strong>
        <span class="catalog-fit">{escape(fit_label)}</span>
        <button class="catalog-try-on-button" type="button" data-aiuta-product
          data-aiuta-sku-id="{escape(product.id, quote=True)}">Probar virtualmente</button>
        <a class="catalog-buy-link" href="{escape(product.url, quote=True)}"
          target="_blank" rel="noopener noreferrer">Ver ficha en {escape(store)}</a>
      </div>
      <div class="catalog-item-measures" hidden>
        <ul>{measures}</ul>
      </div>
    </article>"""


def _garment_catalog(
    perfil: PerfilMedidas,
    preferencia: str,
    visible: bool = False,
    query: Optional[Dict[str, str]] = None,
) -> str:
    query = query or {}
    catalog_data = _catalog_page_data(query, perfil, preferencia)
    type_options = _option("", "Todos los tipos", query.get("type", "")) + "".join(
        _option(product_type, product_type, query.get("type", ""))
        for product_type in catalog_data["types"]
    )
    sort_options = "".join(
        _option(value, label, query.get("sort", "fit-asc"))
        for value, label in CATALOG_SORT_OPTIONS
    )
    page_number = catalog_data["page"] + 1
    page_count = catalog_data["pages"]
    visibility = "" if visible else " hidden"
    return (
        '<section class="garment-catalog" id="garment-catalog" data-garment-catalog '
        f'data-catalog-page-index="{catalog_data["page"]}" '
        f'aria-labelledby="garment-catalog-title"{visibility}>'
        '<div class="catalog-heading"><div>'
        '<h2 id="garment-catalog-title">Catálogo completo de prendas</h2></div>'
        f'<label class="catalog-sort-label" for="catalog-sort">Ordenar por'
        '<select id="catalog-sort" data-catalog-sort>'
        f'{sort_options}</select></label></div>'
        f'<div class="catalog-filters">'
        f'<label>Buscar prendas<input type="search" data-catalog-search '
        f'value="{escape(query.get("search", ""), quote=True)}" '
        'placeholder="Nombre, marca o categoría"></label>'
        f'<label>Tipo de prenda<select data-catalog-type-filter>'
        f'{type_options}</select></label></div>'
        '<p class="catalog-price-note">Productos e imágenes se consultan en las '
        "tiendas enlazadas; precios y disponibilidad pueden cambiar. Paris informa "
        f'{WOMENSWEAR_DATA["stores"]["Paris"]["results_reported"]:,} resultados y '
        f'Tricot {WOMENSWEAR_DATA["stores"]["Tricot"]["results_reported"]:,}. '
        "No se asignan medidas físicas que las fichas no publican.</p>"
        f'<p class="catalog-result-count" data-catalog-result-count '
        f'aria-live="polite">{escape(catalog_data["result_text"])}</p>'
        f'<div class="catalog-grid" data-catalog-items '
        f'data-catalog-page-size="{CATALOG_PAGE_SIZE}">{catalog_data["cards"]}</div>'
        '<nav class="catalog-pagination" data-catalog-pagination '
        'aria-label="Paginación del catálogo">'
        f'<button type="button" data-catalog-previous'
        f'{" disabled" if page_number <= 1 else ""}>← Anterior</button>'
        f'<span data-catalog-page aria-live="polite">'
        f'{escape(catalog_data["page_text"])}</span>'
        '<button type="button" data-catalog-next'
        f'{" disabled" if page_number >= page_count else ""}>Siguiente →</button>'
        '</nav>'
        '<div class="catalog-selection-bar">'
        '<span data-catalog-selection-status aria-live="polite">Ninguna prenda seleccionada</span>'
        '<button class="catalog-compare-button" type="button" '
        'data-catalog-compare disabled>Selecciona Productos a Comparar</button></div>'
        '<section class="catalog-comparison" data-catalog-comparison '
        'aria-label="Detalle de prendas seleccionadas" hidden>'
        '<h3>Detalle de prendas seleccionadas</h3>'
        '<p class="sub">Las holguras se estiman con referencias de la matriz, '
        'no con medidas verificadas en la ficha. Abre cada publicación para '
        'confirmar disponibilidad y completar la compra.</p>'
        '<div data-catalog-comparison-items></div>'
        '<p class="catalog-total" data-catalog-total></p>'
        '</section></section>'
    )


def _aiuta_try_on_panel(query: Dict[str, str]) -> str:
    sku_id = escape(query.get("sku_id", ""), quote=True)

    def _product_option(product: ProductoVestua) -> str:
        category = "superior" if re.search(
            r"\b(?:blazer|camisa|chaqueta|sueter|polera|jacket|cardigan|top|sudadera|jersey|pullover|crop|remera|camiseta|abrigo|vestido|buzo|hoodie)\b",
            " ".join((product.titulo, product.tipo_prenda, product.categorias_catalogo)).casefold(),
        ) else "inferior"
        image_url = escape(CATALOG_IMAGES_BY_URL.get(product.url, ""), quote=True)
        selected = " selected" if product.id == sku_id else ""
        return (
            f'<option value="{escape(product.id, quote=True)}" data-image-url="{image_url}" '
            f'data-category="{category}"{selected}>'
            f'{escape(product.marca)} · {escape(product.titulo)} · {escape(product.talla or "No indicada")}</option>'
        )

    product_options = "".join(_product_option(product) for product in CATALOG_PRODUCTS[:60])
    return (
        '<div class="catalog-panel try-on-page-panel">'
        '<section class="aiuta-try-on" data-aiuta-try-on '
        'aria-labelledby="aiuta-try-on-title">'
        '<header class="section-title aiuta-try-on-header">'
        '<div>'
        '<span class="eyebrow">Aiuta · Virtual Try-On</span>'
        '<h1 id="aiuta-try-on-title">Probador virtual</h1>'
        '</div>'
        '<p class="sub">Prueba prendas del catálogo sin salir de la misma experiencia de Inicio y Catálogo.</p>'
        '</header>'
        '<div class="aiuta-source-photo" data-aiuta-source-photo hidden>'
        '<img data-aiuta-source-preview alt="Foto seleccionada en Inicio">'
        '<p data-aiuta-source-caption>Se usará la foto seleccionada en Inicio.</p></div>'
        '<div class="aiuta-try-on-fields">'
        '<label>Cambiar foto (opcional)'
        '<input type="file" '
        'data-aiuta-image></label>'
        '<label>Prenda del catálogo'
        f'<select data-aiuta-product-select hidden>'
        '<option value="">Selecciona una prenda del catálogo</option>'
        f'{product_options}</select></label>'
        '<div class="aiuta-selection-list" data-aiuta-selection-list aria-live="polite"></div>'
        '<div class="aiuta-picker-groups" data-aiuta-picker-groups></div>'
        f'<input type="hidden" data-aiuta-sku value="{sku_id}" autocomplete="off">'
        '<input type="hidden" data-aiuta-catalog value="main" autocomplete="off">'
        '</div>'
        '<div class="aiuta-try-on-actions">'
        '<button type="button" class="aiuta-generate-button" data-aiuta-generate '
        'aria-label="Probar la prenda seleccionada con Aiuta">Probar prenda</button>'
        '</div>'
        '<p class="aiuta-try-on-status" data-aiuta-status role="status" '
        'aria-live="polite">Modo prueba sin sesión habilitado. Selecciona una foto y una prenda del catálogo.</p>'
        '<div class="aiuta-try-on-results" data-aiuta-results></div>'
        '</section>'
        '</div>'
    )


def _catalog_page_data(
    query: Dict[str, str],
    perfil: Optional[PerfilMedidas] = None,
    preferencia: Optional[str] = None,
) -> Dict[str, object]:
    perfil = perfil or PerfilMedidas.desde_formulario(
        {
            "bust": query.get("bust"),
            "waist": query.get("waist"),
            "hip": query.get("hip"),
        }
    )
    preferencia = preferencia or query.get("preference", "regular")
    recommendations = _catalog_recommendations(perfil, preferencia)
    types = tuple(
        sorted({product.tipo_prenda for product in CATALOG_PRODUCTS}, key=str.casefold)
    )
    normalized_search = _normalize_search_text(query.get("search", ""))
    selected_type = query.get("type", "")
    filtered = []
    for index, (product, reference, reference_label, result) in enumerate(
        recommendations
    ):
        searchable = CATALOG_SEARCH_TEXT_BY_URL[product.url]
        if selected_type and selected_type != product.tipo_prenda:
            continue
        if normalized_search and normalized_search not in searchable:
            continue
        filtered.append((index, product, reference, reference_label, result))

    sort_option = query.get("sort", "fit-asc")
    if sort_option not in {value for value, _ in CATALOG_SORT_OPTIONS}:
        sort_option = "fit-asc"
    sort_by_price = sort_option.startswith("price")
    direction = -1 if sort_option.endswith("desc") else 1

    def sort_key(item):
        index, product, _, _, result = item
        value = (
            product.precio_clp
            if sort_by_price
            else result.puntuacion if result is not None else None
        )
        missing = value is None or (sort_by_price and value <= 0)
        return (
            missing,
            (value or 0) * direction,
            index,
        )

    if sort_option != "fit-asc":
        filtered.sort(key=sort_key)
    try:
        requested_page = max(0, int(query.get("page", "0")))
    except ValueError:
        requested_page = 0
    total = len(filtered)
    page_count = (total + CATALOG_PAGE_SIZE - 1) // CATALOG_PAGE_SIZE
    page = min(requested_page, max(0, page_count - 1))
    start = page * CATALOG_PAGE_SIZE
    visible = filtered[start : start + CATALOG_PAGE_SIZE]
    cards = "".join(
        _catalog_product_card(
            product,
            reference,
            result,
            reference_label,
            index,
            preferencia,
            perfil,
        )
        for index, product, reference, reference_label, result in visible
    )
    result_text = (
        f"Mostrando {start + 1}–{min(start + CATALOG_PAGE_SIZE, total)} de "
        f"{total} prendas"
        if total
        else f"No se encontraron prendas entre {len(CATALOG_PRODUCTS)} fichas"
    )
    return {
        "cards": cards,
        "types": types,
        "total": total,
        "page": page,
        "pages": page_count,
        "result_text": result_text,
        "page_text": f"Página {page + 1} de {page_count}" if page_count else "Sin páginas",
    }


@lru_cache(maxsize=8)
def _catalog_recommendations(
    perfil: PerfilMedidas,
    preferencia: str,
) -> Tuple[
    Tuple[ProductoVestua, Optional[Prenda], str, Optional[ResultadoCalce]], ...
]:
    return tuple(sorted(
        (
            (
                product,
                reference,
                reference_label,
                _calculate_fit(reference, perfil, preferencia)
                if reference is not None
                else None,
            )
            for product in CATALOG_PRODUCTS
            for reference, reference_label in (_reference_for_listing(product),)
        ),
        key=lambda item: (
            item[3].puntuacion if item[3] is not None else float("inf"),
            item[0].id,
        ),
    ))


def _size_chart(perfil: PerfilMedidas) -> str:
    recomendadas, _ = recomendar_tallas(perfil, STANDARD_SIZES)
    tallas_recomendadas = {talla.etiqueta for talla in recomendadas}
    rows = "".join(
        (
            '<tr class="recommended-size">'
            if talla.etiqueta in tallas_recomendadas
            else "<tr>"
        )
        + f"<th scope=\"row\">{escape(talla.etiqueta)}</th>"
        + f"<td>{escape(talla.europea or '—')}</td>"
        + f"<td>{escape(talla.estadounidense or '—')}</td>"
        + f"<td>{escape(talla.busto)}</td>"
        + f"<td>{escape(talla.cintura)}</td>"
        + (
            '<td data-standard-size '
            f'data-size-bust-min="{talla.limites("busto")[0]}" '
            f'data-size-bust-max="{talla.limites("busto")[1]}" '
            f'data-size-waist-min="{talla.limites("cintura")[0]}" '
            f'data-size-waist-max="{talla.limites("cintura")[1]}" '
            f'data-size-hip-min="{talla.limites("cadera")[0]}" '
            f'data-size-hip-max="{talla.limites("cadera")[1]}">'
            f'{escape(talla.cadera)}</td></tr>'
        )
        for talla in STANDARD_SIZES
    )
    return (
        '<section class="size-chart" aria-label="Tabla de medidas y tallas">'
        '<div class="help-heading"><h3>Talla(s) según tabla estándar</h3></div>'
        '<div class="table-scroll"><table><thead><tr>'
        '<th scope="col">Talla alfa</th><th scope="col">Talla EU</th>'
        '<th scope="col">Talla EE.UU.</th>'
        '<th scope="col">Busto / pecho (cm)</th>'
        '<th scope="col">Cintura (cm)</th><th scope="col">Cadera (cm)</th>'
        '</tr></thead>'
        f"<tbody>{rows}</tbody></table></div></section>"
    )


def _format_measure(value: Optional[float]) -> str:
    return "Ingresa medida" if value is None else f"{value:.1f} cm"


def _format_difference(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{'+' if value > 0 else ''}{value:.1f} cm"


def _render_measure(measure) -> str:
    return f"""<div class="measure-card">
      <strong>{escape(measure.nombre)}</strong>
      <div class="metric"><span>Prenda</span><b>{_format_measure(measure.prenda)}</b></div>
      <div class="metric"><span>Tu cuerpo</span><b>{_format_measure(measure.cuerpo)}</b></div>
      <div class="metric"><span>Holgura</span><b>{_format_difference(measure.holgura)}</b></div>
    </div>"""


def _fit_explanation(
    resultado: ResultadoCalce,
    preferencia: str,
    elasticidad: float,
    tolerancia: float,
) -> str:
    minimum, maximum, _ = {
        "adjusted": (0, 4, 2),
        "regular": (2, 8, 5),
        "loose": (6, 14, 10),
    }.get(preferencia, (2, 8, 5))
    if elasticidad >= 8:
        minimum = max(minimum, -1)

    entered = tuple(measure for measure in resultado.medidas if measure.cuerpo is not None)
    missing = tuple(
        measure.nombre.lower()
        for measure in resultado.medidas
        if measure.cuerpo is None
    )
    if not entered:
        return "Ingresa tus medidas para comparar tu cuerpo con las medidas de esta prenda."
    if missing:
        comparison = "; ".join(
            f"{measure.nombre.lower()}: holgura {_format_difference(measure.holgura)}"
            for measure in entered
        )
        return (
            f"Revisión parcial: faltan tus medidas de {', '.join(missing)}. "
            f"Con lo ingresado, {comparison}. Completa las medidas para una comparación más completa."
        )

    status = resultado.diagnostico.etiqueta
    comparison = "; ".join(
        f"{measure.nombre.lower()}: prenda {_format_measure(measure.prenda)}, "
        f"tu cuerpo {_format_measure(measure.cuerpo)}, "
        f"holgura {_format_difference(measure.holgura)}"
        for measure in entered
    )
    if status == "Podría quedarte bien":
        reason = (
            f"Las holguras están dentro del rango orientativo de "
            f"{minimum:g} a {maximum:g} cm para el calce que elegiste."
        )
    elif status == "Podría quedar estrecha":
        affected = tuple(
            measure
            for measure in entered
            if measure.holgura < minimum - tolerancia
        )
        details = " y ".join(
            f"{measure.nombre.lower()} ({_format_difference(measure.holgura)})"
            for measure in affected
        )
        reason = (
            f"Podría quedar estrecha: las holguras de {details or 'una o más medidas'} "
            f"quedan por debajo del mínimo orientativo de {minimum:g} cm, "
            "incluso considerando la tolerancia de corte."
        )
    elif status == "Podría quedar holgada":
        affected = tuple(
            measure
            for measure in entered
            if measure.holgura > maximum + tolerancia
        )
        details = " y ".join(
            f"{measure.nombre.lower()} ({_format_difference(measure.holgura)})"
            for measure in affected
        )
        reason = (
            f"Podría quedar holgada: las holguras de {details or 'una o más medidas'} "
            f"superan el máximo orientativo de {maximum:g} cm, "
            "incluso considerando la tolerancia de corte."
        )
    elif status == "Ajuste al límite":
        affected = " y ".join(
            f"{measure.nombre.lower()} ({_format_difference(measure.holgura)})"
            for measure in entered
            if measure.holgura < minimum
        )
        reason = (
            f"Las holguras de {affected or 'una o más medidas'} están cerca del mínimo de {minimum:g} cm; "
            "el resultado puede variar dentro de la tolerancia de corte."
        )
    elif status == "Holgura al límite":
        affected = " y ".join(
            f"{measure.nombre.lower()} ({_format_difference(measure.holgura)})"
            for measure in entered
            if measure.holgura > maximum
        )
        reason = (
            f"Las holguras de {affected or 'una o más medidas'} están cerca del máximo de {maximum:g} cm; "
            "el resultado puede variar dentro de la tolerancia de corte."
        )
    else:
        reason = "La clasificación es orientativa; revisa los valores comparados."
    return f"{reason} Comparación: {comparison}. No garantiza el calce real."


def _render_product(
    prenda,
    resultado: ResultadoCalce,
    indice: int,
    preferencia: str,
) -> str:
    es_primera = indice == 0
    badge = resultado.diagnostico.etiqueta
    measures = "".join(_render_measure(measure) for measure in resultado.medidas)
    image = VESTUA_IMAGES.get(prenda.marca, {}).get(prenda.categoria, {})
    image_url = image.get("image_url", "")
    image_product_url = image.get("product_url", prenda.fuente)
    image_title = image.get("product_title", f"{prenda.categoria} {prenda.marca}")
    product_size = image.get("product_size", "")
    image_markup = (
        f'<a class="product-image-link" href="{escape(image_product_url, quote=True)}" '
        f'target="_blank" rel="noopener noreferrer" '
        f'aria-label="Ver referencia de {escape(prenda.marca, quote=True)} '
        f'{escape(prenda.categoria, quote=True)} en Vestua">'
        f'<img class="product-image" src="{escape(image_url, quote=True)}" '
        f'alt="Imagen referencial de {escape(image_title, quote=True)} en Vestua" '
        'loading="lazy" referrerpolicy="no-referrer">'
        '<span class="image-source">Imagen referencial · Vestua</span></a>'
        if image_url
        else '<div class="product-image-placeholder" aria-label="Imagen no disponible">'
        f'Referencia {escape(prenda.categoria)} · {escape(prenda.marca)} no disponible en Vestua</div>'
    )
    product_visual = (
        f'<div class="product-visual">{image_markup}'
        f'<span class="vestua-size">Talla Vestua: '
        f'<strong>{escape(product_size) if product_size else "No disponible"}</strong>'
        "</span></div>"
    )
    mold_origin = BRAND_MOLD_ORIGINS.get(prenda.marca)
    mold_origin_markup = (
        f'<div class="product-mold-origin">Molde {escape(mold_origin)}</div>'
        if mold_origin
        else ""
    )
    hidden = "" if es_primera else " hidden"
    return f"""<article class="product-card carousel-card" data-carousel-card
      aria-hidden="{'false' if es_primera else 'true'}"{hidden}>
      <div class="product-top">
        {product_visual}
        <div class="product-summary">
          <div class="product-brand">{escape(prenda.marca)} · {escape(prenda.linea)}</div>
          {mold_origin_markup}
          <div class="product-name">{escape(image_title)}</div>
          <div class="product-meta">{escape(prenda.categoria)} · Fit {escape(prenda.calce)} · {escape(prenda.tela)}<br>
            Elasticidad {prenda.elasticidad:g}% · Holgura diseño {prenda.holgura_diseno:g} cm · Origen {escape(prenda.origen)}</div>
        </div>
        <span class="recommend-badge verdict {escape(resultado.diagnostico.clase_css)}">{escape(badge)}</span>
      </div>
      <div class="fit-detail">
        <div class="fit-heading">
          <strong class="verdict {escape(resultado.diagnostico.clase_css)}">{escape(resultado.diagnostico.etiqueta)}</strong>
          <span>Referencia de medidas, no una talla</span>
        </div>
        <details class="fit-explanation">
          <summary>Ver por qué y comparar medidas</summary>
          <div class="explanation-content">
            <p>{escape(_fit_explanation(resultado, preferencia, prenda.elasticidad, prenda.tolerancia))}</p>
            <div class="measure-grid">{measures}</div>
            <div class="fit-foot">Tolerancia de la referencia: <b>±{prenda.tolerancia:g} cm</b></div>
            <p class="image-disclaimer">La ficha enlazada es una publicación de Vestua de la misma marca y categoría, no necesariamente la misma prenda de la matriz. La app compara cintura y cadera usando medidas de referencia; Vestua no publica medidas físicas específicas de esta ficha.</p>
          </div>
        </details>
      </div>
    </article>"""


def _render_store_recommendation(
    product: ProductoVestua,
    reference,
    result: ResultadoCalce,
    reference_label: str,
    index: int,
    preference: str,
    profile: PerfilMedidas,
) -> str:
    store = CATALOG_STORES_BY_URL.get(product.url, "Vestua")
    image_url = CATALOG_IMAGES_BY_URL.get(product.url, "")
    hidden = " hidden" if index else ""
    measures = "".join(_render_measure(measure) for measure in result.medidas)
    image = (
        f'<a class="product-image-link" href="{escape(product.url, quote=True)}" '
        f'target="_blank" rel="noopener noreferrer">'
        f'<img class="product-image" src="{escape(image_url, quote=True)}" '
        f'alt="Imagen de {escape(product.titulo, quote=True)} en {escape(store, quote=True)}" '
        'loading="lazy" referrerpolicy="no-referrer">'
        f'<span class="image-source">Ver prenda · {escape(store)}</span></a>'
        if image_url
        else '<div class="product-image-placeholder">Imagen no disponible</div>'
    )
    fit_description = _fit_explanation(
        result,
        preference,
        getattr(reference, "elasticidad", 0),
        getattr(reference, "tolerancia", 0),
    )
    return f"""<article class="product-card carousel-card store-recommendation-card"
      data-carousel-card aria-hidden="{'true' if index else 'false'}"{hidden}>
      <div class="product-top">
        <div class="product-visual">{image}
          <span class="vestua-size">Talla publicada: <strong>{escape(product.talla or "No indicada")}</strong></span>
        </div>
        <div class="product-summary">
          <div class="product-brand">{escape(store)} · {escape(product.marca or store)}</div>
          <div class="product-name">{escape(product.titulo)}</div>
          <div class="product-meta">{escape(product.tipo_prenda)} · {_format_price(product.precio_clp)}<br>
            Referencia estimada: {escape(reference_label)}</div>
          <a class="catalog-buy-link" href="{escape(product.url, quote=True)}"
            target="_blank" rel="noopener noreferrer">Ver prenda en {escape(store)}</a>
        </div>
        <span class="recommend-badge verdict {escape(result.diagnostico.clase_css)}">
          {escape(result.diagnostico.etiqueta)}</span>
      </div>
      <div class="fit-detail">
        <div class="fit-heading">
          <strong class="verdict {escape(result.diagnostico.clase_css)}">
            {escape(result.diagnostico.etiqueta)}</strong>
          <span>Estimación con medidas de referencia</span>
        </div>
        <details class="fit-explanation">
          <summary>Ver medidas comparadas</summary>
          <div class="explanation-content">
            <p>{escape(fit_description)}</p>
            <div class="measure-grid">{measures}</div>
            <p class="image-disclaimer">La tienda no publica medidas físicas específicas de esta prenda. La talla corresponde a la ficha enlazada; confirma la guía de tallas antes de comprar.</p>
          </div>
        </details>
      </div>
    </article>"""


def _store_listing_recommendations(
    profile: PerfilMedidas,
    preference: str,
    categories_allowed: Optional[Tuple[str, ...]] = None,
) -> str:
    if not any(value is not None for value in profile.como_diccionario().values()):
        return ""
    compatible = {
        "Podría quedarte bien",
        "Ajuste al límite",
        "Holgura al límite",
    }
    recommendations = []
    for product in CATALOG_PRODUCTS:
        if product.url not in WOMENSWEAR_STORES_BY_URL:
            continue
        if (
            categories_allowed is not None
            and product.categoria_referencia not in categories_allowed
        ):
            continue
        reference, reference_label = _reference_for_listing(product)
        if reference is None:
            continue
        if categories_allowed is not None and reference.categoria not in categories_allowed:
            continue
        result = _calculate_fit(reference, profile, preference)
        if (
            isfinite(result.puntuacion)
            and result.diagnostico.etiqueta in compatible
        ):
            recommendations.append(
                (product, reference, result, reference_label)
            )
    recommendations.sort(key=lambda item: (item[2].puntuacion, item[0].id))
    store_favorites = []
    for store in ("Paris", "Tricot"):
        favorite = next(
            (item for item in recommendations
             if WOMENSWEAR_STORES_BY_URL.get(item[0].url) == store),
            None,
        )
        if favorite:
            store_favorites.append(favorite)
    selected_ids = {item[0].id for item in store_favorites}
    recommendations = store_favorites + [
        item for item in recommendations if item[0].id not in selected_ids
    ][: 9 - len(store_favorites)]
    recommendations.sort(key=lambda item: (item[2].puntuacion, item[0].id))
    if not recommendations:
        return ""

    slides = "".join(
        _render_store_recommendation(
            product,
            reference,
            result,
            reference_label,
            index,
            preference,
            profile,
        )
        for index, (product, reference, result, reference_label)
        in enumerate(recommendations)
    )
    controls = (
        '<div class="carousel-controls" data-carousel-controls>'
        '<button class="carousel-arrow" type="button" data-previous '
        'aria-label="Ver prenda de tienda anterior" disabled>←</button>'
        '<span class="carousel-position" data-carousel-position '
        'aria-live="polite">Recomendado · 1 de '
        f'{len(recommendations)}</span>'
        '<button class="carousel-arrow" type="button" data-next '
        'aria-label="Ver siguiente prenda de tienda"'
        f'{" disabled" if len(recommendations) == 1 else ""}>→</button>'
        "</div>"
    )
    return (
        '<section class="alternative-recommendations store-listing-recommendations" '
        'id="store-listing-recommendations" aria-labelledby="store-listing-title">'
        '<div class="alternative-heading">'
        '<h2 id="store-listing-title">Prendas de tiendas que podrían quedarte bien</h2>'
        '<p class="sub">Productos disponibles en las tiendas del catálogo, '
        "ordenados por coincidencia con tus medidas. Las medidas de la prenda "
        "son referencias de calce, no datos publicados en la ficha.</p>"
        "</div>"
        '<div class="recommendation-carousel" data-carousel data-store-listing-carousel>'
        f'<div class="carousel-slides">{slides}</div>{controls}</div></section>'
    )


def _alternative_recommendations(
    perfil: PerfilMedidas,
    preferencia: str,
    productos_mostrados: tuple,
    categorias_permitidas: Optional[Tuple[str, ...]] = None,
) -> str:
    if not any(value is not None for value in perfil.como_diccionario().values()):
        return ""

    diagnosticos_compatibles = {
        "Podría quedarte bien",
        "Ajuste al límite",
        "Holgura al límite",
    }
    recomendaciones = sorted(
        (
            (prenda, CALCULATOR.calcular(prenda, perfil, preferencia))
            for prenda in CATALOG.prendas
            if prenda not in productos_mostrados
            and (
                categorias_permitidas is None
                or prenda.categoria in categorias_permitidas
            )
        ),
        key=lambda item: item[1].puntuacion,
    )
    recomendaciones = tuple(
        (prenda, resultado)
        for prenda, resultado in recomendaciones
        if resultado.diagnostico.etiqueta in diagnosticos_compatibles
    )
    if not recomendaciones:
        return ""

    slides = "".join(
        _render_product(prenda, resultado, indice, preferencia)
        for indice, (prenda, resultado) in enumerate(recomendaciones)
    )
    controls = (
        '<div class="carousel-controls" data-carousel-controls>'
        '<button class="carousel-arrow" type="button" data-previous '
        'aria-label="Ver opción compatible anterior" disabled>←</button>'
        '<span class="carousel-position" data-carousel-position '
        'aria-live="polite">Recomendado · 1 de '
        f'{len(recomendaciones)}</span>'
        '<button class="carousel-arrow" type="button" data-next '
        'aria-label="Ver opción compatible siguiente"'
        f'{" disabled" if len(recomendaciones) == 1 else ""}>→</button>'
        "</div>"
    )
    return (
        '<section class="alternative-recommendations" '
        'id="alternative-recommendations" aria-labelledby="alternative-title">'
        '<div class="alternative-heading">'
        '<h2 id="alternative-title">Otras opciones que podrían quedarte bien</h2>'
        '<p class="sub">Prendas con calce compatible o cercano, ordenadas por '
        "coincidencia. Se omiten las referencias del carrusel principal.</p>"
        "</div>"
        '<div class="recommendation-carousel" data-carousel data-alternative-carousel>'
        '<div class="carousel-tabs">'
        '<button class="carousel-tab active" type="button" data-recommended '
        'aria-pressed="true">★ Recomendado</button>'
        '<span class="carousel-hint">Usa las flechas para ver otras opciones</span>'
        "</div>"
        f'<div class="carousel-slides">{slides}</div>{controls}</div></section>'
    )


def renderizar_pagina(query: Dict[str, str]) -> str:
    marca = query.get("brand", "Zara")
    categoria = query.get("category", "")
    grupo_categoria = query.get("category_group", "")
    wizard_step = query.get("wizard_step", "1")
    if wizard_step not in {"1", "2", "3"}:
        wizard_step = "1"
    if categoria not in CATALOG.categorias():
        categoria = ""
    if grupo_categoria not in CATEGORY_GROUPS:
        grupo_categoria = ""
    preferencia = query.get("preference", "regular")
    perfil = PerfilMedidas.desde_formulario(
        {
            "bust": query.get("bust"),
            "waist": query.get("waist"),
            "hip": query.get("hip"),
        }
    )
    requested_view = query.get("view")
    active_view = (
        requested_view
        if requested_view in {"catalog", "account", "try-on"}
        else "home"
    )
    categorias_permitidas = (
        CATALOG.categorias()
        if not grupo_categoria and not categoria
        else CATEGORY_GROUPS.get(
            grupo_categoria,
            (categoria,) if categoria else CATALOG.categorias(),
        )
    )
    prendas = tuple(
        prenda
        for prenda in CATALOG.filtrar(
            marca=marca if marca in CATALOG.marcas() else ""
        )
        if categorias_permitidas is None or prenda.categoria in categorias_permitidas
    )
    hay_filtro = (
        ("brand" in query and marca in CATALOG.marcas())
        or (
            "category" in query
            and categoria in CATALOG.categorias())
        or ("category_group" in query and grupo_categoria in CATEGORY_GROUPS)
    )
    hay_medida = any(
        valor is not None for valor in perfil.como_diccionario().values()
    )
    puede_recomendar = hay_medida or hay_filtro
    recomendaciones = sorted(
        (
            (prenda, CALCULATOR.calcular(prenda, perfil, preferencia))
            for prenda in prendas
        ),
        key=lambda elemento: elemento[1].puntuacion,
    )
    variables = "".join(
        f"""<article class="variable">
          <div class="variable-top"><strong>{escape(nombre)}</strong>
            <span class="impact {escape(impacto.lower().replace(' ', '-'))}">{escape(impacto)}</span></div>
          <span class="variable-category">{escape(grupo)}</span>
          <p>{escape(descripcion)}</p>
        </article>"""
        for grupo, nombre, descripcion, impacto in sorted(
            VARIABLES,
            key=lambda variable: IMPACT_PRIORITY.get(variable[3], len(IMPACT_PRIORITY)),
        )
    )
    catalog_query = {"view": "catalog", "preference": preferencia}
    for measurement in ("bust", "waist", "hip"):
        if query.get(measurement):
            catalog_query[measurement] = query[measurement]
    catalog_url = f"/?{urlencode(catalog_query)}"
    home_tab_query = dict(query)
    home_tab_query.pop("view", None)
    home_tab_url = "/?" + urlencode(home_tab_query) if home_tab_query else "/"
    catalog_tab_query = dict(query)
    catalog_tab_query["view"] = "catalog"
    catalog_tab_url = f"/?{urlencode(catalog_tab_query)}"
    try_on_tab_query = dict(query)
    try_on_tab_query["view"] = "try-on"
    try_on_tab_url = f"/?{urlencode(try_on_tab_query)}"
    auth_base_query = {"view": "account", "wizard_step": "2"}
    auth_base_query["auth_mode"] = "sign-in"
    sign_in_url = f"/?{urlencode(auth_base_query)}"
    auth_base_query["auth_mode"] = "sign-up"
    sign_up_url = f"/?{urlencode(auth_base_query)}"
    garment_catalog = _garment_catalog(
        perfil, preferencia, visible=True, query=query
    )
    aiuta_try_on_panel = _aiuta_try_on_panel(query)
    personal_recommendations = _personal_recommendations(
        perfil,
        preferencia,
        catalog_url,
    )
    alternative_recommendations = _alternative_recommendations(
        perfil,
        preferencia,
        prendas,
        CATEGORY_GROUPS.get(grupo_categoria),
    )
    store_recommendations = _store_listing_recommendations(
        perfil,
        preferencia,
        CATEGORY_GROUPS.get(grupo_categoria)
        or ((categoria,) if categoria else None),
    )
    size_chart = _size_chart(perfil)
    results_heading = (
        '<div class="results-head">'
        '<div><h2>Tus mejores opciones</h2>'
        '<p class="sub">Holgura positiva = la prenda mide más que tu cuerpo.</p></div>'
        f'<span class="count">{len(prendas)} '
        f'{"referencia" if len(prendas) == 1 else "referencias"}</span>'
        '</div>'
        if hay_filtro
        else ""
    )
    if not puede_recomendar:
        results_panel_content = (
            f'<a class="catalog-toggle" href="{escape(catalog_url, quote=True)}" '
            'aria-controls="catalog-panel">'
            "Abrir catálogo completo</a>"
        )
    elif recomendaciones:
        slides = "".join(
            _render_product(prenda, resultado, indice, preferencia)
            for indice, (prenda, resultado) in enumerate(recomendaciones)
        )
        controls = (
            '<div class="carousel-controls" data-carousel-controls>'
            '<button class="carousel-arrow" type="button" data-previous '
            'aria-label="Ver recomendación anterior" disabled>←</button>'
            '<span class="carousel-position" data-carousel-position '
            'aria-live="polite">Recomendado · 1 de '
            f'{len(recomendaciones)}</span>'
            '<button class="carousel-arrow" type="button" data-next '
            'aria-label="Ver recomendación siguiente"'
            f'{" disabled" if len(recomendaciones) == 1 else ""}>→</button>'
            "</div>"
        )
        html_resultados = (
            '<div class="recommendation-carousel" data-carousel>'
            '<div class="carousel-tabs">'
            '<button class="carousel-tab active" type="button" data-recommended '
            'aria-pressed="true">★ Recomendado</button>'
            '<span class="carousel-hint">Usa las flechas para ver otras opciones</span>'
            "</div>"
            f'<div class="carousel-slides">{slides}</div>{controls}</div>'
        )
        results_panel_content = (
            '<div class="results-content" aria-live="polite">'
            f"{personal_recommendations}{results_heading}{html_resultados}</div>"
        )
    else:
        html_resultados = (
            '<div class="empty">No encontramos referencias con esos filtros. '
            "Prueba con otra marca o tipo de prenda.</div>"
        )
        results_panel_content = (
            '<div class="results-content" aria-live="polite">'
            f"{personal_recommendations}{results_heading}{html_resultados}</div>"
        )
    template = (WEB_DIRECTORY / "index.html").read_text(encoding="utf-8")
    return template.format(
        supabase_url=escape(SUPABASE_URL, quote=True),
        supabase_publishable_key=escape(SUPABASE_PUBLISHABLE_KEY, quote=True),
        startup_dialogs=(
            ""
            if active_view in {"catalog", "try-on"}
            else (
                '<dialog class="welcome-dialog" data-startup-dialog '
                'aria-labelledby="welcome-title">'
                '<div class="welcome-window">'
                '<span class="welcome-eyebrow">Tu guía de calce personal</span>'
                '<h1 id="welcome-title">Encuentra prendas que podrían quedarte bien.</h1>'
                '</div></dialog>'
                '<dialog class="welcome-dialog welcome-dialog--second" '
                'data-startup-dialog aria-labelledby="preferences-title">'
                '<div class="welcome-window">'
                '<p class="welcome-message" id="preferences-title">'
                'Tu cuerpo, tus preferencias.</p></div></dialog>'
            )
        ),
        measurement_fields=_measurement_fields(query),
        wizard_step=wizard_step,
        results_panel_content=results_panel_content,
        wizard_page_results_hidden=(
            " hidden" if active_view != "home" or wizard_step != "3" else ""
        ),
        alternative_recommendations=alternative_recommendations,
        store_recommendations=store_recommendations,
        garment_catalog=garment_catalog,
        aiuta_try_on_panel=aiuta_try_on_panel,
        size_chart=size_chart,
        variables=variables,
        home_tab_url=escape(home_tab_url, quote=True),
        catalog_tab_url=escape(catalog_tab_url, quote=True),
        try_on_tab_url=escape(try_on_tab_url, quote=True),
        sign_in_url=escape(sign_in_url, quote=True),
        sign_up_url=escape(sign_up_url, quote=True),
        home_link_current=' aria-current="page"' if active_view == "home" else "",
        catalog_link_current=' aria-current="page"' if active_view == "catalog" else "",
        try_on_link_current=' aria-current="page"' if active_view == "try-on" else "",
        sign_in_link_current=(
            ' aria-current="page"'
            if active_view == "account" and query.get("auth_mode") != "sign-up"
            else ""
        ),
        sign_up_link_current=(
            ' aria-current="page"'
            if active_view == "account" and query.get("auth_mode") == "sign-up"
            else ""
        ),
        home_panel_hidden=(
            ' hidden' if active_view in {"catalog", "try-on"} else ""
        ),
        catalog_panel_hidden=' hidden' if active_view != "catalog" else "",
        try_on_panel_hidden=' hidden' if active_view != "try-on" else "",
    )


class MedidasRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send_content("ok", "text/plain; charset=utf-8")
            return
        if parsed.path == "/api/catalog":
            query = {
                key: values[-1]
                for key, values in parse_qs(
                    parsed.query, keep_blank_values=True
                ).items()
            }
            data = _catalog_page_data(query)
            self._send_content(
                json.dumps(data, ensure_ascii=False),
                "application/json; charset=utf-8",
            )
            return
        if parsed.path == "/":
            query = {
                key: values[-1]
                for key, values in parse_qs(
                    parsed.query, keep_blank_values=True
                ).items()
            }
            self._send_content(renderizar_pagina(query), "text/html; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._send_static_file(WEB_DIRECTORY / "styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_static_file(
                WEB_DIRECTORY / "app.js", "text/javascript; charset=utf-8"
            )
            return
        if parsed.path.startswith("/assets/"):
            asset = (WEB_DIRECTORY / parsed.path.lstrip("/")).resolve()
            if WEB_DIRECTORY.resolve() not in asset.parents:
                self.send_error(404, "Recurso no encontrado")
                return
            content_type = guess_type(str(asset))[0] or "application/octet-stream"
            self._send_static_file(asset, content_type)
            return
        self.send_error(404, "Página no encontrada")

    def _send_static_file(self, path: Path, content_type: str) -> None:
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, "Recurso no encontrado")
            return
        except OSError as error:
            self.send_error(500, f"No se pudo leer el recurso: {error}")
            return
        self._send_content(
            content,
            content_type,
            cache_control="public, max-age=3600",
        )

    def _send_content(
        self,
        content,
        content_type: str,
        cache_control: Optional[str] = None,
        status: int = 200,
    ) -> None:
        if isinstance(content, str):
            content = content.encode("utf-8")
        encoding_quality = {}
        for encoding in self.headers.get("Accept-Encoding", "").split(","):
            name, *parameters = encoding.strip().lower().split(";")
            if not name:
                continue
            quality = next(
                (
                    parameter.strip()[2:]
                    for parameter in parameters
                    if parameter.strip().startswith("q=")
                ),
                "1",
            )
            try:
                encoding_quality[name] = float(quality)
            except ValueError:
                encoding_quality[name] = 0
        accepts_gzip = encoding_quality.get(
            "gzip", encoding_quality.get("*", 0)
        ) > 0
        compressed = False
        if accepts_gzip and len(content) >= 1024:
            compressed_content = gzip.compress(content, compresslevel=5, mtime=0)
            if len(compressed_content) < len(content):
                content = compressed_content
                compressed = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Vary", "Accept-Encoding")
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def iniciar_servidor(
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> None:
    host = host or os.environ.get("HOST", "0.0.0.0" if IS_RENDER else HOST)
    port = port or int(os.environ.get("PORT", str(PORT)))
    servidor = ThreadingHTTPServer((host, port), MedidasRequestHandler)
    url = f"http://{host}:{port}/"
    print(f"Medidas está disponible en {url}")
    if not IS_RENDER:
        try:
            _abrir_navegador(url)
        except (OSError, subprocess.CalledProcessError, webbrowser.Error) as error:
            print(f"No se pudo abrir Chrome automáticamente: {error}")
            print(f"Abre esta dirección manualmente: {url}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        servidor.server_close()


def _abrir_navegador(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(
            ["open", "-a", "Google Chrome", url],
            check=True,
            capture_output=True,
            text=True,
        )
        return

    if not webbrowser.open(url):
        raise webbrowser.Error("No se encontró un navegador disponible.")


if __name__ == "__main__":
    iniciar_servidor()
