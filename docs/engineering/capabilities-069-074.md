# ASAI capabilities 069–074

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-069 — Strategy performance tracking
- Purpose: Produce a traceable, paper-only paper performance series; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.performancetracker`; class `PerformanceTracker`; function signature `aggregate(request: PerformanceRequest, *, actor_id: UUID) -> PaperperformanceseriesResult`.
- Contract: Input `PerformanceRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategyPerformanceTrackingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `strategy_performance_series, strategy_performance_point` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `BacktestRepository` is read-only; `audit.EventWriter` may append `StrategyPerformanceTrackingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for mixed currencies or incomplete periods; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) live-labelled run is excluded. (2) missing session yields a gap flag.
- Status: Planned.

### ASAI-070 — Strategy deployment control
- Purpose: Produce a traceable, paper-only paper simulation eligibility state; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.paper_deploymentcontroller`; class `PaperDeploymentController`; function signature `set_state(request: DeploymentRequest, *, actor_id: UUID) -> PapersimulationeligibilitystateResult`.
- Contract: Input `DeploymentRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategyDeploymentControlCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_strategy_deployment, deployment_transition` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `ApprovalService` is read-only; `audit.EventWriter` may append `StrategyDeploymentControlCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for non-paper environment or invalid transition; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) LIVE environment is denied. (2) DISABLED version cannot enqueue simulation.
- Status: Planned.

## PREDICTION

### ASAI-071 — Price-movement estimation
- Purpose: Produce a traceable, paper-only up/down/flat probabilities; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.pricemovementestimator`; class `PriceMovementEstimator`; function signature `estimate(request: FeatureSnapshot, *, actor_id: UUID) -> Up/Down/FlatprobabilitiesResult`.
- Contract: Input `FeatureSnapshot` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PriceMovementEstimationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `price_movement_estimate, estimate_feature_link` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `ModelRegistry` is read-only; `audit.EventWriter` may append `PriceMovementEstimationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for future feature or schema mismatch; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) future-dated feature is rejected. (2) probabilities summing .98 fail validation.
- Status: Planned.

### ASAI-072 — Trend forecasting
- Purpose: Produce a traceable, paper-only horizon trend forecast; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.trendforecaster`; class `TrendForecaster`; function signature `forecast(request: FeatureSnapshot, *, actor_id: UUID) -> HorizontrendforecastResult`.
- Contract: Input `FeatureSnapshot` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `TrendForecastingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `trend_forecast, forecast_feature_link` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `ModelRegistry` is read-only; `audit.EventWriter` may append `TrendForecastingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for out-of-card horizon or stale inputs; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) 500 bars outside 1-60 is rejected. (2) stale features emit no forecast.
- Status: Planned.

### ASAI-073 — Volatility forecasting
- Purpose: Produce a traceable, paper-only volatility interval forecast; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.volatilityforecaster`; class `VolatilityForecaster`; function signature `forecast(request: ReturnSeries, *, actor_id: UUID) -> VolatilityintervalforecastResult`.
- Contract: Input `ReturnSeries` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `VolatilityForecastingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `volatility_forecast, volatility_interval` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `ReturnSeriesRepository` is read-only; `audit.EventWriter` may append `VolatilityForecastingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for irregular cadence or nonconvergence; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) negative predicted variance fails. (2) 19 observations for min-20 is rejected.
- Status: Planned.

### ASAI-074 — Volume forecasting
- Purpose: Produce a traceable, paper-only p10/p50/p90 volume forecast; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.volumeforecaster`; class `VolumeForecaster`; function signature `forecast(request: VolumeSeries, *, actor_id: UUID) -> P10/P50/P90VolumeforecastResult`.
- Contract: Input `VolumeSeries` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `VolumeForecastingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `volume_forecast, volume_quantile` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `VolumeRepository` is read-only; `audit.EventWriter` may append `VolumeForecastingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for negative volume or unknown calendar; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) negative volume is rejected. (2) p90 below p50 violates integrity.
- Status: Planned.

