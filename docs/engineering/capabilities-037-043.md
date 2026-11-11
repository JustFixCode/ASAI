# ASAI capabilities 037–043

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-037 — Market-session awareness
- Purpose: Resolve venue session state from calendars.
- Implementation: `asai.sense.market_session_awareness.MarketSessionAwarenessService`; `run(request: MarketSessionAwarenessServiceRequest) -> MarketSessionAwarenessServiceResult`.
- Contract: Input: venue and timezone-aware timestamp; processing: apply holiday, half-day, and session rules; output: open/closed/pre/post/unknown plus calendar version. Internal event `asai.sense.market_session_awareness.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `market_session_awareness_runs` and `market_session_awareness_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `calendar_registry, timezone`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Holiday resolves closed; naive timestamp is rejected.
- Status: Planned.

### ASAI-038 — Data-quality detection
- Purpose: Detect invalid, duplicate, anomalous, and missing observations.
- Implementation: `asai.sense.data_quality_detection.DataQualityDetectionService`; `run(request: DataQualityDetectionServiceRequest) -> DataQualityDetectionServiceResult`.
- Contract: Input: observation batch and ruleset version; processing: run range, sequence, duplicate, gap checks; output: quality findings. Internal event `asai.sense.data_quality_detection.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `data_quality_detection_runs` and `data_quality_detection_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `market_data_store, rules_registry`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Duplicate sequence is flagged; clean batch has zero critical findings.
- Status: Planned.

### ASAI-039 — Feed-failure detection
- Purpose: Detect provider silence, errors, and sequence discontinuity.
- Implementation: `asai.sense.feed_failure_detection.FeedFailureDetectionService`; `run(request: FeedFailureDetectionServiceRequest) -> FeedFailureDetectionServiceResult`.
- Contract: Input: feed ID, current UTC time, health policy; processing: inspect heartbeat/error/sequence telemetry; output: health state and transition. Internal event `asai.sense.feed_failure_detection.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `feed_failure_detection_runs` and `feed_failure_detection_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `feed_adapter, notification_router`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Timed-out heartbeat degrades; unchanged state emits no duplicate event.
- Status: Planned.

### ASAI-040 — Multi-market observation
- Purpose: Align authorized observations across venues.
- Implementation: `asai.sense.multi_market_observation.MultiMarketObservationService`; `run(request: MultiMarketObservationServiceRequest) -> MultiMarketObservationServiceResult`.
- Contract: Input: 1–100 instruments and as-of UTC; processing: select latest not-after quote and normalize currency; output: source timestamps and explicit gaps. Internal event `asai.sense.multi_market_observation.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `multi_market_observation_runs` and `multi_market_observation_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless raw-feed policy is shorter.
- Dependencies and permissions: `price_store, currency_normalizer, authorization`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Unauthorized source is absent; missing instrument creates explicit gap.
- Status: Planned.


## RESEARCH

### ASAI-041 — Financial news research
- Purpose: Ingest licensed financial-news items for analysis.
- Implementation: `asai.research.financial_news_research.FinancialNewsResearchService`; `run(request: FinancialNewsResearchServiceRequest) -> FinancialNewsResearchServiceResult`.
- Contract: Input: source URL, title, published time, body hash, instruments; processing: deduplicate canonical URL/body and classify entities; output: research item and citations. Internal event `asai.research.financial_news_research.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `financial_news_research_runs` and `financial_news_research_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `source_registry, instrument_master`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Canonical duplicate URL is idempotent; missing publication time quarantines.
- Status: Planned.

### ASAI-042 — Economic-calendar research
- Purpose: Collect scheduled economic releases and revisions.
- Implementation: `asai.research.economic_calendar_research.EconomicCalendarResearchService`; `run(request: EconomicCalendarResearchServiceRequest) -> EconomicCalendarResearchServiceResult`.
- Contract: Input: issuer, event, timezone-aware release time, forecast, actual, source; processing: normalize UTC and revision lineage; output: release record and revision status. Internal event `asai.research.economic_calendar_research.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `economic_calendar_research_runs` and `economic_calendar_research_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `source_registry, timezone`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Naive release time is rejected; duplicate revision is idempotent.
- Status: Planned.

### ASAI-043 — Company research
- Purpose: Compile factual company reports from approved sources.
- Implementation: `asai.research.company_research.CompanyResearchService`; `run(request: CompanyResearchServiceRequest) -> CompanyResearchServiceResult`.
- Contract: Input: company UUID and source UUIDs; processing: extract attributed facts and preserve conflicts; output: cited company report. Internal event `asai.research.company_research.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `company_research_runs` and `company_research_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `company_master, source_registry`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Report without citation is rejected; conflicting facts both remain cited.
- Status: Planned.

