"""Command line entry point: offline demo, live capture, and the stdio MCP server."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cmc_delphi_bridge.client import (
    CMCClient,
    CMCError,
    load_api_key,
    load_sample_bundle,
)
from cmc_delphi_bridge.mcp_server import serve_stdio
from cmc_delphi_bridge.verifier import build_evidence


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cmc-bridge",
        description="CoinMarketCap data to a dated prediction market evidence note",
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("demo", "Build a note from the captured sample responses (no network)"),
        ("live", "Call the three CMC endpoints now and build a note"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument(
            "--market", default="0x0000000000000000000000000000000000000000"
        )
        cmd.add_argument(
            "--question", default="Will BTC close the week higher than it opened?"
        )
        cmd.add_argument("--side", default="YES", choices=["YES", "NO"])
        cmd.add_argument("--asset", default="BTC", choices=["BTC", "ETH", "SOL"])
        cmd.add_argument("--yes-means", default="up", choices=["up", "down"])
    sub.choices["live"].add_argument(
        "--save",
        metavar="PATH",
        help="Write the raw responses and the note to this JSON file",
    )
    sub.add_parser("mcp", help="Run the stdio MCP server")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "mcp":
        return serve_stdio()
    if args.command == "demo":
        bundle = load_sample_bundle()
    else:
        try:
            bundle = CMCClient(api_key=load_api_key()).fetch_bundle()
        except CMCError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    evidence = build_evidence(
        bundle, args.market, args.question, args.side, args.yes_means, args.asset
    )
    print(json.dumps(evidence, indent=2))
    if args.command == "live" and args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"evidence": evidence, "responses": bundle}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"saved {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
