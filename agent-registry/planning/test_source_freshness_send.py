import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from source_freshness import SourceFreshnessError, compare
from source_freshness_send import send
from source_freshness_otlp import EVENT_NAME
from test_source_freshness import snapshot


class Receiver(BaseHTTPRequestHandler):
    response_body = b"{}"

    def do_POST(self):
        self.server.request_path = self.path
        self.server.content_type = self.headers.get("Content-Type")
        self.server.body = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.response_body)

    def log_message(self, *args):
        pass


class SourceFreshnessSendTests(unittest.TestCase):
    def setUp(self):
        self.receiver = HTTPServer(("127.0.0.1", 0), Receiver)
        self.thread = threading.Thread(target=self.receiver.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.receiver.shutdown()
        self.thread.join()
        self.receiver.server_close()

    def test_sends_only_bounded_event_to_loopback_otlp(self):
        report = compare(snapshot())
        send(report, self.receiver.server_port)
        self.assertEqual(self.receiver.request_path, "/v1/logs")
        self.assertEqual(self.receiver.content_type, "application/json")
        payload = json.loads(self.receiver.body)
        record = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
        self.assertEqual(record["eventName"], EVENT_NAME)
        self.assertNotIn("IXOR_Benchmark", self.receiver.body.decode())
        self.assertNotIn("C:\\ChatGPT", self.receiver.body.decode())
        self.assertNotIn("drive:test-canonical-identity", self.receiver.body.decode())

    def test_refuses_promotion_and_partial_success(self):
        report = compare(snapshot())
        report["mechanical_acceptance_granted"] = True
        with self.assertRaises(SourceFreshnessError):
            send(report, self.receiver.server_port)
        self.assertFalse(hasattr(self.receiver, "body"))
        Receiver.response_body = b'{"partialSuccess":{"rejectedLogRecords":1}}'
        try:
            with self.assertRaisesRegex(ValueError, "partial success"):
                send(compare(snapshot()), self.receiver.server_port)
        finally:
            Receiver.response_body = b"{}"

    def test_invalid_port_fails_before_network(self):
        with self.assertRaisesRegex(ValueError, "port"):
            send(compare(snapshot()), 0)


if __name__ == "__main__":
    unittest.main()
