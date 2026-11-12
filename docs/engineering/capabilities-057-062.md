# ASAI capabilities 057–062

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-057 — Momentum analysis
- Purpose: Produce a traceable, paper-only ROC/stochastic readings; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.momentumanalyzer`; class `MomentumAnalyzer`; function signature `calculate(request: BarSet, *, actor_id: UUID) -> Roc/StochasticreadingsResult`.
- Contract: Input `BarSet` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `MomentumAnalysisCompleted.v1`; no external API.
- Data and memory: PostgreSQL `momentum_reading, momentum_metric` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `MarketDataRepository` is read-only; `audit.EventWriter` may append `MomentumAnalysisCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for in-progress bars or invalid periods; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) an unfinished candle is rejected. (2) flat closes yield zero ROC safely.
- Status: Planned.

### ASAI-058 — Liquidity analysis
- Purpose: Produce a traceable, paper-only spread/depth/turnover metrics; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.liquidityanalyzer`; class `LiquidityAnalyzer`; function signature `assess(request: QuoteTradeSet, *, actor_id: UUID) -> Spread/Depth/TurnovermetricsResult`.
- Contract: Input `QuoteTradeSet` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `LiquidityAnalysisCompleted.v1`; no external API.
- Data and memory: PostgreSQL `liquidity_assessment, liquidity_metric` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `QuoteRepository` is read-only; `audit.EventWriter` may append `LiquidityAnalysisCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for crossed or sparse quotes; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) crossed quotes are excluded and flagged. (2) three prints returns INSUFFICIENT_DATA.
- Status: Planned.

### ASAI-059 — Cross-market analysis
- Purpose: Produce a traceable, paper-only correlation/beta report; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.crossmarketanalyzer`; class `CrossMarketAnalyzer`; function signature `compare(request: MarketSeriesSet, *, actor_id: UUID) -> Correlation/BetareportResult`.
- Contract: Input `MarketSeriesSet` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `CrossMarketAnalysisCompleted.v1`; no external API.
- Data and memory: PostgreSQL `cross_market_report, series_alignment` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `SeriesRepository` is read-only; `audit.EventWriter` may append `CrossMarketAnalysisCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for incompatible units or calendar alignment; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) price-to-yield comparison without transform is rejected. (2) only overlapping UTC observations are used.
- Status: Planned.

### ASAI-060 — Market-regime detection
- Purpose: Produce a traceable, paper-only regime probabilities; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.marketregimedetector`; class `MarketRegimeDetector`; function signature `classify(request: FeatureSnapshot, *, actor_id: UUID) -> RegimeprobabilitiesResult`.
- Contract: Input `FeatureSnapshot` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `MarketRegimeDetectionCompleted.v1`; no external API.
- Data and memory: PostgreSQL `regime_assessment, regime_probability` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `FeatureSnapshotRepository` is read-only; `audit.EventWriter` may append `MarketRegimeDetectionCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for stale features or probability violation; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) probabilities totaling 1.02 are rejected. (2) stale features return UNKNOWN.
- Status: Planned.

## STRATEGY

### ASAI-061 — Strategy creation
- Purpose: Produce a traceable, paper-only immutable paper strategy draft; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.strategyfactory`; class `StrategyFactory`; function signature `create(request: StrategySpec, *, actor_id: UUID) -> ImmutablepaperstrategydraftResult`.
- Contract: Input `StrategySpec` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategyCreationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `strategy, strategy_version, strategy_rule` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `UniverseRepository` is read-only; `audit.EventWriter` may append `StrategyCreationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unsafe DSL or unknown universe; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) submit_order DSL verb is rejected. (2) duplicate normalized owner/name conflicts.
- Status: Planned.

### ASAI-062 — Strategy classification
- Purpose: Produce a traceable, paper-only taxonomy labels and rationale; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.strategyclassifier`; class `StrategyClassifier`; function signature `classify(request: StrategyVersion, *, actor_id: UUID) -> TaxonomylabelsandrationaleResult`.
- Contract: Input `StrategyVersion` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategyClassificationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `strategy_classification, classification_label` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `StrategyRepository` is read-only; `audit.EventWriter` may append `StrategyClassificationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unpublished taxonomy or unparsable rules; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) unpublished label is rejected. (2) unmatched strategy receives OTHER.
- Status: Planned.

