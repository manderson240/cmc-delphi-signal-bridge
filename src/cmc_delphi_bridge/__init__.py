"""CoinMarketCap data to a dated prediction market evidence note, as a CLI and a stdio MCP server."""

from cmc_delphi_bridge.client import (
    COIN_IDS,
    ENDPOINTS,
    CMCClient,
    CMCError,
    load_sample_bundle,
)
from cmc_delphi_bridge.verifier import (
    build_evidence,
    evaluate_regime,
    evidence_digest,
    verdict,
)

__all__ = [
    "COIN_IDS",
    "ENDPOINTS",
    "CMCClient",
    "CMCError",
    "build_evidence",
    "evaluate_regime",
    "evidence_digest",
    "load_sample_bundle",
    "verdict",
]
