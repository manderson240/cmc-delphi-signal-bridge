"""Tests run offline against real CoinMarketCap responses captured on 2026-11-26."""

from __future__ import annotations

import copy
import io
import json
from typing import Any, Self
from unittest.mock import patch

import pytest

from cmc_delphi_bridge import mcp_server
from cmc_delphi_bridge.cli import main
from cmc_delphi_bridge.client import (
    CMCClient,
    CMCError,
    load_api_key,
    load_sample_bundle,
)
from cmc_delphi_bridge.verifier import (
    build_evidence,
    evaluate_regime,
    evidence_digest,
    usd_quote,
    verdict,
)

MARKET = "0x1111111111111111111111111111111111111111"


def with_values(fear_greed: int, mcap_change: float) -> dict[str, Any]:
    bundle = copy.deepcopy(load_sample_bundle())
    bundle["fear_and_greed"]["data"]["value"] = fear_greed
    bundle["global_metrics"]["data"]["quote"]["USD"][
        "total_market_cap_yesterday_percentage_change"
    ] = mcap_change
    return bundle


def test_sample_regime_matches_captured_numbers() -> None:
    m = evaluate_regime(load_sample_bundle())
    assert m["btc_price_usd"] == 60871.35
    assert m["fear_greed_value"] == 10
    assert m["fear_greed_label"] == "Extreme fear"
    assert m["total_mcap_change_24h_pct"] == 2.56
    assert m["regime"] == "mixed"  # extreme fear but the market is up, so no clear call


def test_btc_is_picked_by_id_not_ticker() -> None:
    quotes = copy.deepcopy(load_sample_bundle()["quotes"])
    impostor = {
        "id": 99999,
        "symbol": "BTC",
        "quote": [{"symbol": "USD", "price": 0.01, "percent_change_24h": 0}],
    }
    quotes["data"].insert(0, impostor)
    assert usd_quote(quotes, "BTC")["price"] == pytest.approx(60871.35, abs=0.01)


def test_missing_coin_raises() -> None:
    with pytest.raises(KeyError):
        usd_quote({"data": []}, "BTC")


def test_missing_fear_greed_value_raises() -> None:
    bundle = load_sample_bundle()
    del bundle["fear_and_greed"]["data"]["value"]
    with pytest.raises(KeyError):
        evaluate_regime(bundle)


def test_fear_greed_zero_is_read_as_zero() -> None:
    assert evaluate_regime(with_values(0, -1.0))["fear_greed_value"] == 0
    assert evaluate_regime(with_values(0, -1.0))["regime"] == "risk_off"


@pytest.mark.parametrize(
    ("fg", "mcap", "regime"),
    [
        (60, 0.1, "risk_on"),
        (59, 0.1, "mixed"),
        (60, 0.0, "mixed"),
        (35, -0.1, "risk_off"),
        (36, -0.1, "mixed"),
        (35, 0.0, "mixed"),
    ],
)
def test_regime_thresholds(fg: int, mcap: float, regime: str) -> None:
    assert evaluate_regime(with_values(fg, mcap))["regime"] == regime


@pytest.mark.parametrize(
    ("regime", "side", "yes_means", "expected"),
    [
        ("risk_on", "YES", "up", "supports"),
        ("risk_on", "NO", "up", "cuts against"),
        ("risk_off", "YES", "up", "cuts against"),
        ("risk_off", "NO", "up", "supports"),
        ("risk_off", "YES", "down", "supports"),
        ("risk_on", "YES", "down", "cuts against"),
        ("risk_on", "NO", "down", "supports"),
        ("risk_off", "NO", "down", "cuts against"),
        ("mixed", "YES", "up", "is neutral for"),
        ("mixed", "NO", "down", "is neutral for"),
    ],
)
def test_verdict(regime: str, side: str, yes_means: str, expected: str) -> None:
    assert verdict(regime, side, yes_means) == expected


def test_risk_off_note_does_not_claim_support_for_yes_up() -> None:
    ev = build_evidence(
        with_values(20, -3.0), MARKET, "Will BTC rise this week?", "yes"
    )
    assert "cuts against YES" in ev["note"]
    assert "supports" not in ev["note"]


def test_note_is_dated_from_the_response_and_plain() -> None:
    ev = build_evidence(load_sample_bundle(), MARKET, "Will BTC rise this week?", "YES")
    assert ev["as_of"] == "2026-11-26T05:20:17.241Z"
    assert ev["note"].startswith("As of 2026-11-26T05:20:17.241Z")
    for ch in ("\u2014", "\u2013", ";"):
        assert ch not in ev["note"]


def test_digest_is_recomputable_and_covers_the_responses() -> None:
    bundle = load_sample_bundle()
    ev = build_evidence(bundle, MARKET, "Will BTC rise this week?", "YES")
    assert ev["sha256"] == evidence_digest(bundle, MARKET, "YES", ev["note"])
    edits = {
        "quotes": lambda b: b["quotes"]["data"][1]["quote"][0].update(
            price=1.0
        ),  # ETH, unused by the note
        "global_metrics": lambda b: b["global_metrics"]["data"].update(
            eth_dominance=0.0
        ),
        "fear_and_greed": lambda b: b["fear_and_greed"]["status"].update(elapsed=999),
    }
    for edit in edits.values():
        changed = copy.deepcopy(bundle)
        edit(changed)
        assert evidence_digest(changed, MARKET, "YES", ev["note"]) != ev["sha256"]


