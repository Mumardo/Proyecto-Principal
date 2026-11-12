import base64
import json
import threading
import unittest
from http.client import IncompleteRead
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from unittest.mock import patch

from web.servidor import (
    CATALOG_PRODUCTS,
    MedidasRequestHandler,
    _virtual_try_on_category,
)


class _FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _IncompleteReadResponse(_FakeResponse):
    def read(self, limit=-1):
        raise IncompleteRead(b"partial response", 1024)


class DeploymentTests(unittest.TestCase):
    def start_server(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), MedidasRequestHandler)
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join)
        self.addCleanup(server.shutdown)
        return server

    def test_health_check_returns_ok(self):
        server = self.start_server()

        with urlopen(f"http://127.0.0.1:{server.server_port}/healthz") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"ok")

    def test_virtual_try_on_product_search_returns_catalog_matches(self):
        server = self.start_server()
        product = CATALOG_PRODUCTS[0]
        url = (
            f"http://127.0.0.1:{server.server_port}/api/vton-products"
            f"?search={quote(product.titulo)}"
        )

        with urlopen(url) as response:
            data = json.loads(response.read())

        self.assertTrue(
            any(item["product_url"] == product.url for item in data["products"])
        )

    def test_virtual_try_on_rejects_anonymous_requests(self):
        server = self.start_server()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/try-on",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with self.assertRaises(HTTPError) as error:
            urlopen(request)

        self.assertEqual(error.exception.code, 401)

    def test_virtual_try_on_forwards_catalog_images_to_modal(self):
        server = self.start_server()
        product = CATALOG_PRODUCTS[0]
        person_image = b"person image"
        garment_image = b"garment image"
        result_image = base64.b64encode(b"result image").decode("ascii")
        modal_result = json.dumps(
            {
                "status": "simulation",
                "detail": "Inferencia pendiente",
                "result_image_base64": result_image,
            }
        ).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/try-on",
            data=json.dumps(
                {
                    "person_image_base64": base64.b64encode(person_image).decode("ascii"),
                    "product_url": product.url,
                }
            ).encode("utf-8"),
            headers={
                "Authorization": "Bearer supabase-access-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with patch("web.servidor.SUPABASE_URL", "https://supabase.example"), \
                patch("web.servidor.SUPABASE_PUBLISHABLE_KEY", "publishable-key"), \
                patch("web.servidor.VTON_API_URL", "https://modal.example"), \
                patch("web.servidor.VTON_API_TOKEN", "modal-secret"), \
                patch(
                    "web.servidor.urlopen",
                    side_effect=[
                        _FakeResponse(b'{"id":"user-123"}'),
                        _FakeResponse(garment_image),
                        _FakeResponse(modal_result),
                    ],
                ) as modal_requests:
            with urlopen(request) as response:
                data = json.loads(response.read())

        self.assertEqual(data["status"], "simulation")
        self.assertEqual(data["result_image_base64"], result_image)
        self.assertEqual(modal_requests.call_count, 3)
        modal_request = modal_requests.call_args_list[2][0][0]
        forwarded = json.loads(modal_request.data)
        self.assertEqual(
            base64.b64decode(forwarded["person_image_base64"]), person_image
        )
        self.assertEqual(
            base64.b64decode(forwarded["garment_image_base64"]), garment_image
        )
        self.assertEqual(forwarded["category"], _virtual_try_on_category(product))
        self.assertEqual(
            dict((key.lower(), value) for key, value in modal_request.header_items())[
                "authorization"
            ],
            "Bearer modal-secret",
        )

    def test_virtual_try_on_returns_json_when_modal_response_is_incomplete(self):
        server = self.start_server()
        product = CATALOG_PRODUCTS[0]
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/try-on",
            data=json.dumps(
                {
                    "person_image_base64": base64.b64encode(b"person").decode("ascii"),
                    "product_url": product.url,
                }
            ).encode("utf-8"),
            headers={
                "Authorization": "Bearer supabase-access-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with patch("web.servidor.SUPABASE_URL", "https://supabase.example"), \
                patch("web.servidor.SUPABASE_PUBLISHABLE_KEY", "publishable-key"), \
                patch("web.servidor.VTON_API_URL", "https://modal.example"), \
                patch("web.servidor.VTON_API_TOKEN", "modal-secret"), \
                patch(
                    "web.servidor.urlopen",
                    side_effect=[
                        _FakeResponse(b'{"id":"user-123"}'),
                        _FakeResponse(b"garment image"),
                        _IncompleteReadResponse(b""),
                    ],
                ):
            with self.assertRaises(HTTPError) as error:
                urlopen(request)

        self.assertEqual(error.exception.code, 502)
        self.assertEqual(
            error.exception.headers.get_content_type(),
            "application/json",
        )
        self.assertEqual(
            json.loads(error.exception.read())["error"],
            "No se pudo conectar con Modal.",
        )


if __name__ == "__main__":
    unittest.main()
