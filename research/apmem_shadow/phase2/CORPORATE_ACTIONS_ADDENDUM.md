# Corporate-action qualification addendum

Recorded after the six nonsplit panels completed and before fitting the remaining five ordinary-split panels. This changes no model, target, evaluation horizon, cost, exposure rule, or performance threshold. It repairs a data-basis admission dependency; all original snapshots remain immutable.

State Street's November 20, 2025 issuer announcement identifies 2:1 splits effective December 5, 2025 for XLB, XLE, XLK, XLU and XLY. Their current Yahoo OHLC histories are already in constant post-split share units even with auto_adjust=False. On 1,346-1,347 overlapping sessions, independent Massive raw closes multiplied by 0.5 before the event and 1 afterward agree within 6e-8 relative error; open/high/low discrepancies are below 0.001. The event-adjacent dates are explicitly checked. Yahoo adjustment-factor changes imply the reported cash distributions within $0.00004; this is internal distribution-unit consistency, not an independent vendor cash-distribution audit.

The narrow adapter admits only these exact instruments and the single declared event after checking independent overlap (>=500 sessions, >=20 on each side), event dates, close relative error <=1e-5, other OHLC error <=0.001, distribution-factor residual <=$0.0001 and nondistribution factor change <=1e-5. It does not modify price or distribution values. It preserves the original event in source_stock_splits and projects stock_splits=0 to mean no UNAPPLIED event remains in this constant-unit panel. Original/input/output hashes and the qualification receipt are retained. This is a current-vintage ratio-preserving research basis, not historical first-availability proof.

XLF is NOT admitted through this adapter. Its 2016 ratio is associated with an in-kind XLRE distribution and index reconstitution, as described in the issuer's SEC supplement. Treating it as an ordinary share split would silently redefine the economic holding. Its original planned full-window transfer remains unqualified; it is not dropped for poor performance. No XLF model outcome was computed.

Issuer split reference: https://investors.statestreet.com/investor-news-events/press-releases/news-details/2025/State-Street-Investment-Management-Announces-Share-Splits-for-Five-Select-Sector-SPDR-ETFs/default.aspx
XLF source: https://www.sec.gov/Archives/edgar/data/1064641/000119312516719418/R2.htm

After these five unretuned runs, multiple-comparison adjustment is recomputed across the complete eleven-asset family; the earlier six-asset adjustment is retained as an intermediate diagnostic, not selected as the final family.
