# Commission 7: Evidence Lineage, Correlation & Independence Graph

## A. Executive conclusion  
Mastermind must build a formal **evidence lineage and independence framework** so that correlated signals cannot be double-counted. In practice this means: (1) Tracking each feature’s raw inputs and transformations (a provenance graph); (2) Organizing signals into *evidence families* or clusters by shared data origin or statistical overlap; (3) Identifying causal drivers and conditional independencies via domain knowledge or graphical models; and (4) Computing meta-features (e.g. factor exposures or canonical combinations) that isolate independent information.  In effect, highly correlated signals (e.g. price momentum, relative strength, breadth) should be grouped and treated as one underlying “belief,” not as multiple confirmatory votes.  

This capability is critical.  If ignored, the system may **overstate confidence** when many signals move together – the classic diversification illusion (holding five tech stocks is effectively one large-cap tech bet).  Correlation is dynamic and context-dependent, so static assumptions are dangerous.  Instead, Mastermind should leverage both domain taxonomies (e.g. sector, style, factor families) and quantitative analysis (correlation/PCA/CCA) to enforce orthogonality.  In summary, we recommend: instrumenting full feature provenance (e.g. using a metadata/lineage system); defining independence families (static and dynamic); calculating orthogonalized factors; and incorporating these into Portfolio V3. This work is high-priority (P0), as it underpins the reliability of Mastermind’s decision intelligence. 

## B. Current-state census  
**Existing features and code:** The Mastermind code base already ingests a rich set of signals – prices and breadth metrics, point-in-time (PIT) fundamentals, options flows, thematic indicators, ETF/fund data, news/macro context, etc.  An `earnings_expectation` pipeline uses Standardized Unexpected Earnings (SUE) and some estimate revisions.  Portfolio V3 architecture *specifies* evidence families and decision snapshots, but many pieces were marked *NOT_BUILT* in earlier releases. A recent static audit (at commit `d1594f3…`) showed no comprehensive feature lineage tracking – only periodic snapshots of "census" data, suggesting that real-time observability is incomplete. 

**Notable gaps:** The team has flagged several missing elements: (a) **Analyst revisions PIT series:** current fundamental lanes lack a fine-grained, timestamped history of analyst estimate revisions. (b) **Dynamic themes:** there is no canonical table for time-varying sub-theme assignments (signals about trends or categories that evolve). (c) **Flows data:** stock-level institutional flow histories (e.g. from 13F, internal fund flows) are immature. (d) **Independence families:** while the notion exists in spec, the actual grouping of features into “independence families” is incomplete. (e) **Data freshness:** the earlier census was months old, so automated lineage logging / freshness metrics are needed.  

We must verify which pipelines already capture feature provenance (e.g. if `portfolio/lenses.py` or `brain/research_desk.py` log dependencies) versus which are gaps. This census confirms that while Mastermind has abundant signals, it currently has *no integrated system to trace which data sources produce which features*, nor any mechanism to alert when correlated signals imply redundant evidence. These are central hypotheses to validate. 

## C. State-of-the-art research  
Modern AI/quant firms recognize the perils of treating correlated signals as independent evidence.  In **statistical modeling**, correlated predictors (multicollinearity) degrade performance; by contrast orthogonal (independent) features are ideal. IBM notes that *“multicollinearity denotes when independent variables…are correlated”* and that its opposite is *orthogonality*.  In other words, we should aim to project signals into orthogonal components.  

**Correlation ≠ independence:**  It’s well-known that “correlation does not imply causation”.  In probability terms, two signals $A,B$ are *conditionally independent* given context $C$ if $P(A|B,C)=P(A|C)$.  Graph-based causal models (Bayesian networks) formalize this: the graph’s separation implies probabilistic independence.  In practice, this means we should ask for each pair of features: do they share a common cause or is one simply a noisy version of the other? If so, they are not providing new “information.”  

**Dynamic, regime-dependent correlations:**  Finance researchers emphasize that correlations between signals or asset returns change with market state. For example, QuantNeuralEdge (Aug 2026) warns that correlation *“is not a number — it’s a process”* and can surge during crises.  Academic work also shows cross-correlations depend on time scale and volatility: financial signals “are neither scale-free nor amplitude-independent”. In short, signals that seem uncorrelated in calm times may collapse together under stress. Mastermind’s framework must therefore treat correlation as conditional and possibly compute *time-varying independence*.  

