"""Minimal stdio MCP server (JSON-RPC, one message per line) with two tools."""

from __future__ import annotations

import json
import sys
from typing import Any

from cmc_delphi_bridge.client import (
    CMCClient,
    CMCError,
    load_api_key,
    load_sample_bundle,
)
from cmc_delphi_bridge.verifier import build_evidence, evaluate_regime

_SOURCE = {
    "offline": {
        "type": "boolean",
        "default": False,
        "description": "Use the captured sample responses",
    }
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "cmc_market_regime",
        "description": "BTC price, BTC dominance, total market cap change and Fear and Greed from CoinMarketCap, with a regime label.",
        "inputSchema": {"type": "object", "properties": dict(_SOURCE)},
    },
    {
        "name": "cmc_evidence_note",
        "description": "A dated evidence note for one side of a prediction market, with a SHA-256 over the raw CMC responses, market, side and note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "market_address": {"type": "string"},
                "question": {"type": "string"},
                "side": {"type": "string", "enum": ["YES", "NO"]},
                "yes_means": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "default": "up",
                },
                "asset": {
                    "type": "string",
                    "enum": ["BTC", "ETH", "SOL"],
                    "default": "BTC",
                },
                **_SOURCE,
            },
            "required": ["market_address", "question", "side"],
        },
    },
]


def _bundle(offline: bool) -> dict[str, Any]:
    return (
        load_sample_bundle()
        if offline
        else CMCClient(api_key=load_api_key()).fetch_bundle()
    )


def _result(req_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload)
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [{"type": "text", "text": text}],
            "structuredContent": payload,
        },
    }


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    """Answer one JSON-RPC request. Notifications get no reply."""
    method, req_id = req.get("method"), req.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cmc-delphi-signal-bridge", "version": "0.2.0"},
            },
        }
    if req_id is None:
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method != "tools/call":
        return _error(req_id, -32601, f"Method not found: {method}")

    params = req.get("params") or {}
    name, args = params.get("name"), params.get("arguments") or {}
    try:
        bundle = _bundle(bool(args.get("offline", False)))
        if name == "cmc_market_regime":
            return _result(
                req_id,
                {
                    **evaluate_regime(bundle),
                    "as_of": bundle["quotes"]["status"]["timestamp"],
                },
            )
        if name == "cmc_evidence_note":
            ev = build_evidence(
                bundle,
                args["market_address"],
                args["question"],
                args["side"],
                args.get("yes_means", "up"),
                args.get("asset", "BTC"),
            )
            return _result(req_id, ev)
    except (CMCError, KeyError, ValueError) as exc:
        return _error(req_id, -32000, str(exc))
    return _error(req_id, -32602, f"Unknown tool: {name}")


def serve_stdio() -> int:
    """Read requests from stdin and write replies to stdout until stdin closes."""
    for line in sys.stdin:
        if line.strip():
            resp = handle_request(json.loads(line))
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
    return 0
