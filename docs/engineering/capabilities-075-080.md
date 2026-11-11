# ASAI capabilities 075–080

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-075 — Probability scoring
- Purpose: Produce a traceable, paper-only calibrated probability score; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.probabilityscorer`; class `ProbabilityScorer`; function signature `score(request: ClassDistribution, *, actor_id: UUID) -> CalibratedprobabilityscoreResult`.
- Contract: Input `ClassDistribution` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `ProbabilityScoringCompleted.v1`; no external API.
- Data and memory: PostgreSQL `probability_score, score_source_link` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `CalibrationRegistry` is read-only; `audit.EventWriter` may append `ProbabilityScoringCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for class mismatch or expired calibrator; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) binary calibrator rejects three classes. (2) 1.01 probability is rejected.
- Status: Planned.

### ASAI-076 — Prediction tracking
- Purpose: Produce a traceable, paper-only matured outcome linkage; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.predictiontracker`; class `PredictionTracker`; function signature `register_outcome(request: ObservedOutcome, *, actor_id: UUID) -> MaturedoutcomelinkageResult`.
- Contract: Input `ObservedOutcome` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PredictionTrackingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `prediction_tracking, observed_outcome` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `OutcomeRepository` is read-only; `audit.EventWriter` may append `PredictionTrackingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for premature or duplicate outcome; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) 5-day forecast cannot score on day 2. (2) duplicate feed outcome conflicts.
- Status: Planned.

### ASAI-077 — Prediction evaluation
- Purpose: Produce a traceable, paper-only Brier/MAE/accuracy report; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.predictionevaluator`; class `PredictionEvaluator`; function signature `evaluate(request: EvaluationRequest, *, actor_id: UUID) -> Brier/Mae/AccuracyreportResult`.
- Contract: Input `EvaluationRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PredictionEvaluationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `prediction_evaluation, evaluation_member` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `TrackingRepository` is read-only; `audit.EventWriter` may append `PredictionEvaluationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unknown metric or no maturity; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) untracked predictions fail Brier evaluation. (2) missing outcome is disclosed and excluded.
- Status: Planned.

### ASAI-078 — Forecast uncertainty
- Purpose: Produce a traceable, paper-only interval and entropy report; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.uncertaintyquantifier`; class `UncertaintyQuantifier`; function signature `quantify(request: Prediction, *, actor_id: UUID) -> IntervalandentropyreportResult`.
- Contract: Input `Prediction` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `ForecastUncertaintyCompleted.v1`; no external API.
- Data and memory: PostgreSQL `forecast_uncertainty, uncertainty_interval` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `UncertaintyMethodRegistry` is read-only; `audit.EventWriter` may append `ForecastUncertaintyCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for incompatible method or inverted bounds; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) point-only model returns unavailable intervals. (2) lower above upper is rejected.
- Status: Planned.

### ASAI-079 — Model comparison
- Purpose: Produce a traceable, paper-only common-cohort model ranking; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.modelcomparator`; class `ModelComparator`; function signature `compare(request: ModelComparisonRequest, *, actor_id: UUID) -> CommonCohortmodelrankingresult`.
- Contract: Input `ModelComparisonRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `ModelComparisonCompleted.v1`; no external API.
- Data and memory: PostgreSQL `model_comparison, model_comparison_member` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `EvaluationRepository` is read-only; `audit.EventWriter` may append `ModelComparisonCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for different schema or incomplete cohort; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) daily model rejects intraday schema. (2) 10% missing cohort coverage excludes model.
- Status: Planned.

### ASAI-080 — Prediction calibration
- Purpose: Produce a traceable, paper-only held-out calibration artifact; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.prediction.calibrationtrainer`; class `CalibrationTrainer`; function signature `fit(request: CalibrationCohort, *, actor_id: UUID) -> HeldOutcalibrationartifactresult`.
- Contract: Input `CalibrationCohort` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PredictionCalibrationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `calibration_artifact, calibration_bin` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `ModelApprovalService` is read-only; `audit.EventWriter` may append `PredictionCalibrationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for training overlap or degraded reliability; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) training cohort is rejected. (2) worse Brier artifact remains unapproved.
- Status: Planned.

## EXECUTION

