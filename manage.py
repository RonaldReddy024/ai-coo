#!/usr/bin/env python
import argparse
import json
import time
import sys

import requests


BASE_URL = "http://127.0.0.1:8000"


def run_task(args: argparse.Namespace) -> int:
    """
    Call POST /tasks/run_async from the CLI.
    """
    # Build metadata dict
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print("Error: --metadata must be valid JSON (e.g. '{\"week\": \"2025-12-01\"}')")
            return 1
    else:
        metadata = {}

    payload = {
        "title": args.title,
        "company_id": args.company_id,
        "squad": args.squad,
        "metadata": metadata,
    }

    try:
        resp = requests.post(
            f"{BASE_URL}/tasks/run_async",
            json=payload,
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"Error calling API: {e}")
        return 1

    if resp.status_code != 200:
        print(f"API error {resp.status_code}: {resp.text}")
        return 1

    data = resp.json()
    task = data.get("task", {})
    task_id = task.get("id")

    print(f"Task created: id={task_id}, status={task.get('status')}")
    print("Title:", task.get("title"))
    print("Metadata:", json.dumps(task.get("metadata_json", {}), indent=2))

    # If user didn't ask to wait, we’re done
    if not args.wait or not task_id:
        return 0

    print("\nWaiting for task to complete (polling /tasks/{id}/status)...\n")

    # Poll for completion
    while True:
        try:
            status_resp = requests.get(
                f"{BASE_URL}/tasks/{task_id}/status",
                timeout=10,
            )
        except requests.RequestException as e:
            print(f"Error polling status: {e}")
            return 1

        if status_resp.status_code != 200:
            print(f"Status error {status_resp.status_code}: {status_resp.text}")
            return 1

        status_data = status_resp.json()
        status = status_data.get("status")
        result_text = status_data.get("result_text")

        print(f"Task {task_id} status: {status}")

        if status in ("completed", "failed"):
            print("\nFinal result_text:\n")
            print(result_text or "(no result_text)")
            break

        time.sleep(args.interval)

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WorkYodha AI-COO CLI helper"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run-task subcommand
    run_parser = subparsers.add_parser(
        "run-task",
        help="Create an async AI-COO task via /tasks/run_async",
    )
    run_parser.add_argument(
        "--title",
        required=True,
        help="Task title, e.g. 'Prepare weekly revenue summary'",
    )
    run_parser.add_argument(
        "--company-id",
        type=int,
        help="Optional company_id to attach to the task",
    )
    run_parser.add_argument(
        "--squad",
        help="Optional squad name, e.g. 'finance'",
    )
    run_parser.add_argument(
        "--metadata",
        help="Optional metadata as JSON string, e.g. '{\"week\": \"2025-12-01\"}'",
    )
    run_parser.add_argument(
        "--wait",
        action="store_true",
        help="If set, poll /tasks/{id}/status until completed",
    )
    run_parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Polling interval in seconds when --wait is used (default: 3).",
    )

    args = parser.parse_args()

    if args.command == "run-task":
        exit_code = run_task(args)
    else:
        parser.print_help()
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