**Feature lineage systems:**  In machine learning, industry practice is emerging.  Feature-store products (e.g. Feast) integrate with lineage standards (OpenLineage) so teams can trace exactly *“where does this feature’s data come from?”* and *“which models depend on it?”*.  IBM likewise defines **data provenance** as “the historical record of data…detailing its origins”, distinct from data lineage which tracks transformations.  These systems automatically log, for each feature, the source table, transformation query, and as-of timestamps. Adopting a similar scheme would ensure every Mastermind feature includes metadata on raw inputs, calculation code, and timing – forming a graph where features are nodes and “depends-on” edges connect them.  

**Independent factors and orthogonalization:**  In portfolio research, sophisticated methods use canonical analysis to disentangle correlated signals.  For example, Firoozye et al. (2023) reframe a multivariate signal model using *Canonical Correlation Analysis (CCA)*.  Their method *“selects a set of uncorrelated managed portfolios through…CCA”*, effectively constructing orthogonal combinations of assets and signals that capture the independent drivers of return.  (PCA or independent component analysis are similar ideas.)  This suggests one can algorithmically derive independent projections of Mastermind’s features, grouping overlapping signals into common factors.  

In summary, the state-of-art dictates a hybrid solution: use **graphical lineage** to capture provenance (citing IBM/Feast practices), and use **statistical orthogonalization** to identify independent evidence dimensions (citing ML theory and CCA).  Both aspects are needed to avoid false confidence from redundant signals.  

## D. Source landscape  

| **Source**              | **Coverage**                               | **History**          | **Latency**           | **PIT quality**       | **Corrections**        | **Rights/Cost**    | **Best use**                                         |
|-------------------------|--------------------------------------------|----------------------|-----------------------|-----------------------|-----------------------|--------------------|------------------------------------------------------|
| Exchange Price Data     | Global equity/futures markets (tick data)  | Since 1980s          | Real-time (ms)        | Very high (time-stamped) | Rare (splits, reorgs) | Proprietary (high cost) | Core price/momentum signals, volatility              |
| IBES/Refinitiv Analyst  | Analyst estimates & revisions (global)     | 1970s–present        | Daily/nightly         | Moderate (estimates dated) | Yes (revisions)     | Proprietary (expensive) | Earnings expectations, SUE/forecast surprise signals |
| Fundamental Filings     | Public company 10-K/Q data (Compustat, EDGAR) | 1990s–present      | Quarterly (months lag)| Moderate (as-of filing)  | Yes (restatements)   | Open/Low (via SEC)     | Actual fundamentals, base-line factors              |
| Options Data            | US equity/options (OptionMetrics)          | 1990s–present        | Intraday/daily        | High (precise)        | Adjusted (splits)     | Proprietary          | Flow/volatility signals (skew, gamma exposure)       |
| ETF/Mutual Fund Flows   | Flows, holdings (Bloomberg, iShares)       | 2000s–present        | Daily/weekly updates  | Moderate              | Periodic restatements| Proprietary          | Institutional flow imbalance, thematic allocations   |
| News & Sentiment Data   | Global financial news/alerts               | 2000s–present        | Seconds–minutes       | Variable (timestamped) | Rare (errata)        | Proprietary          | Event signals, market sentiment, crowd factors       |
| Macro Indicators        | Economic series (FRED, OECD)               | 1940s–present        | Monthly/quarterly     | Moderate (release lag) | Revisions tracked    | Public/Open         | Regime/context indicators (inflation, rates)         |
| Internal Metadata Logs  | Mastermind DB tables and pipelines         | Current system snapshot | Seconds/minutes      | High (timestamped)    | N/A (track changes)  | Internal             | Provenance of features (lineage graph)               |

**Notes:** Each source must be time-aligned (point-in-time) when ingested. Data from exchanges and IBES has high time precision; filings/news have built-in delays and revisions. Provenance requires tracking `event_time` (occurrence) vs `as_of` (available time) vs `ingested_at`. Proprietary sources (price feeds, IBES, OptionMetrics) deliver rich data but at high cost/licensing; public sources (EDGAR, FRED) are free but slower. The best use column hints where each source adds evidence: e.g. price feeds for short-term market moves, IBES for earnings-related expectations, etc. 

## E. Canonical data model  
We propose a small set of **core tables** (or graph structures) to capture evidence lineage and independence: 

