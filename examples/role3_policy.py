"""Tiny demo policy. Its only input is the judge's JSON conversation."""
import json
import sys


def investigate(initial):
    episode = initial["manifest"]["episode_id"]
    page = yield {"name": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 1}}
    records = page["result"]["records"]
    if records:
        doc = yield {"name": "get_document", "args": {"doc_id": records[0]["doc_id"]}}
        amount = doc["result"]["total_minor"]
        yield {"name": "calculator", "args": {"expression": f"{amount}+0"}}
    yield {"name": "submit", "args": {"findings": {"episode_id": episode, "findings": []}}}


def main():
    initial = json.loads(sys.stdin.readline())
    policy = investigate(initial["observation"])
    action = next(policy)
    while True:
        print(json.dumps(action), flush=True)
        message = json.loads(sys.stdin.readline())
        if message["terminated"] or message["truncated"]:
            return
        action = policy.send(message["observation"])


if __name__ == "__main__":
    main()
