# Amendment 4: observable provisional slow context

The MCD case distinguishes an October 12 early dot while the last completed 2W histogram was still deteriorating from a later October 20 cross with completed slow improvement. A present-day chart's unfinished higher-timeframe bar must not be used to backdate that improvement.

Add a bounded, case-guided measurement test: on each already defined event date, compute the native RSI-MACD value of the current 2W/monthly bar AS IF it ended at that session, using only that exact price prefix. Carry both `observed_at` and the later scheduled period end, and mark the value provisional whenever the scheduled end exceeds the observation date. The prior completed-bar features remain unchanged. Compare the provisional histogram with the preceding completed histogram, and later record whether that sign persisted to the actual period-end observation. This persistence label is evaluated only after period maturity; it cannot participate in the earlier entry decision.

This does not automatically admit intrabar entries, alter G0, change a closed-bar gate or claim that every provisional turn will survive. It quantifies the information/latency tradeoff that would otherwise be hidden by a completed chart. Fixed comparisons: raw event, completed-slow-plus-peer context, and provisional-slow-plus-peer context, on the same event tape with identical next-close fills and costs. Exposed MCD 2026 remains excluded from aggregate validation. No threshold optimization or native chart-phase-parity claim.

At amendment time the supplied chart, MCD observable feature checkpoint, and its June path outcomes were inspected. Primary cohort-policy/model aggregate results remain unread. This is exploratory development, not an independent holdout.
