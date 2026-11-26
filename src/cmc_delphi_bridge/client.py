"""Small stdlib client for the three CoinMarketCap endpoints this project uses."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "https://pro-api.coinmarketcap.com"
KEYLESS_PREFIX = "/public-api"

ENDPOINTS: dict[str, str] = {
    "quotes": "/v3/cryptocurrency/quotes/latest",
    "global_metrics": "/v1/global-metrics/quotes/latest",
    "fear_and_greed": "/v3/fear-and-greed/latest",
}

# Tickers are not unique on CMC (14 listed coins use "BTC"), so coins are requested by CMC id.
COIN_IDS: dict[str, int] = {"BTC": 1, "ETH": 1027, "SOL": 5426}

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLE_FILES = {
    "quotes": "quotes_latest_v3.json",
    "global_metrics": "global_metrics_v1.json",
    "fear_and_greed": "fear_and_greed_v3.json",
}


class CMCError(RuntimeError):
    """A CoinMarketCap request failed."""


def load_api_key(env_path: str | Path = ".env") -> str | None:
    """Return CMC_API_KEY from the environment or a local .env file, or None to use the keyless API."""
    if os.environ.get("CMC_API_KEY", "").strip():
        return os.environ["CMC_API_KEY"].strip()
    p = Path(env_path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key.strip() == "CMC_API_KEY" and value.strip().strip("'\""):
                return value.strip().strip("'\"")
    return None


class CMCClient:
    """Calls the keyed Pro API when given a key, otherwise the keyless /public-api routes."""

    def __init__(
        self, api_key: str | None = None, timeout_seconds: float = 15.0
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @property
    def mode(self) -> str:
        return "keyed" if self.api_key else "keyless"

    def url_for(self, name: str, params: dict[str, Any] | None = None) -> str:
        prefix = "" if self.api_key else KEYLESS_PREFIX
        url = f"{BASE_URL}{prefix}{ENDPOINTS[name]}"
        return url + ("?" + urllib.parse.urlencode(params) if params else "")

    def get(self, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "cmc-delphi-signal-bridge/0.2",
        }
        if self.api_key:
            headers["X-CMC_PRO_API_KEY"] = self.api_key
        req = urllib.request.Request(
            self.url_for(name, params), headers=headers, method="GET"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            raise CMCError(f"CMC HTTP {exc.code} on {ENDPOINTS[name]}: {body}") from exc
        except urllib.error.URLError as exc:
            raise CMCError(
                f"CMC network error on {ENDPOINTS[name]}: {exc.reason}"
            ) from exc

    def fetch_bundle(self, symbols: list[str] | None = None) -> dict[str, Any]:
        """One call to each endpoint. Returns the raw responses untouched."""
        ids = ",".join(str(COIN_IDS[s]) for s in (symbols or ["BTC", "ETH", "SOL"]))
        return {
            "source": self.mode,
            "quotes": self.get("quotes", {"id": ids, "convert": "USD"}),
            "global_metrics": self.get("global_metrics", {"convert": "USD"}),
            "fear_and_greed": self.get("fear_and_greed"),
        }


def load_sample_bundle() -> dict[str, Any]:
    """Real keyless responses captured on 2026-11-26, for offline runs and tests."""
    bundle: dict[str, Any] = {"source": "sample"}
    for name, filename in SAMPLE_FILES.items():
        bundle[name] = json.loads((SAMPLES_DIR / filename).read_text(encoding="utf-8"))
    return bundle