- **`Feature`**: Each row is a derived feature (signal). Key fields: `feature_id, name, description, owner`. Crucially, *lineage fields* like `source_table`, `source_fields`, `transform_script` (or function), and timestamps `(created_at, as_of_date)` record how it was computed. For PIT data, we include `effective_from`/`effective_to` to denote the intended valid period. 

- **`Source`**: Describes raw data sources: e.g. market data feed, IBES, EDGAR. Fields include `source_id, type (exchange, API, file), update_frequency, latency, data_owner`.

- **`FeatureDependency`**: A mapping table linking each `feature_id` to its direct inputs (could be other features or raw source fields). This implements the causal provenance graph: if feature F is computed from source fields or other features X and Y, we create rows (F → X), (F → Y).  These edges allow tracing a feature back to raw data. 

- **`EvidenceFamily`**: Defines manual or computed groups of related features. Fields: `family_id, name, description`. A junction table `FeatureFamily(feature_id,family_id)` assigns each feature to one or more families (e.g. “PriceTrend”, “Sentiment”, “MacroEconomic”). Initially these families can follow Portfolio V3 specs (e.g. separate equity alpha families vs macro vs flows). 

- **`CorrelationMetrics`**: A table of precomputed statistical relationships: e.g. `(feature_id_1, feature_id_2, correlation, last_computed_at, method)`.  This enables queries like “which features exceed correlation threshold 0.8 (in absolute value)?”.  

Temporal semantics: all tables should record *when* a feature or family definition was valid (point-in-time schema), so backtesting avoids using future family assignments.  

This data model is minimal: it preserves **feature ancestry** (via FeatureDependency) and **evidence groupings**, while allowing storage of computed metrics (CorrelationMetrics) and metadata. It can be implemented in a relational DB or graph store. (Feast/OpenLineage concepts align with this design.)  

## F. Derived intelligence  
From the canonical raw data and lineage model, Mastermind should compute these derived insights:

- **Feature ancestry/provenance**: For any feature, the full chain of raw inputs (via successive joins on `FeatureDependency`), so analysts can see *“this indicator came from X and Y tables, ultimately from stock prices and earnings”*. 

- **Evidence family overlap**: Using `CorrelationMetrics` or other statistics, identify when families overlap.  E.g. compute the principal components or canonical factors of a family’s features, to see if multiple signals collapse onto one latent factor.  

- **Orthogonal factors**: Apply dimensionality reduction (PCA/ICA/CCA) to groups of correlated features to extract independent components.  These new components become additional “features” that are mutually orthogonal. (Firoozye et al. use CCA to create uncorrelated portfolios.)  

- **Conditional information gain**: For each feature F and context C (e.g. market index level), compute how much new information F adds beyond C (e.g. via mutual information or improvement in target prediction).  If the gain is negligible, F is redundant given others.  

- **Family “independence score”**: A metric for each evidence family measuring internal redundancy (e.g. average pairwise correlation) and external overlap with other families.  

- **Temporal correlation tracking**: Time-varying correlation curves for feature pairs, to capture regime shifts (building on [52] and [53]). If correlations spike, trigger flags. 

These derived features/metrics should be updated regularly and stored (e.g. augment `CorrelationMetrics`) so that downstream models can query them.  Importantly, they quantify *“how independent”* a signal is, guiding the model’s confidence. 

## G. Mastermind integration map  
We envision the following flow: 

- **Producers**: Raw data ingestion pipelines (e.g. market data feeds, IBES snapshots, news crawlers) and feature-computation modules (e.g. Python scripts in `loop/`, `brain/`). 

- **Metadata/Lineage System** (new): Each feature-computation job will emit lineage events (similar to Feast + OpenLineage). For example, the pipeline that computes “5-day momentum” will log: Feature “Momentum5” ← price data table (symbol, 5d return) at time T. These events populate our `Feature`, `Source`, and `FeatureDependency` tables. 

- **Evidence Families Definition**: A design-time process (by data owners/researchers) will define initial static families (e.g. assign “Momentum5” to PriceTrend family). These definitions are stored in `EvidenceFamily`. Families can be refined dynamically by clustering analysis. 

- **Consumers**: The portfolio engine and ML models in Mastermind (e.g. in `portfolio/lenses.py`, `held_risk.py`, `brain/` modules) will use these artifacts.  Instead of blindly ingesting every signal, they will query “selected independent signals” – for example, take one representative per highly-correlated cluster.  Models might consume canonical factors (above) rather than raw correlated features.   Decider snapshots (`DecisionSnapshots` in Portfolio V3) will include the independence-grouped evidence passed to the strategy. 

