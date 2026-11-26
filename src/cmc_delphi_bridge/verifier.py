"""Turn three raw CoinMarketCap responses into a market regime and a dated evidence note."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from cmc_delphi_bridge.client import COIN_IDS, ENDPOINTS

RESPONSE_KEYS = ("quotes", "global_metrics", "fear_and_greed")

DEFAULT_LINKS = [
    "https://coinmarketcap.com/currencies/bitcoin/",
    "https://coinmarketcap.com/charts/fear-and-greed-index/",
]


def usd_quote(quotes_response: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Find a coin by CMC id in a v3 quotes response and return its USD quote."""
    wanted = COIN_IDS[symbol]
    for coin in quotes_response.get("data") or []:
        if coin.get("id") == wanted:
            for quote in coin.get("quote") or []:
                if quote.get("symbol") == "USD":
                    return quote
    raise KeyError(
        f"no USD quote for {symbol} (CMC id {wanted}) in the quotes response"
    )


def evaluate_regime(bundle: dict[str, Any], asset: str = "BTC") -> dict[str, Any]:
    """Read the asset, BTC, total market cap and the Fear and Greed Index, then label the regime."""
    asset = asset.strip().upper()
    if asset not in COIN_IDS:
        raise ValueError(f"asset must be one of {', '.join(COIN_IDS)}")
    btc = usd_quote(bundle["quotes"], "BTC")
    coin = usd_quote(bundle["quotes"], asset)
    gm = bundle["global_metrics"]["data"]
    gm_usd = gm["quote"]["USD"]
    fg = bundle["fear_and_greed"]["data"]

    fear_greed = int(fg["value"])
    mcap_change = float(gm_usd["total_market_cap_yesterday_percentage_change"])

    if fear_greed >= 60 and mcap_change > 0:
        regime = "risk_on"
    elif fear_greed <= 35 and mcap_change < 0:
        regime = "risk_off"
    else:
        regime = "mixed"

    return {
        "regime": regime,
        "asset": asset,
        "asset_price_usd": round(float(coin["price"]), 2),
        "asset_change_24h_pct": round(float(coin["percent_change_24h"]), 2),
        "asset_market_cap_usd": round(float(coin["market_cap"])),
        "btc_price_usd": round(float(btc["price"]), 2),
        "btc_change_24h_pct": round(float(btc["percent_change_24h"]), 2),
        "btc_dominance_pct": round(float(gm["btc_dominance"]), 2),
        "total_mcap_change_24h_pct": round(mcap_change, 2),
        "fear_greed_value": fear_greed,
        "fear_greed_label": str(fg["value_classification"]),
    }


def verdict(regime: str, side: str, yes_means: str) -> str:
    """Say whether the regime supports, cuts against or is neutral for a side.

    yes_means is the direction a YES outcome needs: "up" or "down".
    """
    if regime == "mixed":
        return "is neutral for"
    side_wants = yes_means if side == "YES" else ("down" if yes_means == "up" else "up")
    regime_points = "up" if regime == "risk_on" else "down"
    return "supports" if side_wants == regime_points else "cuts against"


def evidence_digest(
    bundle: dict[str, Any], market_address: str, side: str, note: str
) -> str:
    """SHA-256 over the raw responses plus the market, side and note. Anyone holding them can recompute it."""
    payload = {
        "responses": {k: bundle[k] for k in RESPONSE_KEYS},
        "market_address": market_address,
        "side": side,
        "note": note,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_evidence(
    bundle: dict[str, Any],
    market_address: str,
    question: str,
    side: str,
    yes_means: str = "up",
    asset: str = "BTC",
    links: list[str] | None = None,
) -> dict[str, Any]:
    """Build the note, links and digest for one prediction market side."""
    side = side.strip().upper()
    if side not in {"YES", "NO"}:
        raise ValueError("side must be YES or NO")
    yes_means = yes_means.strip().lower()
    if yes_means not in {"up", "down"}:
        raise ValueError("yes_means must be up or down")

    m = evaluate_regime(bundle, asset)
    as_of = bundle["quotes"]["status"]["timestamp"]
    note = (
        f"As of {as_of}, CoinMarketCap shows {m['asset']} at ${m['asset_price_usd']:,.2f} "
        f"({m['asset_change_24h_pct']:+.2f}% over 24h, market cap ${m['asset_market_cap_usd'] / 1e9:,.2f}B), BTC dominance at {m['btc_dominance_pct']:.2f}%, "
        f"total market cap {m['total_mcap_change_24h_pct']:+.2f}% against yesterday, and the "
        f"Fear and Greed Index at {m['fear_greed_value']} ({m['fear_greed_label']}). "
        f"I read that as a {m['regime'].replace('_', ' ')} market, which "
        f'{verdict(m["regime"], side, yes_means)} {side} on "{question}".'
    )
    links = links or list(DEFAULT_LINKS)
    return {
        "market_address": market_address,
        "side": side,
        "note": note,
        "links": links,
        "metrics": m,
        "as_of": as_of,
        "source": bundle.get("source", "unknown"),
        "endpoints": list(ENDPOINTS.values()),
        "sha256": evidence_digest(bundle, market_address, side, note),
    }
