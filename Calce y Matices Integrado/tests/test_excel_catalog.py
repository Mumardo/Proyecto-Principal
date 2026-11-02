import unittest
import json
import base64
import os
from math import isfinite
from html import escape
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import tempfile
import threading
from unittest.mock import patch

from medidas.perfil_medidas import PerfilMedidas
from medidas.tallas import RepositorioTallasEstandar, recomendar_tallas
from metricas.calculadora_calce import CalculadoraCalce
from prendas import CatalogoPrendas, RepositorioExcelPrendas, RepositorioVestua
from scripts.importar_catalogo_mujer import (
    _paris_product,
    _paris_search_configuration,
)
from web.servidor import (
    CATALOG,
    CATALOG_PRODUCTS,
    CALCULATOR,
    VESTUA_PRODUCTS,
    WOMENSWEAR_DATA,
    WOMENSWEAR_PRODUCTS,
    MedidasRequestHandler,
    _is_footwear,
    _load_environment_file,
    _is_valid_access_authorization,
    _catalog_page_data,
    _catalog_recommendations,
    _reference_for_listing,
    renderizar_pagina,
)


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "data" / "Matriz_Medidas_Marcas_Vestua.xlsx"
VESTUA_IMAGES = ROOT / "data" / "vestua_images.json"
STANDARD_SIZES = ROOT / "data" / "Tabla_estandar.xlsx"