Graphically: 
```
Raw Sources (Market, IBES, etc) 
    ↓ (data pipelines) 
Feature Generation (code modules) 
    ↓ emits lineage events 
Feature Lineage DB (Feature, Dependency, Family, CorrMetrics) 
    ↓ 
Aggregated Evidence (families, canonical factors) 
    ↓ 
Downstream Models/Portfolios 
```
This ensures all signals feed through a unified lineage/evidence plane, not side channels. 

## H. Empirical validation program  
We must prove that treating correlated signals properly improves performance or stability. Key steps: 

1. **Synthetic injection tests:** Introduce artificial features with known dependencies. For example, create Feature A = price momentum, Feature B = 2×(price momentum) + noise. A robust pipeline should flag A and B as redundant (high correlation) and only one should carry forward. This checks that the lineage graph correctly identifies overlapping evidence.

2. **Backtests with/without orthogonalization:** Run parallel simulations where the only difference is how we handle families. In one, use all raw signals; in another, collapse each correlated cluster into one (e.g. via PCA). Compare portfolio risk-adjusted returns and leverage. If double-counting was boosting apparent Sharpe, the “family-collapsed” run should be more realistic and stable out-of-sample. 

3. **Feature ablation tests:** For each evidence family, drop or replace individual signals and see how portfolio metrics change. If two signals are truly independent, removing one should degrade prediction; if redundant, removing it should have little effect. 

4. **Cross-validation of independence:** When building predictive models (e.g. for earnings or price), verify that selected features pass a conditional independence test. For instance, regress target on Family1 signals and Family2 signals separately vs together. Genuine independent families should both add unique variance. 

5. **Leakage checks:** Ensure that family assignments and correlation stats only use past data. For example, compute each feature’s correlation using only data available *up to* that date (rolling windows). Backtests must avoid using future covariance (or risk overfitting). 

6. **Falsifiers:** Identify ‘fool’s gold’ signals that seem independent but aren’t (e.g. two unrelated-looking features that both proxy market beta). Ensure methodology catches such hidden dependence (perhaps via residual analysis). 

Key metrics: true independent dimension count (e.g. effective rank of correlation matrix), incremental alpha added by each new “independent factor,” overfitting penalty in rolling-window retraining.   The validation program should emphasize *preserving only empirically orthogonal information* rather than assumptions.  

## I. Risks and failure modes  
- **Mis-grouping independent signals:**  Static families could erroneously merge distinct drivers, losing information. For example, grouping all “momentum” by past-1yr might mix short-term and long-term momentum which have different predictive structure. We must guard against overly coarse families.  

- **Overconfidence from residual correlation:**  Even after grouping, residual weak correlations remain. If models ignore this, they may still double-count minor overlapping info. 

- **Dynamic regime shifts:**  As noted, correlation patterns change with market stress. A family that was independent (orthogonal) in normal times may break down in a crash. We must monitor and potentially split families or reduce exposure dynamically. 

- **Leaked future information:** If provenance or family assignment uses future knowledge (e.g. grouping signals by how they ended up performing in hindsight), backtests will overstate gains. All grouping/clustering must be based solely on information available at each time. 

- **Vendor lock-in / rigidity:** Relying too heavily on a single tool (e.g. one vendor’s clustering) risks inflexibility. Also, black-box clustering might not align with economic understanding. Balancing automated clustering with human review is essential. 

- **False precision:** Presenting “feature X has 87% independent information” can be misleading. Correlation estimates have error bars. We should quantify uncertainty: e.g. confidence intervals on correlation or significance tests, and avoid hard cutoffs. 

- **Quality of raw data:** Upstream data errors (outliers, restatements) will propagate. If a source is noisy or later corrected, features depending on it may appear inconsistent. We need to version-control raw inputs and perhaps label features with data quality scores. 

- **Cost vs benefit:** Building and maintaining lineage metadata and clustering logic has overhead. We must ensure the added complexity yields real performance gains. Kill criteria (see below) will guard against over-engineering. 

## J. Build priority  
We recommend the following priorities: 

- **P0 (must-have):** Implement the basic lineage capture infrastructure. Every feature compute job should log its raw inputs and transformation (e.g. via OpenLineage or custom logging). Define a small set of initial evidence families (e.g. {PriceTrend, Earnings, Sentiment, Flows, Macro}). Compute feature correlations on a regular basis. Provide these to the Portfolio V3 engine so that, at minimum, highly-correlated signals within a family are not double-counted.

