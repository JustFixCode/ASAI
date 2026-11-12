# ASAI capabilities 023–029

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-023 — Probability estimation
- Purpose: Estimate probability from observations and priors.
- Implementation: `asai.math.probability_estimation.ProbabilityEstimationService`; `run(request: ProbabilityEstimationServiceRequest) -> ProbabilityEstimationServiceResult`.
- Contract: Input: successes, trials, Beta alpha/beta; processing: validate counts and calculate posterior interval; output: estimate and assumptions. Internal event `asai.math.probability_estimation.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `probability_estimation_runs` and `probability_estimation_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `statistics_service`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: 11 successes/10 trials is rejected; zero trials is prior-labeled.
- Status: Planned.

### ASAI-024 — Expected-return calculations
- Purpose: Calculate scenario-weighted analytical return.
- Implementation: `asai.math.expected_return_calculations.ExpectedReturnCalculationsService`; `run(request: ExpectedReturnCalculationsServiceRequest) -> ExpectedReturnCalculationsServiceResult`.
- Contract: Input: scenario probabilities and decimal returns; processing: verify probability sum and weight contributions; output: expected return report. Internal event `asai.math.expected_return_calculations.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `expected_return_calculations_runs` and `expected_return_calculations_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `probability_estimator, formula_registry`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Probabilities totaling 0.95 are rejected; negative scenario contributes correctly.
- Status: Planned.

### ASAI-025 — Risk calculations
- Purpose: Calculate stated historical risk measures.
- Implementation: `asai.math.risk_calculations.RiskCalculationsService`; `run(request: RiskCalculationsServiceRequest) -> RiskCalculationsServiceResult`.
- Contract: Input: return series and confidence in (0,1); processing: sort losses and calculate VaR/expected shortfall; output: risk report and method. Internal event `asai.math.risk_calculations.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `risk_calculations_runs` and `risk_calculations_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `statistics_service, time_series`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Confidence 1.0 is rejected; 19 observations are insufficient.
- Status: Planned.

### ASAI-026 — Portfolio mathematics
- Purpose: Aggregate supplied position values and weights.
- Implementation: `asai.math.portfolio_mathematics.PortfolioMathematicsService`; `run(request: PortfolioMathematicsServiceRequest) -> PortfolioMathematicsServiceResult`.
- Contract: Input: positions, normalized Decimal prices; processing: calculate market values and total weights; output: portfolio report and missing symbols. Internal event `asai.math.portfolio_mathematics.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `portfolio_mathematics_runs` and `portfolio_mathematics_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `instrument_master, arithmetic_engine`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Missing price is reported not zero; zero total yields undefined weights.
- Status: Planned.

### ASAI-027 — Correlation analysis
- Purpose: Measure linear relationship of aligned series.
- Implementation: `asai.math.correlation_analysis.CorrelationAnalysisService`; `run(request: CorrelationAnalysisServiceRequest) -> CorrelationAnalysisServiceResult`.
- Contract: Input: two dated return series and minimum points; processing: inner-align dates and calculate Pearson r; output: correlation, overlap, exclusions. Internal event `asai.math.correlation_analysis.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `correlation_analysis_runs` and `correlation_analysis_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `time_series, statistics_service`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Disjoint dates are insufficient; constant series correlation is undefined.
- Status: Planned.

### ASAI-028 — Time-series analysis
- Purpose: Validate, resample, and derive returns.
- Implementation: `asai.math.time_series_analysis.TimeSeriesAnalysisService`; `run(request: TimeSeriesAnalysisServiceRequest) -> TimeSeriesAnalysisServiceResult`.
- Contract: Input: UTC points and daily/weekly/monthly frequency; processing: sort, deduplicate by priority, resample; output: return series and gaps. Internal event `asai.math.time_series_analysis.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `time_series_analysis_runs` and `time_series_analysis_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `market_data_store, market_clock`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Equal-priority duplicate timestamp is rejected; zero prior price has unavailable return.
- Status: Planned.

### ASAI-029 — Volatility calculations
- Purpose: Compute annualized realized volatility.
- Implementation: `asai.math.volatility_calculations.VolatilityCalculationsService`; `run(request: VolatilityCalculationsServiceRequest) -> VolatilityCalculationsServiceResult`.
- Contract: Input: return series and positive periods/year; processing: sample deviation times square-root factor; output: volatility, count, formula version. Internal event `asai.math.volatility_calculations.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `volatility_calculations_runs` and `volatility_calculations_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `statistics_service, formula_registry`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Annualization factor zero is rejected; two returns calculate reproducibly.
- Status: Planned.