class ExcelCatalogTests(unittest.TestCase):
    def setUp(self):
        self.repository = RepositorioExcelPrendas(MATRIX)

    def test_loads_products_and_variables_from_the_workbook(self):
        products = self.repository.cargar_prendas()
        variables = self.repository.cargar_variables()

        self.assertEqual(len(products), 42)
        self.assertEqual(len(variables), 14)
        self.assertEqual((products[0].marca, products[0].linea), ("Zara", "Zara Woman"))
        self.assertEqual(products[0].tolerancia, 1)

    def test_duplicate_products_across_lines_are_removed(self):
        products = self.repository.cargar_prendas()
        identities = {
            self.repository._identidad_prenda(product) for product in products
        }
        catalog = CatalogoPrendas(products)

        self.assertEqual(len(products), len(identities))
        self.assertEqual(len(catalog.marcas()), 6)
        self.assertEqual(len(catalog.categorias()), 7)
        self.assertEqual(len(catalog.filtrar(marca="Zara")), 7)
        self.assertEqual(len(catalog.filtrar(marca="ASOS")), 7)

    def test_recommendation_catalog_omits_unlisted_vestua_combinations(self):
        self.assertEqual(len(CATALOG.prendas), 38)
        for brand, category in (
            ("ASOS", "Polera"),
            ("Levi's", "Blazer"),
            ("Nike", "Jeans"),
            ("Nike", "Blazer"),
        ):
            with self.subTest(brand=brand, category=category):
                self.assertEqual(
                    CATALOG.filtrar(marca=brand, categoria=category), ()
                )

    def test_vestua_snapshot_contains_584_unique_publications(self):
        products = RepositorioVestua(ROOT / "data" / "vestua_catalog.json").cargar()

        self.assertEqual(len(products), 584)
        self.assertEqual(len({product.id for product in products}), 584)
        self.assertEqual(len({product.url for product in products}), 584)
        self.assertEqual(sum(product.precio_clp is None for product in products), 0)
        self.assertTrue(all(product.fecha_consulta == "2026-10-29" for product in products))

    def test_catalog_excludes_all_footwear(self):
        source_products = RepositorioVestua(
            ROOT / "data" / "vestua_catalog.json"
        ).cargar()
        footwear = [product for product in source_products if _is_footwear(product)]

        self.assertEqual(len(footwear), 3)
        self.assertTrue(
            all(
                any(term in product.tipo_prenda.casefold() for term in ("sandalia", "zapatilla"))
                for product in footwear
            )
        )
        self.assertFalse(any(_is_footwear(product) for product in CATALOG_PRODUCTS))

    def test_womenswear_store_snapshot_contains_imported_products(self):
        stores = WOMENSWEAR_DATA["stores"]
        tricot_products = [
            product for product in WOMENSWEAR_DATA["products"]
            if product["store"] == "Tricot"
        ]
        paris_products = [
            product for product in WOMENSWEAR_DATA["products"]
            if product["store"] == "Paris"
        ]

        self.assertEqual(len(tricot_products), stores["Tricot"]["products_collected"])
        self.assertEqual(len(paris_products), stores["Paris"]["products_collected"])
        self.assertEqual(
            len(WOMENSWEAR_PRODUCTS),
            len(tricot_products) + len(paris_products),
        )
        self.assertGreater(len(tricot_products), 2000)
        self.assertTrue(
            all(
                item["url"].startswith(
                    ("https://www.tricot.cl/", "https://www.paris.cl/")
                )
                and item["image_url"].startswith("https://")
                for item in WOMENSWEAR_DATA["products"]
            )
        )
        self.assertFalse(any(_is_footwear(product) for product in WOMENSWEAR_PRODUCTS))

    def test_paris_api_product_mapping_keeps_product_links_and_offer_prices(self):
        page = (
            r'\"searchQueryArgs\":{\"filters\":[{\"key\":\"group_id\",'
            r'\"stringValues\":[\"mujModa\"]}],\"applicationId\":'
            r'\"34bb8686968a85a272a6c546ddcb9860db1ea14ee72f5207ef0c028280a6e7bc\"},'
            r'\"facetsSearchQueryArgs\":{}'
        )
        item = {
            "id": "478798",
            "name": {"es-CL": "Blusa Manga Corta"},
            "slug": {"es-CL": "blusa-manga-corta-478798"},
            "brand": {"es-CL": "Alaniz"},
            "masterVariant": {
                "images": [{"url": "https://images.paris.cl/item.jpg"}],
                "prices": {
                    "regular": {"value": {"centAmount": 16990}},
                    "offer": {"value": {"centAmount": 13490}},
                },
            },
        }

        self.assertEqual(
            _paris_search_configuration(page),
            (
                "mujModa",
                "34bb8686968a85a272a6c546ddcb9860db1ea14ee72f5207ef0c028280a6e7bc",
            ),
        )
        product = _paris_product(item)
        self.assertIsNotNone(product)
        self.assertEqual(product["url"], "https://www.paris.cl/blusa-manga-corta-478798.html")
        self.assertEqual(product["price_clp"], 13490)
        self.assertEqual(product["image_url"], "https://images.paris.cl/item.jpg")
        item["name"] = {"es-CL": "Zapatilla Urbana"}
        self.assertIsNone(_paris_product(item))
        item["name"] = {"es-CL": "Modelo casual"}
        item["categories"] = [{"id": "mujModZapatos"}]
        self.assertIsNone(_paris_product(item))

    def test_parses_elastane_percentages_from_fabric(self):
        products = self.repository.cargar_prendas()

        self.assertEqual(products[0].elasticidad, 0)
        self.assertEqual(products[1].elasticidad, 3)
        self.assertEqual(products[6].elasticidad, 15)

    def test_catalog_filters_excel_rows_and_calculates_pants(self):
        catalog = CatalogoPrendas(self.repository.cargar_prendas())

        blouses = catalog.filtrar(marca="Zara", categoria="Blusa")
        pants = catalog.filtrar(categoria="Pantalon")[0]
        profile = PerfilMedidas(cintura=74, cadera=100)
        fit = CalculadoraCalce().calcular(pants, profile)

        self.assertEqual(len(blouses), 1)
        self.assertEqual(
            [measure.nombre for measure in fit.medidas], ["Cintura", "Cadera"]
        )
        self.assertEqual([measure.holgura for measure in fit.medidas], [2, 2])

    def test_lower_garment_recommendation_uses_only_waist_and_hip(self):
        catalog = CatalogoPrendas(self.repository.cargar_prendas())
        calculator = CalculadoraCalce()
        profile = PerfilMedidas(
            busto=155,
            cintura=74,
            cadera=100,
            largo=40,
        )

        for category in ("Pantalon", "Jeans"):
            garment = catalog.filtrar(categoria=category)[0]
            result = calculator.calcular(garment, profile)
            another_profile = PerfilMedidas(
                busto=45,
                cintura=74,
                cadera=100,
                largo=170,
            )
            result_with_irrelevant_measurements = calculator.calcular(
                garment, another_profile
            )

            with self.subTest(category=category):
                self.assertEqual(
                    [measure.nombre for measure in result.medidas],
                    ["Cintura", "Cadera"],
                )
                self.assertIsNone(result.diferencia_largo)
                self.assertEqual(
                    result.puntuacion,
                    result_with_irrelevant_measurements.puntuacion,
                )

    def test_every_garment_category_uses_only_waist_and_hip(self):
        calculator = CalculadoraCalce()
        profile = PerfilMedidas(
            busto=160,
            cintura=70,
            cadera=96,
            largo=40,
        )
        altered_irrelevant_measures = PerfilMedidas(
            busto=40,
            cintura=70,
            cadera=96,
            largo=170,
        )

        for garment in self.repository.cargar_prendas():
            result = calculator.calcular(garment, profile)
            result_without_irrelevant_measures = calculator.calcular(
                garment, altered_irrelevant_measures
            )
            with self.subTest(category=garment.categoria):
                self.assertEqual(
                    [measure.nombre for measure in result.medidas],
                    ["Cintura", "Cadera"],
                )
                self.assertEqual(
                    result.puntuacion,
                    result_without_irrelevant_measures.puntuacion,
                )

    def test_page_renders_product_and_variable_data_from_excel(self):
        page = renderizar_pagina(
            {"brand": "Zara", "category": "Blusa", "waist": "70", "hip": "96"}
        )

        self.assertIn("1 referencia", page)
        self.assertIn("<h2>Tus mejores opciones</h2>", page)
        self.assertIn(
            '<section class="wizard-step" data-wizard-panel="2" '
            'aria-labelledby="wizard-measures-title" hidden>',
            page,
        )
        self.assertNotIn("Ver recomendaciones", page)
        self.assertIn("Zara · Zara Woman", page)
        self.assertIn("Slim-Regular-Oversize", page)
        self.assertIn('data-carousel', page)
        self.assertIn('data-recommended', page)
        self.assertIn('data-previous', page)
        self.assertIn('data-next', page)
        self.assertIn('Recomendado · 1 de 1', page)
        self.assertEqual(
            page.split("data-alternative-carousel", 1)[0].count("data-carousel-card"),
            1,
        )
        self.assertIn('class="recommend-badge verdict tight">Podría quedar estrecha', page)
        self.assertIn('<summary>Ver por qué y comparar medidas</summary>', page)
        self.assertIn("podría quedar estrecha", page.lower())
        self.assertIn("las holguras de cintura (0.0 cm) y cadera (0.0 cm) quedan", page)
        self.assertIn("cadera (0.0 cm)", page)
        self.assertIn('class="product-image"', page)
        self.assertIn('href="https://www.vestua.cl/store/product/', page)
        self.assertIn('<div class="product-name">Camisa Zara</div>', page)
        self.assertIn("no necesariamente la misma prenda", page)

    def test_page_renders_complete_sortable_and_selectable_catalog(self):
        page = renderizar_pagina(
            {
                "view": "catalog",
                "brand": "Zara",
                "waist": "70",
                "hip": "96",
            }
        )
        catalog = page.split('data-garment-catalog', 1)[1].split("</section>", 1)[0]

        page_size = min(9, len(CATALOG_PRODUCTS))
        self.assertEqual(catalog.count("data-catalog-card"), page_size)
        self.assertEqual(len(CATALOG_PRODUCTS), len(WOMENSWEAR_PRODUCTS) + 6)
        self.assertEqual(catalog.count('class="catalog-image"'), page_size)
        self.assertEqual(
            catalog.count('class="catalog-product-link"'),
            page_size,
        )
        self.assertNotIn("catalog-image-placeholder", catalog)
        self.assertIn('value="price-asc">Precio: menor a mayor</option>', catalog)
        self.assertIn('value="price-desc">Precio: mayor a menor</option>', catalog)
        self.assertIn('value="fit-asc" selected>Mejor calce</option>', catalog)
        self.assertIn('value="fit-desc">Peor calce</option>', catalog)
        self.assertIn('data-catalog-select', catalog)
        self.assertNotIn("consulta del 2026-10-29", catalog)
        self.assertNotIn(
            "El calce es una estimación con medidas de referencia",
            catalog,
        )
        self.assertIn("data-catalog-type-filter", catalog)
        self.assertIn('data-catalog-page-size="9"', catalog)
        self.assertIn('data-catalog-previous disabled', catalog)
        self.assertIn(
            f"Página 1 de {(len(CATALOG_PRODUCTS) + 8) // 9}",
            catalog,
        )
        self.assertNotIn('data-catalog-card hidden', catalog)
        for store in ("Tricot", "Paris"):
            sample = next(
                product for product in WOMENSWEAR_DATA["products"]
                if product["store"] == store
            )
            matching_page = _catalog_page_data({"search": sample["title"]})
            self.assertIn(
                f'<a class="catalog-product-link" href="{escape(sample["url"], quote=True)}"',
                matching_page["cards"],
            )
            self.assertIn(
                f'src="{escape(sample["image_url"], quote=True)}"',
                matching_page["cards"],
            )
            self.assertIn(f"Ver ficha en {store}", matching_page["cards"])
        self.assertIn("referencia de matriz para", catalog)
        self.assertNotIn("Explora tiendas de ropa de mujer en Chile", catalog)
        self.assertNotIn('class="catalog-shops"', catalog)
        self.assertIn(
            'data-catalog-compare disabled>Selecciona Productos a Comparar</button>',
            catalog,
        )
        self.assertIn('data-catalog-comparison-items', catalog)

    def test_catalog_search_and_pagination_cover_the_full_snapshot(self):
        first_page = _catalog_page_data({"sort": "fit-asc"})
        second_page = _catalog_page_data({"sort": "fit-asc", "page": "1"})
        first_ids = set(re.findall(r'data-catalog-id="([^"]+)"', first_page["cards"]))
        second_ids = set(re.findall(r'data-catalog-id="([^"]+)"', second_page["cards"]))
        target = next(
            product for product in WOMENSWEAR_DATA["products"]
            if product["store"] == "Paris"
        )
        search_result = _catalog_page_data(
            {"search": target["title"], "type": target["type"]}
        )

        self.assertEqual(first_page["total"], len(CATALOG_PRODUCTS))
        self.assertEqual(first_page["pages"], (len(CATALOG_PRODUCTS) + 8) // 9)
        self.assertEqual(first_page["cards"].count("data-catalog-card"), 9)
        self.assertEqual(second_page["page"], 1)
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertGreaterEqual(search_result["total"], 1)
        self.assertIn(target["url"], search_result["cards"])

    def test_catalog_reuses_fit_recommendations_for_the_same_profile(self):
        query = {
            "bust": "103.5",
            "waist": "77.25",
            "hip": "101.75",
            "preference": "loose",
            "search": "blusa",
        }
        first_result = _catalog_page_data(query)
        hits_before_repeat = _catalog_recommendations.cache_info().hits

        repeated_result = _catalog_page_data(query)

        self.assertEqual(repeated_result, first_result)
        self.assertEqual(
            _catalog_recommendations.cache_info().hits,
            hits_before_repeat + 1,
        )

    def test_catalog_badge_uses_home_waist_and_hip_for_fit_diagnosis(self):
        page = _catalog_page_data(
            {"bust": "90", "waist": "70", "hip": "96"}
        )
        first_id = re.search(r'data-catalog-id="([^"]+)"', page["cards"]).group(1)
        product = next(product for product in CATALOG_PRODUCTS if product.id == first_id)
        reference, _ = _reference_for_listing(product)
        profile = PerfilMedidas(busto=90, cintura=70, cadera=96)
        expected = CALCULATOR.calcular(reference, profile)

        self.assertIn(
            f'data-catalog-fit-badge="{expected.diagnostico.etiqueta}"',
            page["cards"],
        )
        self.assertIn(
            f'class="catalog-fit-badge {expected.diagnostico.clase_css}"',
            page["cards"],
        )
        self.assertIn('data-catalog-bust="90.0 cm"', page["cards"])

    def test_wizard_can_finish_into_catalog_with_measurements_and_fit_preference(self):
        wizard_page = renderizar_pagina({"wizard_step": "3"})
        self.assertRegex(
            wizard_page,
            r'<button class="matices-button matices-button-primary" type="submit"\s+'
            r'name="view" value="catalog">Cerrar asistente e ir al catálogo</button>',
        )

        query = {
            "view": "catalog",
            "bust": "90",
            "waist": "74",
            "hip": "100",
            "preference": "loose",
        }
        catalog_page = renderizar_pagina(query)
        cards = _catalog_page_data(query)
        first_id = re.search(
            r'data-catalog-id="([^"]+)"', cards["cards"]
        ).group(1)
        product = next(item for item in CATALOG_PRODUCTS if item.id == first_id)
        reference, _ = _reference_for_listing(product)
        profile = PerfilMedidas(busto=90, cintura=74, cadera=100)
        expected = CALCULATOR.calcular(reference, profile, "loose")

        self.assertIn('id="garment-catalog" data-garment-catalog', catalog_page)
        self.assertIn(
            f'data-catalog-fit-badge="{expected.diagnostico.etiqueta}"',
            cards["cards"],
        )
        self.assertIn('data-catalog-bust="90.0 cm"', cards["cards"])
        self.assertIn('data-measure-body="74.0 cm"', cards["cards"])

    def test_photo_step_offers_device_camera_and_image_picker(self):
        page = renderizar_pagina({})
        photo_step = page.split(
            'data-wizard-panel="1"', 1
        )[1].split('data-wizard-panel="2"', 1)[0]

        self.assertIn("data-camera-open>Tomar foto</button>", photo_step)
        self.assertIn("<span>Elegir foto</span>", photo_step)
        self.assertIn('data-camera-panel hidden', photo_step)
        self.assertIn(
            'id="matices-camera-video" class="matices-camera-preview" '
            'autoplay playsinline muted',
            photo_step,
        )
        self.assertIn('data-camera-capture>Capturar foto</button>', photo_step)
        self.assertIn('accept="image/*"', photo_step)
        self.assertIn(
            'class="matices-preview-remove" type="button" data-photo-remove',
            photo_step,
        )
        self.assertIn('aria-label="Eliminar imagen"', photo_step)
        self.assertIn('id="matices-remember" type="checkbox"', photo_step)
        app_script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("indexedDB.open(rememberedPhotoDatabase, 1)", app_script)
        self.assertIn("restoreRememberedPhoto();", app_script)
        self.assertIn("No se pudo recuperar la foto guardada.", app_script)
        self.assertIn("No se pudo borrar la foto guardada.", app_script)
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("aspect-ratio: 10 / 4;", styles)
        self.assertIn("object-fit: contain;", styles)

    def test_home_wizard_is_embedded_in_page_not_a_floating_dialog(self):
        page = renderizar_pagina({})

        self.assertIn(
            '<section id="style-wizard" class="style-wizard"',
            page,
        )
        self.assertNotIn('<dialog id="style-wizard"', page)
        self.assertNotIn("data-wizard-reopen", page)

    def test_fit_details_section_is_collapsible_and_closed_by_default(self):
        page = renderizar_pagina({})
        details_section = page.split(
            '<details class="variable-details">', 1
        )[1].split("</details>", 1)[0]

        self.assertIn("<summary", details_section)
        self.assertIn("Detrás de cada recomendación", details_section)
        summary, content = details_section.split("</summary>", 1)
        self.assertNotIn("14 detalles que cambian el calce", summary)
        self.assertIn("14 detalles que cambian el calce", content)
        self.assertIn('class="variable-grid"', details_section)
        self.assertNotIn("<details class=\"variable-details\" open>", page)

    def test_wizard_measurement_step_precedes_summary_step(self):
        page = renderizar_pagina(
            {"wizard_step": "3", "bust": "90", "waist": "74", "hip": "100"}
        )
        wizard = page.split('id="style-wizard"', 1)[1].split("</form>", 1)[0]
        measurement_step = wizard.split('data-wizard-panel="2"', 1)[1].split(
            'data-wizard-panel="3"', 1
        )[0]
        summary_step = wizard.split('data-wizard-panel="3"', 1)[1]

        self.assertIn('aria-valuemax="3"', page)
        self.assertNotIn('wizard-palette-title', wizard)
        self.assertNotIn('id="matices-result"', wizard)
        self.assertNotIn("Tu paleta recomendada", summary_step)
        self.assertNotIn("Paso 2 de 3", summary_step)
        self.assertIn("Medidas corporales", measurement_step)
        self.assertIn('name="waist"', measurement_step)
        self.assertIn("Paso 3 de 3", summary_step)
        self.assertIn('data-wizard-next="3">Ver resumen</button>', measurement_step)
        self.assertIn("Volver a la foto", measurement_step)
        self.assertIn("Volver a las medidas", summary_step)
        self.assertNotIn("Elige los colores que usarías", summary_step)
        self.assertNotIn('name="preferred_color"', summary_step)
        self.assertNotIn("Prendas más recomendadas", summary_step)
        self.assertNotIn('class="wizard-recommendations"', summary_step)
        self.assertNotIn('class="results-panel"', summary_step)
        self.assertNotIn('name="waist"', summary_step)
        self.assertNotIn('name="preference"', summary_step)
        self.assertNotIn('name="category"', summary_step)
        self.assertNotIn('name="brand"', summary_step)
        self.assertNotIn("¿Cómo te gusta el calce?", summary_step)
        self.assertNotIn("Estándar / cómodo", summary_step)
        self.assertNotIn(">Todas</button>", summary_step)
        self.assertNotIn(">Arriba</button>", summary_step)
        self.assertNotIn(">Abajo</button>", summary_step)
        self.assertNotIn("Tipo de prenda", summary_step)
        self.assertNotIn("Marca", summary_step)
        self.assertIn('data-palette-summary', summary_step)
        self.assertIn('data-size-summary', summary_step)
        self.assertIn("2 · Medidas", page)
        self.assertIn("3 · Resumen", page)
        self.assertNotIn("Prendas a explorar", summary_step)
        self.assertIn("Cerrar asistente e ir al catálogo", page)
        self.assertIn(
            '<section class="results-panel wizard-page-results" '
            'aria-label="Resultados de calce">',
            page,
        )
        self.assertIn("Marcas con mejor coincidencia", page)
        self.assertIn(
            '<section class="results-panel wizard-page-results" '
            'aria-label="Resultados de calce" hidden>',
            renderizar_pagina({}),
        )

    def test_wizard_step_three_query_opens_summary_after_measurements(self):
        page = renderizar_pagina({"wizard_step": "3"})

        self.assertIn('<input type="hidden" name="wizard_step" value="3">', page)
        self.assertIn('data-wizard-panel="2"', page)
        self.assertIn('data-wizard-panel="3"', page)

    def test_supabase_account_controls_and_row_security_schema_are_present(self):
        page = renderizar_pagina({})
        schema = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")

        sign_in_position = page.index('data-open-account="sign-in"')
        sign_up_position = page.index('data-open-account="sign-up"')
        home_position = page.index('id="home-link"')
        self.assertLess(sign_in_position, sign_up_position)
        self.assertLess(sign_up_position, home_position)
        self.assertIn(
            '<meta name="supabase-url" '
            'content="https://twhszjxhmimqlzthlbgy.supabase.co">',
            page,
        )
        self.assertIn('id="supabase-email" type="email"', page)
        self.assertIn('data-supabase-sign-in', page)
        self.assertIn('data-supabase-sign-up', page)
        self.assertIn('data-auth-mode="sign-in"', page)
        self.assertIn('data-auth-mode="sign-up"', page)
        self.assertIn('id="supabase-password-confirm"', page)
        self.assertIn('minlength="8"', page)
        self.assertIn(
            '<input id="supabase-remember-session" type="checkbox">',
            page,
        )
        self.assertIn(">Recuérdame</span>", page)
        self.assertIn("emailRedirectTo", (ROOT / "web" / "app.js").read_text(encoding="utf-8"))
        self.assertIn('data-open-account="sign-in"', page)
        self.assertIn('data-open-account="sign-up"', page)
        self.assertIn('<nav class="page-tabs" aria-label="Secciones principales">', page)
        self.assertNotIn('id="account-link"', page)
        self.assertIn('data-open-account="sign-in"', page.split("</nav>", 1)[0])
        self.assertIn('data-open-account="sign-up"', page.split("</nav>", 1)[0])
        self.assertIn('class="profile-menu" data-profile-menu hidden>', page)
        profile_menu = page.split('data-profile-menu hidden>', 1)[1].split('</details>', 1)[0]
        self.assertNotIn('data-profile-auth=', profile_menu)
        self.assertNotIn('>Iniciar sesión</a>', profile_menu)
        self.assertNotIn('>Crear cuenta</a>', profile_menu)
        self.assertIn('href="/?wizard_step=2" data-profile-edit hidden>Modificar perfil</a>', page)
        self.assertIn('data-supabase-sign-out hidden>Cerrar sesión</button>', page)
        self.assertIn('data-profile-email', page)
        app_script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("profileMenu.hidden = !user", app_script)
        self.assertIn("profileEditLink.hidden = !user", app_script)
        self.assertIn("signOutButton.hidden = !user", app_script)
        self.assertIn("supabaseClient.auth.signOut()", app_script)
        self.assertIn("await handleAuthSession(null)", app_script)
        self.assertIn("storage: authStorage", app_script)
        self.assertIn("window.localStorage", app_script)
        self.assertIn("window.sessionStorage", app_script)
        self.assertIn("rememberSessionRow.hidden = creatingAccount", app_script)
        self.assertIn("new URLSearchParams(window.location.search).get(\"auth_mode\")", app_script)
        measured_page = renderizar_pagina(
            {"bust": "90", "waist": "74", "hip": "100"}
        )
        self.assertIn(
            'href="/?view=account&amp;wizard_step=2&amp;auth_mode=sign-in"',
            measured_page,
        )
        self.assertIn(
            'href="/?view=account&amp;wizard_step=2&amp;auth_mode=sign-up"',
            measured_page,
        )
        account_page = renderizar_pagina({"view": "account", "auth_mode": "sign-up"})
        self.assertIn(
            'data-open-account="sign-up" aria-current="page">Crear cuenta</a>',
            account_page,
        )
        self.assertNotIn('data-open-account="sign-in" aria-current="page"', account_page)
        self.assertIn('data-account-panel', account_page)
        self.assertIn('auth_mode=sign-up', account_page)
        self.assertIn('data-account-back', account_page)
        self.assertIn("Recordar medidas", page)
        self.assertIn("alter table public.user_profiles enable row level security", schema)
        self.assertIn("(select auth.uid()) = user_id", schema)
        self.assertIn("remember_measurements boolean not null default false", schema)
        self.assertIn("remember_photo boolean not null default false", schema)
        self.assertIn("photo_path text", schema)
        self.assertIn("insert into storage.buckets", schema)
        self.assertIn("bucket_id = 'user-profile-photos'", schema)
        self.assertIn("(storage.foldername(name))[1] = (select auth.uid())::text", schema)
        self.assertIn(
            "rememberCheckbox?.checked === true || rememberPhoto",
            app_script,
        )
        self.assertIn("pendingPhotoRemember", app_script)
        self.assertIn("data.remember_photo === true", app_script)
        self.assertIn("upload(profilePhotoPath(user)", app_script)
        self.assertIn(".download(rememberedPhotoPath)", app_script)
        self.assertIn('window.addEventListener("matices:restore-photo"', app_script)
        self.assertNotIn("service_role", schema)

    def test_private_hosting_requires_basic_authentication(self):
        password = "test-private-password"
        credentials = base64.b64encode(
            f"medidas:{password}".encode("utf-8")
        ).decode("ascii")
        valid_header = f"Basic {credentials}"

        self.assertTrue(_is_valid_access_authorization(valid_header, password))
        self.assertFalse(_is_valid_access_authorization("", password))
        self.assertFalse(_is_valid_access_authorization(valid_header, "another-password"))
        self.assertFalse(_is_valid_access_authorization("Basic invalid", password))
        self.assertFalse(_is_valid_access_authorization("Bearer token", password))

        render_config = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("plan: free", render_config)
        self.assertIn("healthCheckPath: /healthz", render_config)
        self.assertIn("key: APP_ACCESS_PASSWORD", render_config)

    def test_private_hosting_http_gate_and_health_check(self):
        password = "test-private-password"
        credentials = base64.b64encode(
            f"medidas:{password}".encode("utf-8")
        ).decode("ascii")
        server = ThreadingHTTPServer(("127.0.0.1", 0), MedidasRequestHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            with patch.dict(
                os.environ,
                {"RENDER": "true", "APP_ACCESS_PASSWORD": password},
            ):
                connection = HTTPConnection("127.0.0.1", server.server_port)
                connection.request("GET", "/")
                response = connection.getresponse()
                self.assertEqual(response.status, 401)
                self.assertIn("Basic", response.getheader("WWW-Authenticate"))
                response.read()
                connection.close()

                connection = HTTPConnection("127.0.0.1", server.server_port)
                connection.request(
                    "GET",
                    "/",
                    headers={"Authorization": f"Basic {credentials}"},
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                connection.close()

                connection = HTTPConnection("127.0.0.1", server.server_port)
                connection.request("GET", "/healthz")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"ok")
                connection.close()

            with patch.dict(os.environ, {"RENDER": "true"}, clear=True):
                connection = HTTPConnection("127.0.0.1", server.server_port)
                connection.request("GET", "/")
                response = connection.getresponse()
                self.assertEqual(response.status, 503)
                response.read()
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join()

    def test_local_env_file_loads_values_without_overriding_existing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "# local settings\n"
                "export SUPABASE_URL='https://local.example'\n"
                "SUPABASE_PUBLISHABLE_KEY=\"public-key\"\n"
                "IGNORED_LINE\n",
                encoding="utf-8",
            )
            environment = {"SUPABASE_URL": "https://from-shell.example"}

            _load_environment_file(env_path, environment)
            _load_environment_file(Path(directory) / "missing.env", environment)

        self.assertEqual(environment["SUPABASE_URL"], "https://from-shell.example")
        self.assertEqual(environment["SUPABASE_PUBLISHABLE_KEY"], "public-key")
        self.assertNotIn("IGNORED_LINE", environment)

    def test_catalog_fit_badge_requests_measurements_when_missing_or_partial(self):
        product = next(item for item in WOMENSWEAR_DATA["products"] if item["store"] == "Paris")
        no_measurements = _catalog_page_data({"search": product["title"]})
        partial_measurements = _catalog_page_data(
            {"search": product["title"], "waist": "70"}
        )

        self.assertIn(
            'data-catalog-fit-badge="Ingresa tus medidas"',
            no_measurements["cards"],
        )
        self.assertIn(
            'data-catalog-fit-badge="Completa cintura y cadera"',
            partial_measurements["cards"],
        )

    def test_selected_catalog_cards_expose_published_size_and_body_measurements(self):
        product = next(item for item in WOMENSWEAR_DATA["products"] if item["store"] == "Paris")
        search_result = _catalog_page_data({"search": product["title"]})

        self.assertIn('data-catalog-size="No indicada"', search_result["cards"])
        self.assertIn('data-catalog-bust="Ingresa medida"', search_result["cards"])
        self.assertIn('data-comparison-measure="Cintura"', search_result["cards"])
        self.assertIn('data-measure-garment=', search_result["cards"])
        self.assertIn('data-measure-body=', search_result["cards"])
        self.assertIn('data-measure-ease=', search_result["cards"])
        self.assertNotIn(
            "Ingresa tus medidas para comparar tu cuerpo con las medidas de esta prenda.",
            search_result["cards"],
        )
        self.assertNotIn("Referencia usada:", search_result["cards"])

    def test_catalog_and_home_are_separate_linked_views(self):
        home_page = renderizar_pagina({})
        catalog_page = renderizar_pagina({"view": "catalog"})

        self.assertIn('action="/"', home_page)
        self.assertIn("Abrir catálogo completo", home_page)
        self.assertIn('href="/?view=catalog&amp;preference=regular"', home_page)
        self.assertIn('<nav class="page-tabs" aria-label="Secciones principales">', home_page)
        self.assertIn('href="/" aria-current="page">Inicio</a>', home_page)
        self.assertIn('href="/?view=catalog" aria-current="page">Catálogo</a>', catalog_page)
        self.assertNotIn('role="tablist"', home_page)
        self.assertNotIn('data-page-tab-link', home_page)
        self.assertIn('data-page-panel="catalog"', home_page)
        self.assertIn('data-page-panel="home"', catalog_page)
        self.assertIn('data-page-panel="catalog" hidden', home_page)
        self.assertIn('data-page-panel="home" hidden', catalog_page)
        self.assertIn('data-page-panel="catalog"', catalog_page)
        self.assertIn('id="garment-catalog" data-garment-catalog', catalog_page)
        self.assertIn('id="home-panel"', catalog_page)
        self.assertIn("Toma o selecciona una foto", catalog_page)
        self.assertEqual(catalog_page.count('data-startup-dialog'), 0)
        self.assertEqual(home_page.count('data-startup-dialog'), 2)
        self.assertNotIn("Tu guía de calce personal", catalog_page)
        self.assertNotIn("fashion-modish-sample.png", catalog_page)
        self.assertNotIn("welcome-font-sample", catalog_page)
        self.assertNotIn("Encuentra prendas que podrían quedarte bien.", catalog_page)
        self.assertNotIn("RECOMENDACIÓN ORIENTATIVA", catalog_page)
        self.assertNotIn("Tu cuerpo, tus preferencias.", catalog_page)
        self.assertIn(
            '<p class="welcome-message" id="preferences-title">Tu cuerpo, tus preferencias.</p>',
            home_page,
        )
        self.assertLess(
            home_page.index("Encuentra prendas que podrían quedarte bien."),
            home_page.index("Tu cuerpo, tus preferencias."),
        )
        self.assertNotIn('data-dismiss-dialog', catalog_page)
        self.assertNotIn(
            "Comparamos cintura y cadera con referencias de medidas disponibles",
            catalog_page,
        )

    def test_page_hides_best_options_heading_until_a_filter_is_selected(self):
        page = renderizar_pagina({})
        home_panel = page.split('id="catalog-panel"', 1)[0]

        self.assertNotIn("Tus mejores opciones", home_panel)
        self.assertNotIn('data-carousel', home_panel)
        self.assertNotIn('data-carousel-card', home_panel)
        self.assertNotIn("Ingresa tus medidas", home_panel)
        self.assertIn(
            '<section class="wizard-step" data-wizard-panel="2" '
            'aria-labelledby="wizard-measures-title" hidden>',
            home_panel,
        )
        self.assertNotIn("Ver recomendaciones", home_panel)
        self.assertNotIn("Coloca tus medidas", page)
        self.assertIn("Abrir catálogo completo", page)
        self.assertNotIn('name="brand"', page)

        filtered_page = renderizar_pagina({"category": "Blusa"})
        self.assertIn("<h2>Tus mejores opciones</h2>", filtered_page)
        self.assertIn('data-carousel', filtered_page)
        self.assertIn('class="results-content" aria-live="polite"', filtered_page)
        self.assertNotIn("Coloca tus medidas", filtered_page)

    def test_product_carousel_waits_for_measurements_or_garment_filters(self):
        preference_page = renderizar_pagina({"preference": "loose"})
        self.assertNotIn('data-carousel', preference_page)
        self.assertNotIn("alternative-recommendations", preference_page)

        measurement_page = renderizar_pagina(
            {"bust": "85", "waist": "67", "hip": "93"}
        )
        self.assertIn('data-carousel', measurement_page)
        self.assertIn("alternative-recommendations", measurement_page)

        brand_page = renderizar_pagina({"brand": "Zara"})
        self.assertIn('data-carousel', brand_page)

    def test_home_includes_tricot_and_paris_listing_recommendations(self):
        page = renderizar_pagina(
            {"bust": "85", "waist": "67", "hip": "93"}
        )

        self.assertIn(
            '<h2 id="store-listing-title">Prendas de tiendas que podrían quedarte bien</h2>',
            page,
        )
        store_section = page.split(
            'id="store-listing-recommendations"', 1
        )[1].split("</section>", 1)[0]
        self.assertIn("Paris", store_section)
        self.assertIn("Tricot", store_section)
        self.assertIn('class="product-image"', store_section)
        self.assertIn('class="catalog-buy-link"', store_section)
        self.assertIn("Talla publicada:", store_section)
        self.assertIn("Referencia estimada:", store_section)
        self.assertIn("Ver medidas comparadas", store_section)
        self.assertLess(
            page.index('id="store-listing-recommendations"'),
            page.index('class="size-chart"'),
        )

    def test_home_store_recommendations_respect_selected_garment_category(self):
        page = renderizar_pagina(
            {"bust": "85", "waist": "67", "hip": "93", "category": "Jeans"}
        )
        store_section = page.split(
            'id="store-listing-recommendations"', 1
        )[1].split("</section>", 1)[0]

        self.assertIn("Jeans", store_section)
        self.assertNotIn("Vestido", store_section)

    def test_wizard_removes_fit_and_garment_filter_controls(self):
        expected = (
            ("__all__", "38 referencias"),
            ("__top__", "27 referencias"),
            ("__bottom__", "11 referencias"),
        )
        for category_filter, count in expected:
            with self.subTest(category_filter=category_filter):
                page = renderizar_pagina(
                    {"brand": "", "category_group": category_filter}
                )

                self.assertIn(f'<span class="count">{count}</span>', page)
                wizard = page.split('id="style-wizard"', 1)[1].split("</form>", 1)[0]
                summary_step = wizard.split('data-wizard-panel="3"', 1)[1]
                self.assertNotIn('data-category-filter=', summary_step)
                self.assertNotIn('name="preference"', summary_step)
                self.assertNotIn('name="category"', summary_step)
                self.assertNotIn('name="brand"', summary_step)

    def test_category_tabs_limit_alternative_recommendations_to_selected_group(self):
        page = renderizar_pagina(
            {
                "brand": "Zara",
                "category_group": "__top__",
                "bust": "85",
                "waist": "67",
                "hip": "93",
            }
        )
        alternative_section = page.split(
            'id="alternative-recommendations"', 1
        )[1].split("</section>", 1)[0]

        if alternative_section:
            self.assertNotIn("Jeans · Fit", alternative_section)
            self.assertNotIn("Pantalon · Fit", alternative_section)

    def test_alternative_fit_carousel_precedes_size_table_and_excludes_main_filter(self):
        page = renderizar_pagina(
            {
                "bust": "85",
                "waist": "67",
                "hip": "93",
                "brand": "Zara",
                "category": "Blusa",
            }
        )

        self.assertIn(
            '<h2 id="alternative-title">Otras opciones que podrían quedarte bien</h2>',
            page,
        )
        self.assertIn("Holgura al límite", page)
        self.assertLess(
            page.index('id="alternative-recommendations"'),
            page.index('class="size-chart"'),
        )
        alternative_section = page.split(
            'id="alternative-recommendations"', 1
        )[1].split("</section>", 1)[0]
        cards = alternative_section.split('<article class="product-card carousel-card"')
        self.assertFalse(
            any(
                "Zara · Zara Woman" in card and "Blusa · Fit" in card
                for card in cards
            )
        )
        self.assertIn("H&amp;M", alternative_section)
        self.assertIn("data-alternative-carousel", page)
        alternative_cards = re.findall(
            r'class="recommend-badge verdict [^"]+">(.*?)</span>',
            alternative_section,
        )
        self.assertTrue(alternative_cards)
        self.assertTrue(
            all(
                badge in {
                    "Podría quedarte bien",
                    "Ajuste al límite",
                    "Holgura al límite",
                }
                for badge in alternative_cards
            )
        )

    def test_fit_detail_boxes_are_ordered_by_declared_importance(self):
        page = renderizar_pagina({})
        impacts = re.findall(r'class="impact ([^"]+)"', page)

        self.assertEqual(
            impacts,
            ["muy-alto"] * 4 + ["alto"] * 6 + ["medio"] * 4,
        )

    def test_brand_and_category_summary_reports_all_closest_ties(self):
        profile = PerfilMedidas(busto=85, cintura=67, cadera=93)
        preference = "regular"
        matches = tuple(
            (product, result)
            for product in CATALOG.prendas
            if (
                (result := CalculadoraCalce().calcular(product, profile, preference))
            ).diagnostico.etiqueta != "Revisión parcial"
            and isfinite(result.puntuacion)
        )
        minimum_score = min(result.puntuacion for _, result in matches)
        closest_matches = tuple(
            (product, result)
            for product, result in matches
            if abs(result.puntuacion - minimum_score) < 1e-9
        )
        closest_brands = tuple(
            dict.fromkeys(product.marca for product, _ in closest_matches)
        )
        closest_categories = tuple(
            dict.fromkeys(product.categoria for product, _ in closest_matches)
        )
        page = renderizar_pagina(
            {"bust": "85", "waist": "67", "hip": "93"}
        )

        self.assertIn(
            '<div><span>Marcas con mejor coincidencia</span><strong>'
            f'{", ".join(escape(brand) for brand in closest_brands)}</strong>',
            page,
        )
        self.assertIn(
            '<div><span>Tipo de ropa recomendado</span><strong>'
            f'{", ".join(escape(category) for category in closest_categories)}</strong></div>',
            page,
        )
        self.assertIn("Hay un empate entre marcas", page)
        self.assertIn("estos datos no permiten distinguir", page.lower())

    def test_vestua_image_references_cover_each_brand(self):
        catalog = CatalogoPrendas(self.repository.cargar_prendas())
        with VESTUA_IMAGES.open(encoding="utf-8") as image_file:
            image_references = json.load(image_file)

        self.assertEqual(set(image_references), set(catalog.marcas()))
        for brand, category_references in image_references.items():
            self.assertTrue(category_references)
            for category, reference in category_references.items():
                self.assertIn(category, catalog.categorias())
                self.assertIn(brand.lower(), reference["product_title"].lower())
                self.assertTrue(reference["product_size"])
                self.assertTrue(reference["image_url"].startswith("https://"))
                self.assertTrue(
                    reference["product_url"].startswith(
                        "https://www.vestua.cl/store/product/"
                    )
                )

    def test_product_images_match_the_selected_brand_and_category(self):
        with VESTUA_IMAGES.open(encoding="utf-8") as image_file:
            image_references = json.load(image_file)

        for brand, category in (("Levi's", "Jeans"), ("Nike", "Top Deportivo")):
            with self.subTest(brand=brand, category=category):
                page = renderizar_pagina({"brand": brand, "category": category})
                reference = image_references[brand][category]
                self.assertIn(
                    f'aria-label="Ver referencia de {escape(brand, quote=True)} '
                    f'{escape(category, quote=True)} en Vestua"',
                    page,
                )
                self.assertIn(
                    f'href="{reference["product_url"]}"',
                    page,
                )
                self.assertIn(
                    f'alt="Imagen referencial de '
                    f'{escape(reference["product_title"], quote=True)} en Vestua"',
                    page,
                )
                self.assertIn(
                    f'<span class="vestua-size">Talla Vestua: '
                    f'<strong>{escape(reference["product_size"])}</strong></span>',
                    page,
                )

    def test_missing_brand_category_product_does_not_use_another_brand_photo(self):
        page = renderizar_pagina(
            {
                "brand": "Nike",
                "category": "Jeans",
                "bust": "85",
                "waist": "67",
                "hip": "93",
            }
        )

        self.assertIn("No encontramos referencias con esos filtros.", page)
        self.assertNotIn("Referencia Jeans · Nike", page)
        self.assertNotIn("Nike · Nike", page)
        self.assertNotIn("data-carousel-card", page.split("data-alternative-carousel", 1)[0])
        self.assertNotIn("class=\"product-image-placeholder\"", page)

    def test_wizard_omits_brand_filters_without_changing_recommendation_details(self):
        page = renderizar_pagina(
            {"brand": "Zara", "category": "Blusa", "bust": "88", "waist": "70"}
        )
        wizard = page.split('id="style-wizard"', 1)[1].split("</form>", 1)[0]
        summary_step = wizard.split('data-wizard-panel="3"', 1)[1]

        self.assertNotIn('name="brand"', summary_step)
        self.assertNotIn('name="category"', summary_step)
        self.assertNotIn("Molde europeo / Inditex", summary_step)
        self.assertIn("Molde europeo / Inditex", page)
        self.assertNotIn('value="Europeo"', page)

    def test_fit_explanation_says_when_measurements_are_in_range(self):
        page = renderizar_pagina(
            {"brand": "Zara", "category": "Blusa", "waist": "67", "hip": "93"}
        )

        self.assertIn("dentro del rango orientativo de 2 a 8 cm", page)
        self.assertIn("tu cuerpo 67.0 cm", page)
        self.assertIn("prenda 70.0 cm", page)

    def test_profile_parses_optional_measurements(self):
        profile = PerfilMedidas.desde_formulario(
            {"bust": "92,5", "waist": "", "hip": "nan", "length": "65"}
        )

        self.assertEqual(profile.busto, 92.5)
        self.assertIsNone(profile.cintura)
        self.assertIsNone(profile.cadera)
        self.assertEqual(profile.largo, 65)

    def test_standard_size_chart_is_loaded_and_recommends_matching_size(self):
        sizes = RepositorioTallasEstandar(STANDARD_SIZES).cargar()
        recommended, exact_match = recomendar_tallas(
            PerfilMedidas(busto=87, cintura=68, cadera=95), sizes
        )

        self.assertEqual(
            [
                (
                    size.etiqueta,
                    size.europea,
                    size.estadounidense,
                    size.busto,
                    size.cintura,
                    size.cadera,
                )
                for size in sizes
            ],
            [
                ("XXS", "30/32", "00/0", "76-82", "54-62", "84-88"),
                ("XS", "34", "2/4", "82-86", "62-66", "88-92"),
                ("S", "36/38", "4/6", "86-90", "66-70", "92-98"),
                ("M", "38/40", "8/10", "90-96", "70-76", "98-102"),
                ("L", "42/44", "12/14", "96-102", "76-82", "102-108"),
                ("XL", "46/48", "16/18", "102-110", "82-90", "108-116"),
                ("XXL", "50/52", "20/22", "110-118", "90-98", "116-124"),
            ],
        )
        self.assertEqual([size.etiqueta for size in recommended], ["S"])
        self.assertTrue(exact_match)

    def test_standard_size_chart_reports_closest_size_when_measures_conflict(self):
        sizes = RepositorioTallasEstandar(STANDARD_SIZES).cargar()
        recommended, exact_match = recomendar_tallas(
            PerfilMedidas(busto=80, cintura=98, cadera=124), sizes
        )

        self.assertEqual([size.etiqueta for size in recommended], ["XXL"])
        self.assertFalse(exact_match)
        page = renderizar_pagina({"bust": "80", "waist": "99", "hip": "124"})
        self.assertIn("Son las tallas más cercanas.", page)
        self.assertNotIn("tus medidas no coinciden todas con un mismo rango", page)

    def test_bust_alone_selects_size_and_is_shown_in_the_standard_table(self):
        sizes = RepositorioTallasEstandar(STANDARD_SIZES).cargar()
        recommended, exact_match = recomendar_tallas(
            PerfilMedidas(busto=84), sizes
        )
        page = renderizar_pagina({"bust": "84"})

        self.assertEqual([size.etiqueta for size in recommended], ["XS"])
        self.assertTrue(exact_match)
        self.assertIn(
            '<tr class="recommended-size"><th scope="row">XS</th>', page
        )
        self.assertIn("<td>82-86</td>", page)

    def test_page_renders_recommendations_measurement_guidance_and_size_chart(self):
        page = renderizar_pagina(
            {"bust": "85", "waist": "67", "hip": "93", "brand": "Zara"}
        )

        self.assertIn("Marcas con mejor coincidencia", page)
        self.assertIn("Tipo de ropa recomendado", page)
        self.assertIn("Talla(s) según tabla estándar", page)
        self.assertIn(
            "La tabla estándar usa busto/pecho, cintura y cadera. El cálculo de "
            "calce de las prendas considera cintura y cadera, ya que las fichas "
            "importadas de Vestua no publican medidas físicas exactas.</span>",
            page,
        )
        self.assertIn('aria-describedby="recommendations-help"', page)
        self.assertIn('data-size-bust-min="76.0"', page)
        self.assertIn('data-size-waist-max="62.0"', page)
        self.assertIn('data-size-hip-max="88.0"', page)
        self.assertIn("Tallas según tabla estándar", page)
        self.assertIn('data-palette-summary-colors', page)
        self.assertNotIn(
            '<p class="sub">Filtra por marca o tipo de prenda para comparar',
            page,
        )
        self.assertIn("<strong>S (EU 36/38) (EE.UU. 4/6)</strong>", page)
        self.assertNotIn("Tabla Estándar de Tallas", page)
        self.assertIn('<section class="size-chart"', page)
        self.assertIn("<th scope=\"col\">Talla alfa</th>", page)
        self.assertNotIn("Medidas corporales en centímetros", page)
        self.assertNotIn("El archivo adjunto no contiene tablas oficiales por marca", page)
        self.assertNotIn("Esta referencia estándar no garantiza equivalencia con una marca", page)
        self.assertIn("Talla EU", page)
        self.assertIn('<th scope="col">Talla EE.UU.</th>', page)
        for size, us_size in (
            ("XXS", "00/0"),
            ("XS", "2/4"),
            ("S", "4/6"),
            ("M", "8/10"),
            ("L", "12/14"),
            ("XL", "16/18"),
            ("XXL", "20/22"),
        ):
            self.assertIn(
                f'<th scope="row">{size}</th><td>',
                page,
            )
            row_start = page.index(f'<th scope="row">{size}</th>')
            row_end = page.index("</tr>", row_start)
            self.assertIn(f"<td>{us_size}</td>", page[row_start:row_end])
        self.assertIn("Busto / pecho (cm)", page)
        self.assertIn("Cintura (cm)", page)
        self.assertIn("Cadera (cm)", page)
        self.assertIn('id="measurement-bust"', page)
        self.assertIn("parte más amplia del pecho", page)
        self.assertIn('href="/?view=catalog&amp;preference=regular&amp;bust=85&amp;waist=67&amp;hip=93"', page)
        self.assertIn(
            '<input id="remember-me" type="checkbox"> Recordar',
            page,
        )
        self.assertIn('id="remember-status"', page)
        self.assertIn(
            "Mide alrededor de la parte más estrecha de la cintura "
            "(usualmente justo por encima del ombligo)",
            page,
        )
        self.assertIn(
            "Junta los pies y mide alrededor de la parte más ancha de las "
            "caderas y glúteos.",
            page,
        )
        self.assertEqual(page.count('class="measurement-help-trigger"'), 4)
        self.assertEqual(page.count('class="measurement-tooltip"'), 4)
        self.assertNotIn('class="measurement-help">', page)
        for field in ("bust", "waist", "hip"):
            self.assertIn(f'id="measurement-{field}"', page)
        self.assertNotIn('id="measurement-length"', page)
        self.assertLess(
            page.index('class="size-chart"'),
            page.index("14 detalles que cambian el calce"),
        )


if __name__ == "__main__":
    unittest.main()
