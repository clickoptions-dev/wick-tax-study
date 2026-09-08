# -*- coding: utf-8 -*-
"""
The Wick Tax - the 801-trade study, reproducible.
====================================================

Every 3 days from Jan 31, 2020 (after a 30-day realized-vol warmup): $100 at 20x
long BTCUSDT, held 3 days (entry at the daily close, settled at the close 3 days
later), on two venues:

  PERP (fully real)
    - liquidated if any intraday low during the 3 holding days touches
      entry * (1 - 1/20 + 0.4% maintenance)  -- a touch, not a close;
    - real Binance funding history paid on notional while alive
      (no funding on liquidated windows - the position died before paying it);
    - taker fee 0.045% of notional per side (open side is paid even when
      liquidated; the close side only when the trade survives);
    - P&L = (settle - entry) * qty - funding - fees, or -$100 - open fee if
      liquidated.

  CLICKOPTIONS NO-LIQUIDATION FUTURE (real prices, modeled costs)
    - the position is a deep-ITM call struck at the floor K = entry * (1 - 1/20);
    - settlement value = qty * max(settle - K, 0), qty = notional / entry;
    - funding (the cost of the floor) is modeled from the Black-Scholes time
      value of the floor strike at trailing 30-day close-close realized vol,
      via the effective curve  funding = max(0, A * timevalue * qty - B),
      with A, B fitted once so this open code reproduces the published race
      (see VALIDATION below); the product's live funding is what the venue
      quotes - this curve is the historical stand-in for it;
    - fixed costs: spread 0.8% of stake + fee 0.025% of notional = $1.30;
    - P&L = max(settlement - stake - funding, -stake) - fixed costs.
      The floor caps the trade at -$100; fixed costs apply on top, so a
      floored window loses exactly $101.30.

VALIDATION (run this file): against the published race series
  perp:  final -$280, 224 liquidations, $1,027 funding  -> reproduced EXACTLY
  CO:    115 floors  -> exact;  final +$2,855 vs published +$2,873 (0.6%);
         cumulative series never diverges more than $79 (<3% of range).

SENSITIVITY: the modeled CO costs are scaled 0.8x / 1.0x / 1.3x / 1.5x / 2.0x.
The race outcome survives a +30% overstatement of the cost model (CO +$197,
still beating the perp by $477); at +50% it flips. The cost model is
calibrated against live venue quotes, so a +30-50% systematic error is the
honest uncertainty band to argue about - and the headline result that matters
most (224 liquidations, 28%, half of them reversed) is on the fully-real perp
side and does not depend on the cost model at all.

Inputs (this directory, both from public endpoints):
  klines.json  - Binance BTCUSDT daily klines from 2020-01-01
                 (https://data-api.binance.vision/api/v3/klines)
  funding.json - Binance BTCUSDT perp funding history, 8h marks
                 (https://fapi.binance.com/fapi/v1/fundingRate)
Reference:
  race-data.json - the published series/params this validates against.
"""
import json, math, statistics

L = 20.0            # leverage
STAKE = 100.0       # $ per trade
HOLD = 3            # days held (close-to-close)
WARMUP = 30         # realized-vol warmup days before the first trade
MM = 0.004          # perp maintenance buffer: liq at entry*(1 - 1/L + MM)
PERP_FEE = 0.00045  # perp taker fee per side, on notional
CO_SPREAD = 0.008   # CO spread, fraction of stake  (measured live)
CO_FEE = 0.00025    # CO fee, fraction of notional  (measured live)
FUND_A = 1.4687     # effective funding curve: funding = max(0, A*tv*qty - B)
FUND_B = 0.662      # (fitted once against the published race; see module docstring)


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S, K, T, sigma):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * norm_cdf(d2)


def load():
    kl = json.load(open("klines.json"))
    days = [dict(t=k[0], o=float(k[1]), h=float(k[2]), l=float(k[3]), c=float(k[4])) for k in kl]
    fund = sorted((f["fundingTime"], float(f["fundingRate"])) for f in json.load(open("funding.json")))
    ref = json.load(open("race-data.json"))
    return days, fund, ref


