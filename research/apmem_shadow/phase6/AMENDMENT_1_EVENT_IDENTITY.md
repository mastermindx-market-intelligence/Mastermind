# Amendment 1: entry-family identity, before new event/payoff reads

The supplied charts show an RSI-MACD panel with bullish/bearish crossover markers while Golden Oracle Confluence is hidden. Those visible markers are not sufficient evidence that native G0 (StochRSI cross with oversold memory plus rising 2D RSI-MACD histogram) fired on the same dates.

Add a separately named `rsi_macd_3d_cross` research trigger: the native 3D RSI-MACD histogram crosses strictly above zero from a nonpositive prior completed bar, observed at the actual completed 3D close. It is an event, not three forward-filled board days. Compare it with G0; do not relabel it G0, T1 or T2. The same six predeclared context policies are applied to each family, while phase-neutral confirmation remains a distinct G0 challenger. Episode failure memory is calculated separately for each family. Any gate state on an unfinished bar remains provisional and is excluded from the closed-bar primary.

This addition follows inspection of the user-supplied screenshots and source semantics, before the new panel's event outcomes or policy performance have been read. MCD 2026 remains an exposed design case, excluded from aggregate predictive qualification. No current production detector, signal era or authority changes.
