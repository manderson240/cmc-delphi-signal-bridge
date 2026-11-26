# Notes on building with the CoinMarketCap API

## What the API made possible

Three calls give me everything the note needs: a price, a market wide move and a sentiment reading, all with timestamps from CMC itself. The `status.timestamp` on each response is what dates the note, so I never have to trust my own clock. The keyless `/public-api` routes meant I could build and test against real responses before I had a key, and the same parsing code works for both.

`total_market_cap_yesterday_percentage_change` in global metrics was the most useful single field. It saves keeping my own history to know whether the market is up on the day.

## Where it got in the way

1. **Tickers are not unique.** `quotes/latest?symbol=BTC,ETH,SOL` returned 28 coins: 14 using BTC, 8 using SOL and 6 using ETH. The first match is not always the one you mean. I switched to `id=1,1027,5426`, which is exact but means looking ids up first.
2. **v1 and v3 shapes differ.** In v3 quotes, `data` is a list and each coin's `quote` is a list of objects with a `symbol` field. In v1 global metrics, `quote` is an object keyed by currency. Fear and Greed in v3 returns a single object. Each needs its own parsing.
3. **Moving versions.** The v1 quotes and listings routes I first wrote against are marked deprecated in the docs in favour of v3, so I rewrote the client. A changelog entry per route with a removal date would help.
4. **The anonymous limit is low and undocumented in the response.** After a handful of keyless calls I got HTTP 429 with error 1022 ("limit for anonymous access"). That is fair, but the response does not say when it resets, so a client cannot back off sensibly.
