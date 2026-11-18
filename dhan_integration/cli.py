"""Command line interface for Dhan historical data; data-only, no order APIs."""
from __future__ import annotations

import argparse
from datetime import date
import os

from dotenv import load_dotenv

from .client import DhanClient
from .downloader import download_active_future, download_options, download_spot


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD") from exc


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Dhan historical data downloader (paper research only)")
    parser.add_argument("--test-auth", action="store_true", help="Verify token and data API permission with a small Nifty index request")
    sub = parser.add_subparsers(dest="command")

    def common(p):
        p.add_argument("--from", dest="start", type=parse_date, required=True)
        p.add_argument("--to", dest="end", type=parse_date, required=True)
        p.add_argument("--interval", type=int, choices=(1, 5, 15, 25, 60), default=1)

    spot = sub.add_parser("spot", help="Download Nifty 50 index candles")
    common(spot)
    options = sub.add_parser("options", help="Download rolling expired Nifty options")
    common(options)
    options.add_argument("--expiry-flag", choices=("WEEK", "MONTH"), default="WEEK")
    options.add_argument("--expiry-code", type=int, choices=(0, 1, 2), default=1)
    options.add_argument("--max-strike-offset", type=int, choices=range(0, 11), default=10)
    futures = sub.add_parser("futures", help="Download an ACTIVE Nifty futures contract only")
    common(futures)
    futures.add_argument("--security-id", required=True)

    args = parser.parse_args()
    if not args.test_auth and not args.command:
        parser.print_help()
        return
    if args.command and args.start >= args.end:
        parser.error("--from must be earlier than --to")
    client = DhanClient()
    if args.test_auth:
        client.test_auth()
        print("Dhan token and historical Data API access test passed.")
        return
    if args.command == "spot":
        download_spot(client, args.start, args.end, args.interval)
    elif args.command == "options":
        download_options(client, args.start, args.end, args.interval,
                         args.expiry_flag, args.expiry_code, args.max_strike_offset)
    elif args.command == "futures":
        download_active_future(client, args.security_id, args.start, args.end, args.interval)


if __name__ == "__main__":
    main()
