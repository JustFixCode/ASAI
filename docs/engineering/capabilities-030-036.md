# ASAI capabilities 030–036

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-030 — Scenario modelling
- Purpose: Apply bounded supplied shocks to baselines.
- Implementation: `asai.math.scenario_modelling.ScenarioModellingService`; `run(request: ScenarioModellingServiceRequest) -> ScenarioModellingServiceResult`.
- Contract: Input: baseline variables, named shocks, formula version; processing: apply shocks deterministically in sequence; output: deltas and assumptions. Internal event `asai.math.scenario_modelling.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `scenario_modelling_runs` and `scenario_modelling_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `formula_registry, portfolio_math`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Unknown shock variable is rejected; same-variable shocks retain input sequence.
- Status: Planned.


## SENSE

### ASAI-031 — Live price monitoring
- Purpose: Ingest authorized real-time prices and detect staleness.
- Implementation: `asai.sense.live_price_monitoring.LivePriceMonitoringService`; `run(request: LivePriceMonitoringServiceRequest) -> LivePriceMonitoringServiceResult`.
- Contract: Input: provider, instrument, bid/ask/last, observed time, sequence; processing: validate quote/sequence and persist tick; output: ingest result and stale state. Internal event `asai.sense.live_price_monitoring.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `live_price_monitoring_runs` and `live_price_monitoring_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `feed_adapter, instrument_master`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Replayed sequence is idempotent; ask below bid quarantines.
- Status: Planned.

### ASAI-032 — Historical price collection
- Purpose: Collect licensed historical OHLCV data with lineage.
- Implementation: `asai.sense.historical_price_collection.HistoricalPriceCollectionService`; `run(request: HistoricalPriceCollectionServiceRequest) -> HistoricalPriceCollectionServiceResult`.
- Contract: Input: instrument, interval, UTC start/end, provider; processing: page, validate, and deduplicate bars; output: collection count and gaps. Internal event `asai.sense.historical_price_collection.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `historical_price_collection_runs` and `historical_price_collection_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `feed_adapter, market_clock`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: End before start is rejected; duplicate bar is idempotent.
- Status: Planned.

### ASAI-033 — Order-book analysis
- Purpose: Analyze supplied book depth without orders.
- Implementation: `asai.sense.order_book_analysis.OrderBookAnalysisService`; `run(request: OrderBookAnalysisServiceRequest) -> OrderBookAnalysisServiceResult`.
- Contract: Input: ordered bid/ask levels and 1–100 depth; processing: validate monotonic book and calculate depth/imbalance; output: spread, depth, imbalance. Internal event `asai.sense.order_book_analysis.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `order_book_analysis_runs` and `order_book_analysis_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `feed_adapter, arithmetic_engine`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Descending asks are rejected; one-sided book returns no spread.
- Status: Planned.

### ASAI-034 — Trading-volume monitoring
- Purpose: Compare observed volume with rolling baseline.
- Implementation: `asai.sense.trading_volume_monitoring.TradingVolumeMonitoringService`; `run(request: TradingVolumeMonitoringServiceRequest) -> TradingVolumeMonitoringServiceResult`.
- Contract: Input: instrument bar and baseline window; processing: validate volume and calculate ratio/z-score; output: volume signal or insufficient history. Internal event `asai.sense.trading_volume_monitoring.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `trading_volume_monitoring_runs` and `trading_volume_monitoring_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `historical_collector, statistics_service`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Negative volume is rejected; zero baseline avoids division by zero.
- Status: Planned.

### ASAI-035 — Spread monitoring
- Purpose: Measure bid-ask spreads and threshold status.
- Implementation: `asai.sense.spread_monitoring.SpreadMonitoringService`; `run(request: SpreadMonitoringServiceRequest) -> SpreadMonitoringServiceResult`.
- Contract: Input: bid, ask, timestamp, threshold version; processing: calculate absolute/midpoint bps spread; output: spread observation/classification. Internal event `asai.sense.spread_monitoring.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `spread_monitoring_runs` and `spread_monitoring_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `live_price_monitor, instrument_master`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Bid 100/ask 101 gives 100 bps; crossed quote is rejected.
- Status: Planned.

### ASAI-036 — Volatility monitoring
- Purpose: Monitor realized volatility of observed returns.
- Implementation: `asai.sense.volatility_monitoring.VolatilityMonitoringService`; `run(request: VolatilityMonitoringServiceRequest) -> VolatilityMonitoringServiceResult`.
- Contract: Input: series UUID and 2–252 lookback; processing: fetch returns and calculate latest metric; output: volatility and staleness state. Internal event `asai.sense.volatility_monitoring.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `volatility_monitoring_runs` and `volatility_monitoring_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `time_series, volatility_calculator`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Lookback one is rejected; stale source reports stale state.
- Status: Planned.

