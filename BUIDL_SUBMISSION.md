# CMC Delphi Signal Bridge: DoraHacks BUIDL submission

**Hackathon**: Build with CMC: API Hackathon (#2466)
**Track**: AI Agents and Automation
**Repository**: https://github.com/manderson240/cmc-delphi-signal-bridge

This is the text I paste into the DoraHacks build form, kept in the repo so it stays in step with the code.

## Form fields

### Name
```text
CMC Delphi Signal Bridge
```

### Brief description (112 characters)
```text
Turns three live CoinMarketCap endpoints into a dated, hashed evidence note for one side of a prediction market.
```

### Tags
```text
AI Agents, CoinMarketCap API, MCP, Prediction Markets, Python
```

### Team
```text
Mike Anderson
```

### Links
- GitHub: https://github.com/manderson240/cmc-delphi-signal-bridge
- Demo video: https://raw.githubusercontent.com/manderson240/cmc-delphi-signal-bridge/main/docs/cmc_bridge_demo.mp4

### Contact
- Telegram: `manderson240`
- Discord: `miked238725`

## Description

### Why I built this

Forecasting agents often justify a position with something like "sentiment looks bullish", with no date, no numbers and no source. I wanted a tool an agent can call that returns a short note with the exact figures, the CMC timestamp they came from, and a hash that ties the note to the raw responses.

### How it works

It calls three CoinMarketCap endpoints:

- `GET /v3/cryptocurrency/quotes/latest` with `id=1,1027,5426` for the price, 24h change and market cap of BTC, ETH or SOL
- `GET /v1/global-metrics/quotes/latest` for BTC dominance and the total market cap change against yesterday
- `GET /v3/fear-and-greed/latest` for the index and its label

It labels the market risk on (Fear and Greed 60 or more and market cap up), risk off (35 or less and market cap down) or mixed. Given a question, a side and whether YES needs prices up or down, it writes one paragraph saying whether that regime supports, cuts against or is neutral for the side. The output includes a SHA-256 over the three raw responses, the market address, the side and the note, which anyone can recompute.

### Verification

The repo ships three unedited keyless responses captured on 2026-11-26 at 05:20 UTC in `src/cmc_delphi_bridge/samples/`. The client code that makes the calls is `src/cmc_delphi_bridge/client.py`. Running the offline demo on those responses gives:

"As of 2026-11-26T05:20:17.241Z, CoinMarketCap shows BTC at $60,871.35 (+2.87% over 24h, market cap $1,224.58B), BTC dominance at 58.72%, total market cap +2.56% against yesterday, and the Fear and Greed Index at 10 (Extreme fear). I read that as a mixed market, which is neutral for YES on "Will BTC close the week higher than it opened?"."

`cmc-bridge live --save receipts/now.json` makes the three calls again and saves the raw responses next to the note.

### How to try it

`uv sync`, then `uv run cmc-bridge demo` with no key and no network. `uv run cmc-bridge live` calls the API (keyless works for a few calls, a free key in `.env` removes the limit). `uv run cmc-bridge mcp` starts the MCP server with two tools, `cmc_market_regime` and `cmc_evidence_note`. There are 38 tests that run offline, and the verifier is mutation-tested.

### What the API enabled and where it got in the way

CMC's own `status.timestamp` dates every note, and `total_market_cap_yesterday_percentage_change` saves keeping history. What got in the way: `symbol=BTC` returns 14 different coins, so I request by id. v1 and v3 responses have different shapes. The v1 quotes route I started on is deprecated. The keyless limit returns HTTP 429 (error 1022) with no reset time. Details are in `docs/cmc_api_feedback.md`.

### Tech

Python 3.11 standard library only: `urllib` for HTTP, `hashlib` for the digest, a line based JSON-RPC loop for MCP. Tests with pytest.

### Limits

The regime rule is two thresholds, meant to be readable rather than clever. The note covers BTC, ETH and SOL, chosen by an argument rather than read from the question. The tool writes the note but does not post it anywhere.

### Future roadmap

Pick the asset from the question text instead of an argument, and add more coins by adding their CMC ids.
