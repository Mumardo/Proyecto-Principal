import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

from web.servidor import MedidasRequestHandler


class DeploymentTests(unittest.TestCase):
    def test_health_check_returns_ok(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), MedidasRequestHandler)
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join)
        self.addCleanup(server.shutdown)

        with urlopen(f"http://127.0.0.1:{server.server_port}/healthz") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"ok")

if __name__ == "__main__":
    unittest.main()
