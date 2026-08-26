#!/usr/bin/env python3
"""Apple Ads economics: LTV per trial, break-even trial-start rate, and a scaling verdict.

Formula source: marketing/HANDBOOK.md Part 2.4 ("Економіка: скільки ти можеш собі дозволити
платити"). Two distinct rates matter and must not be confused:

  trial_to_paid_cvr        share of trial-STARTERS who convert to paying (Крок 2 — ~38%, an
                            input/assumption unless measured)
  download_to_trial_rate   share of DOWNLOADS that start a trial (Крок 3/4 — this is "the trial
                            rate" the break-even conclusion is about, e.g. "break-even ≈ 6.8%")

Every number this script prints in normal (non-self-check) mode carries a `derived:` tag naming
every input, per references/provenance.md — a wrong output must be traceable to the wrong input
without re-deriving it by hand.

Usage:
    economics.py --price 49.99 --commission 0.15 --retention 0.221 --trial-to-paid-cvr 0.38 \
                  --cpi 1.39 [--observed-trial-rate 0.05]
    economics.py --self-check
"""

from __future__ import annotations

import argparse


def ltv_per_paying_subscriber(price: float, commission: float, retention: float) -> float:
    """Net revenue per paying subscriber over their full lifetime.

    HANDBOOK.md Крок 1: first-year net, plus a renewal "tail" at the same retention rate every
    subsequent year — an infinite geometric series, net / (1 - retention). The handbook's own
    worked figure ("$54") is a rounded version of exactly this.
    """
    if not 0 <= retention < 1:
        raise ValueError("retention must be in [0, 1)")
    net_year_one = price * (1 - commission)
    return net_year_one / (1 - retention)


def ltv_per_trial(price: float, commission: float, retention: float, trial_to_paid_cvr: float) -> float:
    """HANDBOOK.md Крок 2: LTV per subscriber, discounted by how many trial-starters ever pay."""
    return ltv_per_paying_subscriber(price, commission, retention) * trial_to_paid_cvr


def breakeven_trial_start_rate(ltv_trial: float, cpi: float) -> float:
    """HANDBOOK.md Крок 3/4: the download-to-trial rate at which LTV/download exactly covers CPI."""
    if ltv_trial <= 0:
        raise ValueError("ltv_per_trial must be positive")
    return cpi / ltv_trial


def scaling_verdict(observed_trial_rate: float, breakeven_rate: float) -> str:
    if observed_trial_rate >= breakeven_rate:
        return (
            f"observed trial-start rate {observed_trial_rate:.1%} clears break-even "
            f"({breakeven_rate:.1%}) — the arithmetic supports raising spend"
        )
    return (
        f"observed trial-start rate {observed_trial_rate:.1%} is BELOW break-even "
        f"({breakeven_rate:.1%}) — fix the trial rate (onboarding/paywall — product work) before "
        f"raising spend; bidding harder at a losing trial rate just buys more of the same loss"
    )


def _tag(*input_names: str) -> str:
    return f"derived:({','.join(input_names)})"


def run(args: argparse.Namespace) -> None:
    inputs = "price,commission,retention,trial_to_paid_cvr"
    ltv_sub = ltv_per_paying_subscriber(args.price, args.commission, args.retention)
    print(f"LTV per paying subscriber: ${ltv_sub:.2f}  [{_tag('price', 'commission', 'retention')}]")

    ltv_trial = ltv_per_trial(args.price, args.commission, args.retention, args.trial_to_paid_cvr)
    print(f"LTV per trial start:       ${ltv_trial:.2f}  [{_tag(inputs)}]")

    breakeven = breakeven_trial_start_rate(ltv_trial, args.cpi)
    print(
        f"Break-even trial-start rate: {breakeven:.2%}  "
        f"[{_tag(inputs + ',cpi')}]"
    )

    if args.observed_trial_rate is not None:
        print(scaling_verdict(args.observed_trial_rate, breakeven))
    else:
        print("(pass --observed-trial-rate to get a scaling verdict against this break-even point)")


def self_check() -> None:
    # HANDBOOK.md Part 2.4 worked example. The handbook rounds at every step (LTV/subscriber to
    # "$54", the final LTV/trial to "$20.50"); this script keeps full precision throughout, so the
    # check is "close to" the handbook's rounded figures, not bit-exact.
    price, commission, retention, trial_to_paid_cvr, cpi = 49.99, 0.15, 0.221, 0.38, 1.39

    ltv_sub = ltv_per_paying_subscriber(price, commission, retention)
    assert 53.0 <= ltv_sub <= 55.0, f"LTV/subscriber {ltv_sub:.2f} should be close to handbook's ~$54"

    ltv_trial = ltv_per_trial(price, commission, retention, trial_to_paid_cvr)
    assert abs(ltv_trial - 20.50) < 1.00, f"LTV/trial {ltv_trial:.2f} should be close to handbook's ~$20.50"

    breakeven = breakeven_trial_start_rate(ltv_trial, cpi)
    assert abs(breakeven - 0.068) < 0.005, f"break-even {breakeven:.4f} should be close to handbook's ~6.8%"

    # Break-even must respond correctly to every input direction (US5 acceptance scenario 2/3):
    # higher price, lower commission, higher retention, or higher trial_to_paid_cvr each raise LTV
    # and therefore LOWER the break-even trial-start rate needed to justify the same CPI.
    higher_price_ltv = ltv_per_trial(price * 2, commission, retention, trial_to_paid_cvr)
    assert higher_price_ltv > ltv_trial
    assert breakeven_trial_start_rate(higher_price_ltv, cpi) < breakeven

    lower_commission_ltv = ltv_per_trial(price, 0.0, retention, trial_to_paid_cvr)
    assert lower_commission_ltv > ltv_trial

    higher_retention_ltv = ltv_per_trial(price, commission, 0.9, trial_to_paid_cvr)
    assert higher_retention_ltv > ltv_trial

    # Verdict direction, both sides:
    assert "BELOW" in scaling_verdict(0.05, breakeven)
    assert "clears" in scaling_verdict(0.10, breakeven)

    print(
        f"OK — LTV/subscriber ${ltv_sub:.2f} (handbook ~$54), LTV/trial ${ltv_trial:.2f} "
        f"(handbook ~$20.50), break-even {breakeven:.2%} (handbook ~6.8%); "
        f"monotonicity and verdict-direction checks hold"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-check", action="store_true", help="run the built-in self-check and exit")
    parser.add_argument("--price", type=float, help="annual subscription price, $")
    parser.add_argument("--commission", type=float, help="Apple's commission rate, e.g. 0.15")
    parser.add_argument("--retention", type=float, help="year-over-year renewal rate, e.g. 0.221")
    parser.add_argument("--trial-to-paid-cvr", type=float, help="share of trial starters who convert to paid")
    parser.add_argument("--cpi", type=float, help="observed cost per install, $")
    parser.add_argument(
        "--observed-trial-rate",
        type=float,
        default=None,
        help="measured share of downloads that start a trial (trial_starts / downloads); optional",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_check:
        self_check()
        return 0

    required = ["price", "commission", "retention", "trial_to_paid_cvr", "cpi"]
    missing = [f"--{name.replace('_', '-')}" for name in required if getattr(args, name) is None]
    if missing:
        parser.error(f"missing required arguments: {', '.join(missing)}")

    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
