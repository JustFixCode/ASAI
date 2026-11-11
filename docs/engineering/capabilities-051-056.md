# ASAI capabilities 051–056

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-051 — Technical analysis
- Purpose: Produce a traceable, paper-only indicator readings; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.technicalanalyzer`; class `TechnicalAnalyzer`; function signature `analyze(request: BarSet, *, actor_id: UUID) -> IndicatorreadingsResult`.
- Contract: Input `BarSet` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `TechnicalAnalysisCompleted.v1`; no external API.
- Data and memory: PostgreSQL `technical_indicator_run, technical_indicator_value` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `MarketDataRepository` is read-only; `audit.EventWriter` may append `TechnicalAnalysisCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for missing bars or invalid windows; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) 13 bars for RSI-14 is rejected. (2) a corrected bar creates a new run.
- Status: Planned.

### ASAI-052 — Fundamental analysis
- Purpose: Produce a traceable, paper-only factor assessment; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.fundamentalanalyzer`; class `FundamentalAnalyzer`; function signature `assess(request: FilingSet, *, actor_id: UUID) -> FactorassessmentResult`.
- Contract: Input `FilingSet` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `FundamentalAnalysisCompleted.v1`; no external API.
- Data and memory: PostgreSQL `fundamental_assessment, fundamental_factor` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `FilingRepository` is read-only; `audit.EventWriter` may append `FundamentalAnalysisCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for conflicting filings or mixed units; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) millions mixed with dollars is rejected. (2) a restatement retains both source accessions.
- Status: Planned.

### ASAI-053 — Sentiment analysis
- Purpose: Produce a traceable, paper-only entity-weighted sentiment; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.sentimentanalyzer`; class `SentimentAnalyzer`; function signature `score(request: DocumentSet, *, actor_id: UUID) -> EntityWeightedsentimentresult`.
- Contract: Input `DocumentSet` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `SentimentAnalysisCompleted.v1`; no external API.
- Data and memory: PostgreSQL `sentiment_document, sentiment_score` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `NewsRepository` is read-only; `audit.EventWriter` may append `SentimentAnalysisCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unlicensed or ambiguous text; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) syndicated copies deduplicate by hash. (2) two equally likely entities are flagged ambiguous.
- Status: Planned.

### ASAI-054 — Trend identification
- Purpose: Produce a traceable, paper-only trend label and confidence; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.trendidentifier`; class `TrendIdentifier`; function signature `identify(request: TechnicalSnapshot, *, actor_id: UUID) -> TrendlabelandconfidenceResult`.
- Contract: Input `TechnicalSnapshot` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `TrendIdentificationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `trend_label, trend_evidence` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `TechnicalSnapshotRepository` is read-only; `audit.EventWriter` may append `TrendIdentificationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for stale or mixed-frequency indicators; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) daily/weekly inputs are rejected. (2) stale indicators return INSUFFICIENT_DATA.
- Status: Planned.

### ASAI-055 — Support and resistance detection
- Purpose: Produce a traceable, paper-only scored price levels; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.supportresistancedetector`; class `SupportResistanceDetector`; function signature `detect(request: BarSet, *, actor_id: UUID) -> ScoredpricelevelsResult`.
- Contract: Input `BarSet` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `SupportAndResistanceDetectionCompleted.v1`; no external API.
- Data and memory: PostgreSQL `price_level_set, price_level` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `MarketDataRepository` is read-only; `audit.EventWriter` may append `SupportAndResistanceDetectionCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for nonpositive prices or invalid tolerance; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) zero adjusted price is rejected. (2) nearby highs within tolerance cluster once.
- Status: Planned.

### ASAI-056 — Pattern recognition
- Purpose: Produce a traceable, paper-only pattern findings and pivots; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.analysis.patternrecognizer`; class `PatternRecognizer`; function signature `recognize(request: BarSet, *, actor_id: UUID) -> PatternfindingsandpivotsResult`.
- Contract: Input `BarSet` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PatternRecognitionCompleted.v1`; no external API.
- Data and memory: PostgreSQL `pattern_finding, pattern_pivot` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `MarketDataRepository` is read-only; `audit.EventWriter` may append `PatternRecognitionCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unknown catalog or low fit; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) unpublished catalog version is rejected. (2) insufficient pivots emit no pattern.
- Status: Planned.

