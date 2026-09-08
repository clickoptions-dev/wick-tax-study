# The Wick Tax — the 801-trade study

The same trade, 801 times: every 3 days from January 2020, **$100 into a 20× long
on BTCUSDT**, held 3 days — once as a traditional perpetual future, once as a
[ClickOptions no-liquidation future](https://clickoptions.ai/futures).

Result over 801 identical windows (Jan 2020 – Sep 2026):

| | Perp | No-liquidation future |
|---|---|---|
| Final P&L | **−$280** | **+$2,873** |
| Liquidations | **224** (28% of all trades) | 0 — none possible |
| Max-loss settlements | — | 115 (capped at the $100 stake) |

Of the 224 wicks that liquidated the perp, **113 fully reversed** — the trade
would have come back above its liquidation price. Half the deaths were for
nothing. That is the wick tax.

**This repository is the full receipt.** Run one file, no dependencies beyond
Python 3:

```bash
python race_study.py
```

It reproduces the published race from raw exchange data and prints the
validation against the published series, then the sensitivity analysis.

## What is real and what is modeled

- **The perp side is fully real**: Binance daily OHLC, real funding history
  (7,307 records), taker fees, liquidation on an intraday *touch* of
  `entry × (1 − 1/20 + 0.4% maintenance)`. The reproduction is exact to the
  dollar: −$280, 224 liquidations, $1,027 funding.
- **The ClickOptions side uses real prices but modeled historical costs** (the
  product launched in 2026, so 2020-era costs cannot be observed). Costs follow
  the product's measured structure — spread 0.8% of stake, fee 0.025% of
  notional, and funding derived from the Black-Scholes time value of the floor
  strike at trailing 30-day realized volatility, calibrated against live venue
  quotes. Reproduction: max-loss count exact (115), final within 0.6%
  (+$2,855 vs +$2,873), cumulative series never diverging more than $79.

## Sensitivity — where the conclusion would break

We stress the modeled costs, because that is the honest attack surface:

| Modeled CO costs × | CO final | Beats perp by |
|---|---|---|
| 0.8 | +$4,670 | +$4,949 |
| 1.0 | +$2,855 | +$3,135 |
| **1.3** | **+$197** | **+$477** |
| 1.5 | −$1,526 | −$1,247 |
| 2.0 | −$5,680 | −$5,401 |

The outcome survives a **+30% overstatement** of the cost model; at +50% it
flips. The cost model is calibrated to live quotes, so that band is the honest
thing to argue about — and the headline numbers that matter most
(224 liquidations, 28%, half reversed) sit entirely on the fully-real perp side
and do not depend on the cost model at all.

## Files

| File | Contents |
|---|---|
| `race_study.py` | The whole study: model spec (docstring), simulation, validation, sensitivity |
| `klines.json` | Binance BTCUSDT daily klines from 2020-01-01 ([source](https://data-api.binance.vision/api/v3/klines)) |
| `funding.json` | Binance BTCUSDT perp funding history, 8h marks ([source](https://fapi.binance.com/fapi/v1/fundingRate)) |
| `race-data.json` | The published race series/params that the script validates against |

## See it move

The animated version of this dataset runs at the
[no-liquidation futures page](https://clickoptions.ai/futures) — the race, a playable
game on real weeks, and the methodology paper.

Found a flaw? Open an issue. That is what this repo is for.

---
*Not investment advice. Past performance is history, not prophecy.*
