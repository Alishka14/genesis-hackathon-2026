"""Read-only, local dashboard for synthetic LedgerGym development reports.

Never serves private truth, provenance, pair indexes, raw evaluator feedback
or arbitrary filesystem paths. Not a production web server or security boundary.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit, parse_qs

from .episode_io import load_public_episode


WEB = Path(__file__).resolve().parent / "dashboard_static"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
TABLES = {"ledger", "invoices", "payments", "fx"}
SPLITS = {"train", "dev"}
KINDS = {"synthetic_company_development", "synthetic_company_development_with_settlements"}


def _dataset(root: Path):
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("dataset must be a directory")
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "evaluation" / "summary.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict) or index.get("kind") not in KINDS:
        raise ValueError("expected a supported synthetic company dataset")
    if not isinstance(summary, dict) or summary.get("kind") != index["kind"]:
        raise ValueError("dataset summary mismatch")
    episodes = {}
    for split in ("train", "dev"):
        values = index.get(split)
        if not isinstance(values, list) or len(values) != 10:
            raise ValueError("expected 10 episodes per split")
        episodes[split] = {}
        for entry in values:
            if not isinstance(entry, dict):
                raise ValueError("invalid dataset index")
            rel = entry.get("path")
            if not isinstance(rel, str) or not re.fullmatch(rf"{split}/episode-[0-9]{{2}}", rel):
                raise ValueError("invalid dataset episode path")
            name = rel.split("/")[1]
            if name in episodes[split]:
                raise ValueError("duplicate episode index")
            episodes[split][name] = {
                "episode_id": entry.get("episode_id"),
                "name": name, "split": split,
            }
    # Only known aggregate summary keys are exposed; unknown/private fields
    # introduced by a future evaluator do not silently enter the API.
    allowed = {"kind", "policies", "splits", "replay", "model_counts",
               "v2_label_counts", "clean_false_accusations", "shortcut_warning"}
    summary = {key: value for key, value in summary.items() if key in allowed}
    return root, summary, episodes


def dashboard_server(dataset: Path, *, port: int = 8765):
    """Create a localhost HTTP server; caller owns serve_forever()/close()."""
    root, summary, episodes = _dataset(dataset)

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "LedgerGymLocal/1.0"

        def _send(self, code, payload, mime):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                             "base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, code, data):
            payload = json.dumps(data, ensure_ascii=True, allow_nan=False,
                                 separators=(",", ":")).encode("utf-8")
            self._send(code, payload, "application/json; charset=utf-8")

        def do_GET(self):
            url = urlsplit(self.path)
            path = url.path
            try:
                if path in ASSETS:
                    filename, mime = ASSETS[path]
                    self._send(200, (WEB / filename).read_bytes(), mime)
                elif path == "/api/health":
                    self._json(200, {"status": "ok", "mode": "local_read_only",
                                     "dataset": "synthetic_development"})
                elif path == "/api/summary":
                    self._json(200, summary)
                elif path == "/api/episodes":
                    self._json(200, {
                        "train": list(episodes["train"].values()),
                        "dev": list(episodes["dev"].values()),
                    })
                elif path == "/api/records":
                    query = parse_qs(url.query, keep_blank_values=True)
                    if set(query) != {"split", "episode", "table", "page"}:
                        raise ValueError("expected split, episode, table, page")
                    if any(len(values) != 1 for values in query.values()):
                        raise ValueError("duplicate parameters")
                    split, episode, table, page_value = (
                        query[key][0] for key in ("split", "episode", "table", "page")
                    )
                    if (split not in SPLITS or table not in TABLES
                            or episode not in episodes[split]
                            or not re.fullmatch(r"[0-9]{1,4}", page_value)):
                        raise ValueError("invalid records query")
                    page = int(page_value)
                    if page > 1000:
                        raise ValueError("page too large")
                    # Never open a caller-controlled path. Explicitly load
                    # ONLY this episode's public/ folder.
                    folder = root / split / episode / "public"
                    public = load_public_episode(folder)
                    rows = public["tables"][table]
                    start = page * 50
                    self._json(200, {
                        "split": split, "episode": episode, "table": table,
                        "page": page, "page_size": 50, "total": len(rows),
                        "records": rows[start:start + 50],
                        "manifest": {
                            "schema_version": public["manifest"].get("schema_version"),
                            "episode_id": public["manifest"].get("episode_id"),
                        },
                        "accounting_model": public["policy"].get("accounting_model"),
                    })
                else:
                    self._json(404, {"error": "not_found"})
            except json.JSONDecodeError:
                self._json(500, {"error": "local_dataset_unavailable"})
            except (ValueError, KeyError, TypeError):
                self._json(400, {"error": "invalid_request"})
            except OSError:
                self._json(500, {"error": "local_dataset_unavailable"})

        def log_message(self, format_string, *args):
            # Requests can include identifiers or public financial records;
            # avoid logging query parameters to the operator's terminal.
            return

    return ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset", type=Path, help="existing synthetic 10+10 dataset")
    source.add_argument("--demo", action="store_true", help="create temporary 10+10 local data")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")

    def serve(root):
        with dashboard_server(root, port=args.port) as server:
            host, port = server.server_address
            print(f"LedgerGym Dashboard: http://{host}:{port}", flush=True)
            print("Read-only. Stop with Ctrl+C.", flush=True)
            try:
                server.serve_forever(poll_interval=0.25)
            except KeyboardInterrupt:
                pass
            finally:
                server.shutdown()

    if args.demo:
        from .company_dataset import create_company_dataset
        from .fixture_evaluation import evaluate_fixture_dataset
        with tempfile.TemporaryDirectory(prefix="ledgergym-dashboard-") as temp:
            dataset = Path(temp) / "synthetic"
            print("Creating local 10+10 synthetic dataset...", flush=True)
            create_company_dataset(dataset, seed=2026,
                                   include_settlement_hard_negatives=True)
            evaluate_fixture_dataset(dataset, dataset / "evaluation")
            serve(dataset)
    else:
        serve(args.dataset)


if __name__ == "__main__":
    main()
