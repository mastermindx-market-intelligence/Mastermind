# Financial X: affiliated account and interaction networks
**As of:** 2026-10-30
**Status:** selected public-source first pass, not an exhaustive X interaction dataset
**Scope:** commercial and social affiliation, not just fake/bot accounts. No control or payment allegation solely from repost behavior.

## Corrected task

The inclusion criterion is observed affiliation: meaningful repeated reposts, comments/replies, quotes, brand endorsement, shared promotional destinations, creator content distribution, or an investor/portfolio relationship. A company-run channel is only one possible explanation; employee, host, independent affiliate, investor, customer and creator are separately legitimate relationship classes.

For each edge, keep three questions independent:
1. OBSERVATION: What account did what to which account, where and when?
2. AFFILIATION: Does this support a social, commercial, product, portfolio or editorial relationship?
3. CONTROL: Is the account plausibly controlled by a company, by an independent creator, or undetermined?

## Cluster A — OpenMarket, Thanefield Capital, Percept and third-party creators

| Account relationship | Directly observed evidence | Bounded classification |
| --- | --- | --- |
| @ThanefieldCap -> @ThanefieldRes | Thanefield Capital X profile explicitly names @ThanefieldRes as its market-research account. | Claimed company research arm. Historical snapshot; current handle continuity not independently authenticated. |
| Thanefield Capital -> Kiyotaka / OpenMarket | [Official portfolio](https://thanefield.capital/portfolio/) names a "Next-gen crypto market intelligence platform" illustrated with a Kiyotaka_260px.svg asset. [Capital X archive](https://mobile.twstalker.com/ThanefieldCap) shows **at least 11 distinct** reposted Kiyotaka/OpenMarket posts over its visible, multi-year history. | First-party portfolio relationship plus sustained repost affinity. Equity stake, legal control and editorial access not established. |
| @ThanefieldRes -> @openmarket_raw | @openmarket_raw announced "Thanefield Research is now OpenMarket Raw" and that @openmarket_xyz remains the official channel. | Self-identified predecessor publication/brand transition. Same X numeric user ID or legal transfer not verified. |
| @openmarket_xyz <-> @openmarket_raw | OpenMarket main account explicitly endorsed Raw; main also reposted its chart analysis. Raw's timeline repeatedly reposts the main brand's product updates. | Strong, **acknowledged secondary publishing channel**. Company-controlled editorial orbit plausible; actual X administrator unknown. |
| @percept_labs -> @openmarket_xyz | [Percept archive](https://twstalker.com/percept_labs) shows **at least six DISTINCT underlying OpenMarket product posts** marked as retweeted. The visible source spans multiple releases and is not a complete 30-day feed. | Strong recurring cross-promotion. |
| @openmarket_xyz -> @percept_labs | OpenMarket's [X post visible in archive](https://mobile.twstalker.com/ThanefieldCap) directs charting developers to @percept_labs; another archive shows it repost Percept's TitanCharts copy. | Reciprocal product affiliation, not just generic topic overlap. |
| Trontal Group engineer -> Percept and Kiyotaka | [First-person career site](https://russellkong.com/) reports work on Percept enterprise charts and previously Kiyotaka trading platform while employed at Trontal Group. | Strong self-reported shared engineering environment; the current capital/ownership relationship between Percept and OpenMarket is unknown. |
| @ThanefieldCap -> @thalamus_xyz | Archived retweet of Thalamus prediction-market launch. [OpenMarket Google Play](https://play.google.com/store/apps/details?id=xyz.openmarket.app) names Thalamus Technologies, Inc. as the app publisher. | Portfolio/related-business *lead*. Similar branding is not proof that the @thalamus_xyz account and legal publisher are same corporate entity. |
| @ThanefieldCap -> @tread_fi | Thanefield publicly states it invested in Tread.fi and reposts its announcements. | Directly stated investor/portfolio link, not common operations. |
| @ThanefieldCap -> @SynopticCom and @attentiondotme | Multiple reposts in historical archive; Synoptic also listed in firm's official portfolio. | Portfolio/promotional affinity; no account ownership transfer shown. |
| @openmarket_xyz <-> @Luckshuryy | Main OpenMarket and OpenMarket Raw amplify Luckshury's free footprint guide and free layouts; creator states that OpenMarket is his charting terminal. | Repeated creator collaboration/endorsement; likely independent subject to unverified economics. |
| @openmarket_xyz <-> @backquant | Back says he ported TradingView invite-only scripts to OpenMarket's paid marketplace; official OpenMarket reposts and says it handles marketplace billing. | Real content-marketplace commercial link; account ownership not shown. |
| @openmarket_xyz <-> @Trader_Leumas | Brand reposts an independent charting testimonial. | Product-user amplification, any compensation unknown. |
| @openmarket_xyz -> Tisiphone | Brand credits this script creator in at least two distinct public launch posts. | Community creator spotlight; no verified current X handle or paid contract. |
| @SPXVIX -> OpenMarket | October 28 options tutorial promotes tagged link https://openmarket.xyz/?ref=SPXVIX. | Referral-bearing creator, commission unknown; not evidence of ownership. |
| @ToneVays -> OpenMarket, GoCharting, TradingView | Promotes links to competing charting products, says he has received TradingView affiliate income over years, and markets separately created indicators. | Cross-provider independent creator is a strong alternative to one-company-controlled account. |

### Repeated interaction coverage

The above **11** and **6** are *lower-bound counts of distinct underlying posts* in **specific visible indexed snapshots**. They are NOT complete number-of-retweet events in the last 30 days, not all-post shares, and not unique post dates in a uniform window. Mirror content may be stale or incomplete, and repost event timestamps are usually absent. A single repost copied on five mirrors must count once.

### OpenMarket affiliation conclusion

- **High observed affinity, plausible official publishing:** @openmarket_xyz and @openmarket_raw because the main account **explicitly endorsed** a formerly Thanefield-branded research channel.
- **High business linkage, corporate control unresolved:** Thanefield Capital portfolio listing and public media history; Percept mutual product promotion and shared Trontal-linked engineering.
- **Commercial or editorial but plausibly independent:** @SPXVIX, @ToneVays, @Luckshuryy, @backquant. Tone Vays promoting multiple competing platforms is a valuable independence counterexample.
- **Weaker satellite relation:** Thalamus as related product / shared public publisher name; no direct account administration proof.

**Core archive evidence:** [Thanefield Capital X](https://mobile.twstalker.com/ThanefieldCap), [OpenMarket X](https://ww1.twstalker.com/openmarket_xyz), [Percept X](https://twstalker.com/percept_labs), [OpenMarket Raw X](https://ww1.twstalker.com/openmarket_raw), [Thanefield portfolio](https://thanefield.capital/portfolio/), [engineer's first-person portfolio](https://russellkong.com/), [Google Play](https://play.google.com/store/apps/details?id=xyz.openmarket.app).

## Cluster B — Unusual Whales, hosts, third-party business and tastytrade

| Edge | Evidence | Relationship interpretation |
| --- | --- | --- |
| @unusual_whales -> @WhaleWatch_UW | Main brand repeatedly promotes WhaleWatch show and clips. | Branded show content. |
| @WhaleWatch_UW <-> @NicholasFNS | Nicholas self-identifies as UW media host, interacts with show and its cohost and reposts company material. | Public host affiliation, exact employment not proven. |
| @WhaleWatch_UW <-> @AnthonySandford | Anthony self-identifies as co-host and consistently publishes tools/trading examples. | Host/content partner, private account ownership unknown. |
| @NicholasFNS <-> @AnthonySandford | Mutual discussions, replies, show references and cross-promoted clips on indexed feeds. | High social/professional overlap beyond isolated mention. |
| @AnthonySandford -> Unusual Whales | Own referral/10% discount code "asandfordx"; advertises his separately priced Stock Hub community. | Affiliated referral creator with distinct monetization. |
| Unusual Whales -> tastytrade | Main brand's posted disclosure explicitly says tastytrade compensates Unusual Whales under a marketing agreement; Monday show sponsor code "UNUSUALWHALES". Disclosure says parties remain independent. | **Direct documented paid sponsorship**, not shared company ownership. |
| @NicholasFNS -> @Ryan__Rigg | Visible reposts of Ryan's market observations; reciprocal show-related chatter. | Outer social ring ONLY. No contract inferred. |

Sources: [Official Unusual Whales timeline](https://www.sotwe.com/unusual_whales), [Nicholas timeline](https://twstalker.com/NicholasFNS), [Anthony Sandford timeline](https://www.sotwe.com/AnthonySandford?lang=en), [first-party company page](https://unusualwhales.com/about).

## Cluster C — Similar named trader accounts: caution against over-attribution

An exploratory search identifies distinct near-handle profiles that **repost the same original trader** and reuse older account description copy:

- Established public analyst: @Jake__Wujastyk, subscription currently advertised around $20/month.
- @Jake__Wujatsky: old $14/month promotional biography; an indexed timeline shows many reposts of genuine Jake.
- @Jaike__Wujastk: similar old $14/month biography, dominated by reposts of genuine Jake in mirror sample.
- @Jake___W and @00Jake_Wujastyk: other near-name accounts with many genuine Jake reposts or professional-copy similarities.

Sources: [genuine analyst](https://www.sotwe.com/Jake__Wujastyk), [lookalike 1](https://www.twstalker.com/Jake__Wujatsky), [lookalike 2](https://www.twstalker.com/Jaike__Wujastk), [lookalike 3](https://d46rckpsl2ks7laj5lfg.twstalker.com/Jake___W), [lookalike 4](https://ww.twstalker.com/00Jake_Wujastyk).

**Classification: unverified lookalike / one-way repost affinity.** These accounts could be impersonators, fan/archive pages, independent entrepreneurs, or authorized side accounts. There is no evidence the genuine analyst or charting brands operate or control them. Similar bios are not authorization evidence. Do not publish claims of crime or fabricated engagement on this basis.

## Revised network analysis method

An investigative edge is one **inspectable** event with a date, source, type, source account and target. Suggested classes: REPOST, QUOTE, REPLY, MENTION, BRAND_ACKNOWLEDGMENT, AFFILIATE_LINK, CROSSES_BRANDS, HOST, SPONSOR, PORTFOLIO, SHARED_ENGINEERING, CLAIMED_REBRAND. Include indirect and unlabeled ties, but never merge business affiliation into account ownership.

1. For a chosen 30-day interval, obtain X-permitted account posts / engagement exports including original post ID, author ID, repost/quote/reply target, created_at UTC, normalized text hash, outbound URL and expanded referral token. Keep source coverage and crawl time.
2. Deduplicate by canonical post ID, not by mirrored page URL. Normalize renamed handles against stable account IDs where possible.
3. Produce directed counts per edge type, reciprocal counts, distinct original post counts, shared audiences/overlapping promo targets, post-time cross-correlation, and similarity against each participant's own normal market-posting baseline.
4. Evaluate repeated *interaction density*, but do not treat being in a network or talking about the same breaking stock as evidence of control. Use denominators and matching non-promotional comparison accounts.
5. Separately assess commercial affiliation (ref link, marketplace, disclosure, mutual acknowledgment), editorial affiliation and ultimate control (verified legal/corporate/administrative evidence).
6. Distinguish official company-controlled publishing from freelance creators, legitimate community programs, undisclosed incentives, unauthorized impersonators and unknown third-party activity.

### Sampling priority

P1: OpenMarket+Thanefield+Percept, then OpenMarket creator/affiliate outer ring; P2: Unusual Whales with tastytrade sponsorship and cohost network; P3: a Moomoo campaign vs ordinary posts as an essential incentive-campaign control; P4: earlier StockSelectAI/SpinOfDesk material only if new discriminative evidence appears.

## Boundaries

This is a first-pass, sourced social/business *graph*, not proof of synthetic engagement or a complete census of current X interaction frequency. Some archived X timelines are from different crawl dates, and retweet event timestamps often are not exposed. Public operator identity, commercial terms, and shared login control remain unknown for many edges. No private communications, phone numbers, or personally sensitive account metadata included.


## 2026-10-30 scope correction: two identifiable Equity Edge follow networks

See the dedicated [Equity Edge giveaway ring](equityedge_affiliate_giveaway_ring.md) for **22 selected originating accounts** with campaign rules requiring the central trio **@EquityEdgeUK + @Danieltrades + @berkayglife** and **13 selected originating accounts** requiring **@EquityEdgeUK + @EquitySpace1**. These are samples of distinct handles in indexed X excerpts, **not complete 30-day interaction-event totals or distinct proven human owners**, and at least one creator (@skyshark0) participates in both hubs.

- The first hub has a declared **company co-founder** (@berkayglife), **head of affiliate marketing** (@Danieltrades, self-declared, founder-reposted), and public firm affiliate terms advertising **30%** commission.
- The second hub is notable because **@EquitySpace1 calls itself merely "Prop Trader"** while substantially concentrating visible content on Equity Edge reposts and giveaways. It is a plausible company-managed/sponsored publication **candidate**, but there is no first-party statement or technical record that the firm actually owns the account.
- Promoters with codes **EFE50, TWO, DANIEL50, LOGAN50, DAVID50, MIRA50, TOPG10, FIDE** have observable commercial referral mechanisms. @everythingfxx has an October 24 **Paid partnership** label.
- Some outer-ring creators demonstrably advertise **multiple competing** prop firms (e.g., @skyshark0 → AlphaCapitalUK, @De_CaptainChart → NYSMarkets and THEFUNDEDWAY, @THE_SNR_SNIPER → Hola Prime/Blue Guardian, @New_owner1 → EraFunded/AquaFunded). This is evidence against assuming every promoter is controlled by one company.
- Several creator links are more than co-mentioned tags: **@deartrader__ reposts and replies to Emrik and Playmaker promotions**; **@mirngaprime reposts @Aeroonfx**; and **@EquitySpace1 reposts official Equity Edge announcements**. Still, rates of reciprocal comments/retweets are not quantified without complete X post IDs/timestamps.
- [Firm's giveaway/BOGO rules](https://equityedge.io/general/giveaway-accounts-bogo-offers): promotional account sizes are simulated trading capacity and accounts close after the first payout; do not characterize $50K giveaway as $50K cash.
- Sources and machine-readable **181 directed relationship edges** now in [typed network graph](interaccount_edges_first_pass.json). Graph edges include one per distinct **required-follow relationship** in selected contest posts, not each actual user follow/repost/like.

## TrendSpider founder and owned product channel

- [TrendSpider official social-media policy](https://trendspider.com/blog/trendspiders-policy-on-social-media-chart-posting-and-chart-requests/) specifically identifies personal founder account **@danushman** and sets separate conduct rules for corporate account @TrendSpider versus founder's trading posts; employees can post through corporate social accounts.
- [SignalStack official about page](https://signalstack.com/about/) states it is brought by TrendSpider; [@SignalStack's indexed profile](https://w.twstalker.com/SignalStack) says "A @TrendSpider company" and contains brand reposts.
- [TrendSpider company about page](https://trendspider.com/about/) identifies founder Daniel Ushman. His [public profile](https://x.noodl3.net/danushman) discusses multiple founder projects. This is a clear company/founder/product multi-account graph without grounds to label it a deceptive bot network.

## Highest-value unresolved cases

1. **@EquitySpace1:** Who commissions campaigns, and does a first-party brand channel explicitly acknowledge its control? Its currently available promotional history is strongly aligned with Equity Edge but insufficient for ownership.
2. **OpenMarket historical research migration:** Can the numeric X account ID or official company document confirm whether historical @ThanefieldRes became @openmarket_raw on the same account? Directly announced affiliation is already sufficient to rank it as a related publisher.
3. **Actual interaction density:** Obtain permitted X 30-day post export and timestamps for selected core and outer-ring accounts. Compute per-pair repost/reply/quote counts and reciprocal proportions and compare to account-level baseline. Do not infer a rate from archived feed snippets.


## Graph audit and measured versus inferred edges

The extended [machine-readable edge graph](interaccount_edges_first_pass.json) currently contains **181 typed relationship edges, 98 account/company/product label nodes, and 77 cited public source URLs**, distributed into five connected components of sizes **61** (Equity Edge), **22** (OpenMarket/Thanefield/Percept), **7** (Unusual Whales/tastytrade), **5** (Jake near-handle lookalikes), and **3** (TrendSpider/SignalStack). Seven public account/company alias edges were added so otherwise split subgraphs correctly represent the same named business, without implying shared administration. This is a relational evidence map, **not** a time-normalized centrality score or a census of distinct real-world people.

The required-follow giveaway instructions dominate the graph's raw edge count: each Hub-A originator contributes 3 public contest recipient relationships, and each Hub-B originator 2. Additional categories include explicit business and affiliate connections, profile-declared roles, public reply/repost observations, and a paid brokerage marketing agreement. The two-count distinction is essential before calling an account "highly connected" versus "frequently engaged with."

New cross-brand creator connections are explicit in [@AfaaqFx indexed posts](https://ww.twstalker.com/AfaaqFx) and [@DaCryptoSheikh indexed posts](https://w.twstalker.com/DaCryptoSheikh): Equity Edge contests, AquaFunded, FundedNext/OrionFunded or FundingTraders referrals; each account operates in **multiple company marketing circles**, making a single-brand owned-account claim unsupported. Related 2026 X mirrors are snapshots with inconsistent relative dates and no validated post-event denominator.

See [the interactive network](account_network_interactive.html) to switch between **campaign directives** and **observed repost/reply** links. It permits visual inspection of topology but cannot generate missing timestamps, authenticate X numeric user IDs or prove common ownership.


## October 31 provenance upgrade: OpenMarket original-post control

The prior OpenMarket creator case can now be anchored to **two actual original status IDs** in a public, individually addressable archive, rather than relying only on a general profile snapshot:

- **@SPXVIX, first long-form launch thread:** [status `2115570292106170818`](https://teapaw.org/SPXVIX/status/2115570292106170818) → Twitter Snowflake-derived **2026-10-28 22:23:57.690 UTC**. The indexed permalink independently prints **Oct 28, 2026 10:23 PM UTC** and contains a personal detailed walkthrough of **51 OpenMarket options studies**, segmented into GEX, options positioning, skew, IV rank, dealer behavior, contract flows, etc., alongside the explicit `openmarket.xyz/?ref=SPXVIX` tracking parameter.
- **@SPXVIX follow-up / workflow wrap-up:** [status `2115571123433963601`](https://teapaw.org/SPXVIX/status/2115571123433963601) → derived **2026-10-28 22:27:15.894 UTC**. The permalink says **10:27 PM UTC**, reinforces the same walkthrough and carries the **same creator-specific referral token**. These are **two posts by one creator sharing one source referral relationship**, not two unrelated affiliates or evidence of two paid commissions.
- **Independent public index of official @openmarket_xyz profile:** [TwStalker archive](https://ww1.twstalker.com/openmarket_xyz) directly labels a repost of the **@backquant** creator listing technical indicators on its paid marketplace; a repost of a **@Luckshuryy** freely published order-flow/footprint tutorial; a repost/endorsement of **@openmarket_raw** following Raw’s own stated move from Thanefield Research; and a repost of **@percept_labs** product positioning. These correspond to **four distinguishable mechanisms**: content marketplace, educational creator, acknowledged secondary publisher, and adjacent chart infrastructure/product amplification. Their original company-post IDs and complete event histories were **not recovered** from this profile-level mirror.

**Evidence classification:** OpenMarket’s @SPXVIX promotion is **a date-grounded creator-authored, feature-specific educational thread with a disclosed attribution link**, rather than an observed short-form repetitive thread reply. Its exact economic arrangement is **still unknown**: referral tagging does not establish commission receipts, ownership of the author’s account, company control over the text, conversion rate, organic subscriber increase, or paid-placement disclosure adequacy. A creator could receive compensation, referral revenue, free access, or no economic benefit; no account-specific contract was inspected. The traceable launch also does **not** prove that every described options tool works in the production product without functional testing.

**Cross-niche comparator:** [the October 31 three-account prop-firm reply audit](affiliate_reply_seeding_claim_audit_2026-10-31.md) shows the opposite observed distribution form—short ranking-thread responses that reuse a company's payout claims and sometimes collapse the distinction between reviewed and self-reported figures. The contrast is useful for competitive marketing: **creator-authored original useful analysis versus repetitive comparison-thread brand insertion**. Neither form alone proves a bot network or unethical account control, and one verified long original thread does not establish overall quality, audience conversion or independence of other creators.

**Crawl caveat:** The indexed per-status teapaw archive contains the original post ID and UTC time, and the derived Snowflake UTC matches the displayed permalink time. That is stronger than undated partial TwStalker snapshots but still **not an authenticated first-party X API response**. Do not include these two IDs in an October 30-day interaction *rate* unless the sampling frame and other denominators are complete.