def test_bad_side_and_direction_rejected() -> None:
    with pytest.raises(ValueError):
        build_evidence(load_sample_bundle(), MARKET, "q", "MAYBE")
    with pytest.raises(ValueError):
        build_evidence(load_sample_bundle(), MARKET, "q", "YES", yes_means="sideways")


class FakeResponse(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def test_keyless_client_uses_public_api_and_sends_no_key() -> None:
    seen = []

    def fake_urlopen(req: Any, timeout: float) -> FakeResponse:
        seen.append(req)
        return FakeResponse(b'{"data": {}, "status": {}}')

    with patch("urllib.request.urlopen", fake_urlopen):
        CMCClient().fetch_bundle()
    assert [r.full_url.split("?")[0] for r in seen] == [
        "https://pro-api.coinmarketcap.com/public-api/v3/cryptocurrency/quotes/latest",
        "https://pro-api.coinmarketcap.com/public-api/v1/global-metrics/quotes/latest",
        "https://pro-api.coinmarketcap.com/public-api/v3/fear-and-greed/latest",
    ]
    assert "id=1%2C1027%2C5426" in seen[0].full_url
    assert all(r.get_header("X-cmc_pro_api_key") is None for r in seen)


def test_keyed_client_uses_pro_routes_and_header() -> None:
    seen = []

    def fake_urlopen(req: Any, timeout: float) -> FakeResponse:
        seen.append(req)
        return FakeResponse(b"{}")

    with patch("urllib.request.urlopen", fake_urlopen):
        CMCClient(api_key="test-key").get("fear_and_greed")
    assert (
        seen[0].full_url == "https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest"
    )
    assert seen[0].get_header("X-cmc_pro_api_key") == "test-key"


def test_network_error_becomes_cmc_error() -> None:
    import urllib.error

    def boom(req: Any, timeout: float) -> FakeResponse:
        raise urllib.error.URLError("offline")

    with patch("urllib.request.urlopen", boom), pytest.raises(CMCError):
        CMCClient().get("quotes")


def test_load_api_key(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CMC_API_KEY", raising=False)
    assert load_api_key(tmp_path / ".env") is None
    (tmp_path / ".env").write_text("CMC_API_KEY='abc'\n")
    assert load_api_key(tmp_path / ".env") == "abc"
    monkeypatch.setenv("CMC_API_KEY", "from-env")
    assert load_api_key(tmp_path / ".env") == "from-env"


def test_cli_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", "--side", "NO"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["side"] == "NO" and out["source"] == "sample"


def test_cli_live_save(tmp_path: Any, capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(CMCClient, "fetch_bundle", lambda self: load_sample_bundle()):
        assert main(["live", "--save", str(tmp_path / "r.json")]) == 0
    saved = json.loads((tmp_path / "r.json").read_text())
    assert saved["evidence"]["sha256"] == evidence_digest(
        saved["responses"],
        saved["evidence"]["market_address"],
        "YES",
        saved["evidence"]["note"],
    )


def test_mcp_initialize_list_and_call() -> None:
    init = mcp_server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert init["result"]["serverInfo"]["name"] == "cmc-delphi-signal-bridge"
    assert (
        mcp_server.handle_request(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        is None
    )
    names = [
        t["name"]
        for t in mcp_server.handle_request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )["result"]["tools"]
    ]
    assert names == ["cmc_market_regime", "cmc_evidence_note"]
    call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "cmc_evidence_note",
            "arguments": {
                "market_address": MARKET,
                "question": "q",
                "side": "YES",
                "offline": True,
            },
        },
    }
    result = mcp_server.handle_request(call)["result"]["structuredContent"]
    assert result["as_of"] == "2026-11-26T05:20:17.241Z"


def test_mcp_errors_are_reported_not_raised() -> None:
    bad = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "cmc_evidence_note", "arguments": {"offline": True}},
    }
    assert mcp_server.handle_request(bad)["error"]["code"] == -32000
    unknown = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "nope", "arguments": {"offline": True}},
    }
    assert mcp_server.handle_request(unknown)["error"]["code"] == -32602


def test_mcp_stdio_roundtrip(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    monkeypatch.setattr(
        "sys.stdin", io.StringIO("\n".join(json.dumps(x) for x in lines) + "\n\n")
    )
    assert mcp_server.serve_stdio() == 0
    replies = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]


@pytest.mark.parametrize(
    "asset, price, change, mcap_b",
    [("ETH", "$1,698.14", "+2.34%", "$207.60B"), ("SOL", "$71.15", "+3.63%", "$42.13B")],
)
def test_eth_and_sol_notes_use_their_own_quote(
    asset: str, price: str, change: str, mcap_b: str
) -> None:
    ev = build_evidence(
        load_sample_bundle(), MARKET, f"Will {asset} rise?", "YES", asset=asset
    )
    assert f"shows {asset} at {price} ({change} over 24h, market cap {mcap_b})" in ev["note"]
    assert "$60,871.35" not in ev["note"]
    assert ev["metrics"]["asset"] == asset
    assert ev["metrics"]["btc_price_usd"] == 60871.35  # BTC context still reported


def test_asset_changes_the_digest() -> None:
    bundle = load_sample_bundle()
    digests = {
        build_evidence(bundle, MARKET, "q", "YES", asset=a)["sha256"]
        for a in ("BTC", "ETH", "SOL")
    }
    assert len(digests) == 3


def test_unknown_asset_rejected() -> None:
    with pytest.raises(ValueError, match="asset must be one of"):
        build_evidence(load_sample_bundle(), MARKET, "q", "YES", asset="DOGE")
