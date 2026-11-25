import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class AlertWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/alerts":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            self.send_error(400, "Invalid webhook payload")
            return

        status = payload["status"]
        names = [alert["labels"]["alertname"] for alert in payload["alerts"]]
        print(f"{status}: {', '.join(names)}", flush=True)

        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), AlertWebhookHandler).serve_forever()