- **P1 (high):** Develop automated family clustering. Use statistical methods (PCA/CCA/hierarchical clustering) to refine families beyond the static list. Compute canonical orthogonal factors and make them available as features. Integrate conditional independence checks to split or merge families. Incorporate these into existing code (e.g. `brain/`, `portfolio/` modules) to adjust risk computations. 

- **P2 (medium):** Build user tools for exploration: e.g. a UI to visualize the evidence graph and correlations, or dashboards showing which signals were grouped at each date. Implement alerts for regime shifts (when correlation patterns change abruptly). Add provenance queries (e.g. “show all raw fields behind feature X”).

- **Defer:** Advanced ML interpretability (e.g. training an LLM to read feature-code comments and infer relationships) is out-of-scope now. Also, exotic unsupervised methods beyond PCA/CCA can wait until basic clustering is stable. 

- **Reject:** Do not try to invent one opaque “master evidence score” for each asset; we must preserve inspectable dimensions. Avoid chasing marginal signals that add only noise.  

## K. Proposed implementation phases  
1. **Metadata Instrumentation (Weeks 1–4):**  Embed lineage logging into data pipelines. For example, wrap each feature computation with a call that records its inputs and timestamp in the `Feature`/`FeatureDependency` tables. Validate by cross-checking logs with known dependencies (e.g. momentum feature draws from price tables). 

2. **Baseline Family Definition (Weeks 3–6):**  Workshop with stakeholders to define an initial taxonomy of evidence families (using Portfolio V3 notes). Populate the `EvidenceFamily` table accordingly. Tag existing features into families.  

3. **Correlation Analysis (Weeks 5–8):**  Compute pairwise correlations of all signals (daily cross-section or rolling time series). Populate `CorrelationMetrics`. Identify clusters with a threshold (e.g. |ρ|>0.8) and compare to static families – adjust groups if needed. 

4. **Orthogonal Features (Weeks 7–10):**  Perform PCA/CCA within each family to extract principal components. Add the top components as new features (with proper PIT handling). Test that these explain most variance. 

5. **Portfolio Integration (Weeks 9–12):**  Modify Portfolio V3 assembly so that it draws at most one feature per strongly-correlated cluster. For example, require that decision snapshots pick representative features or canonical composites from each family. Backtest to verify decisions change as expected (we should see a reduction in apparent diversification). 

6. **Validation & Refinement (Weeks 11–16):**  Run the validation tests (see section H). Iterate on family definitions, clustering algorithms, threshold levels. Deploy monitoring of evidence overlap (e.g. how often are multiple features from same cluster selected together) to detect gaps. 

This phased plan ensures quick wins (lineage capture, simple blocking of exact duplicates) before tackling the full complexity of statistical clustering. 

## L. Exact implementation handoff  
**Implementation Commission 8 (Evidence Independence Engine)**: Upon acceptance of this research, the engineering team should be tasked as follows:

- **Task:** Build an **Evidence Independence Engine** that integrates with Mastermind’s data pipelines and modeling code. This engine must: (a) Record full data provenance for each feature (source tables, transformations, timestamps); (b) Maintain an *Evidence Lineage Graph* (as per the schema above); (c) Group signals into evidence families, initially from static definitions, later refined by correlation analysis; (d) Compute and store correlation and orthogonality metrics (e.g. principal components) for each family; (e) Expose an API or interface so that portfolio allocation and models consume only independent evidence dimensions (e.g. one per cluster). 

- **Requirements:** Use point-in-time data correctly (no peeking). Update lineage and correlation metrics daily. Provide backward compatibility (older snapshots of the graph). Ensure the system logs any violation of independence assumptions (e.g. unexpected correlation spikes). 

- **Handoff deliverables:** A running service or module that fills the proposed tables (Feature, Dependency, Family, CorrelationMetrics). Updated model/strategy code that queries this metadata instead of raw signals. Documentation of new APIs and schema. A set of regression tests confirming no future data leakage.  

This final handoff should be implemented by the engineering team with the leadership of the data platform team, under the oversight of the Chief Data Officer. The expected outcome is an institutional-grade evidence-tracking layer that guarantees Mastermind never double-counts correlated signals. 

**Priority:** P0 (execute immediately after research acceptance).