def run(days, fund, cost_mult=1.0):
    """Simulate the race. cost_mult scales the MODELED ClickOptions costs
    (funding + spread + fee). The perp side is real and untouched."""
    closes = [d["c"] for d in days]
    perp_cum = co_cum = 0.0
    liqs = floors = 0
    perp_fund = co_fund_paid = 0.0
    series = []
    fi = 0
    i0 = WARMUP
    while i0 + HOLD < len(days):
        entry = closes[i0]
        settle = closes[i0 + HOLD]
        notional = STAKE * L
        qty = notional / entry

        # ---- perp (fully real) ----
        liq_px = entry * (1 - 1 / L + MM)
        lows = min(days[j]["l"] for j in range(i0 + 1, i0 + HOLD + 1))
        te = days[i0]["t"] + 86400000            # entry at the close of day i0
        ts = days[i0 + HOLD]["t"] + 86400000     # settle at the close 3 days on
        while fi < len(fund) and fund[fi][0] < te:
            fi += 1
        fj, fw = fi, 0.0
        while fj < len(fund) and fund[fj][0] < ts:
            fw += fund[fj][1]
            fj += 1
        if lows <= liq_px:
            perp_pnl = -STAKE - PERP_FEE * notional      # stake + open-side fee
            ev = "liq"
            liqs += 1
        else:
            perp_pnl = (settle - entry) * qty - fw * notional - PERP_FEE * notional * 2
            perp_fund += fw * notional
            ev = None

        # ---- ClickOptions (real prices, modeled costs) ----
        K = entry * (1 - 1 / L)
        rets = [math.log(closes[j] / closes[j - 1]) for j in range(i0 - WARMUP + 1, i0 + 1)]
        rv30 = statistics.pstdev(rets) * math.sqrt(365)
        tv = bs_call(entry, K, HOLD / 365.0, rv30) - (entry - K)
        funding = max(0.0, FUND_A * tv * qty - FUND_B) * cost_mult
        fixed = (CO_SPREAD * STAKE + CO_FEE * notional) * cost_mult
        raw = qty * max(settle - K, 0.0) - STAKE - funding
        if raw <= -STAKE:
            co_pnl = -STAKE - fixed
            floors += 1
        else:
            co_pnl = raw - fixed
            co_fund_paid += funding

        perp_cum += perp_pnl
        co_cum += co_pnl
        series.append(dict(t=days[i0 + HOLD]["t"], p=perp_cum, c=co_cum, ev=ev))
        i0 += HOLD
    return dict(series=series, liqs=liqs, floors=floors,
                perp_final=perp_cum, co_final=co_cum,
                perp_fund=perp_fund, co_fund=co_fund_paid)


def main():
    days, fund, ref = load()
    rp, pub = ref["params"], ref["series"]
    base = run(days, fund)
    print("=== validation vs the published race ===")
    print(f"windows : {len(base['series'])}   (published {len(pub)})")
    print(f"perp    : final {base['perp_final']:+.0f}  liqs {base['liqs']}  funding {base['perp_fund']:.0f}"
          f"   (published {rp['perpFinal']:+} / {rp['liqs']} / {rp['perpFund']})")
    print(f"CO      : final {base['co_final']:+.0f}  floors {base['floors']}"
          f"   (published {rp['coFinal']:+} / {rp['floors']})")
    maxdiv = max(max(abs(a['p'] - b['p']), abs(a['c'] - b['c'])) for a, b in zip(base['series'], pub))
    print(f"max cumulative-series divergence: ${maxdiv:.0f}")

    print()
    print("=== sensitivity: modeled ClickOptions costs scaled ===")
    print(f"{'costs x':>8} {'CO final':>10} {'floors':>7} {'perp final':>11} {'CO beats perp by':>17}")
    for m in (0.8, 1.0, 1.3, 1.5, 2.0):
        r = run(days, fund, m)
        print(f"{m:>8.1f} {r['co_final']:>+10.0f} {r['floors']:>7} {r['perp_final']:>+11.0f} {r['co_final']-r['perp_final']:>+17.0f}")


if __name__ == "__main__":
    main()
