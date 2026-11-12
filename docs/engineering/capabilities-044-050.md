# ASAI capabilities 044–050

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-044 — Cryptocurrency research
- Purpose: Compile source-linked digital-asset research.
- Implementation: `asai.research.cryptocurrency_research.CryptocurrencyResearchService`; `run(request: CryptocurrencyResearchServiceRequest) -> CryptocurrencyResearchServiceResult`.
- Contract: Input: asset UUID and source UUIDs; processing: reconcile chain, token, and market claims; output: attributed crypto report. Internal event `asai.research.cryptocurrency_research.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `cryptocurrency_research_runs` and `cryptocurrency_research_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `digital_asset_master, source_registry`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Ambiguous ticker without asset ID is rejected; source-less claim fails.
- Status: Planned.

### ASAI-045 — Forex research
- Purpose: Research currency-pair drivers and macro evidence.
- Implementation: `asai.research.forex_research.ForexResearchService`; `run(request: ForexResearchServiceRequest) -> ForexResearchServiceResult`.
- Contract: Input: base currency, quote currency, source UUIDs, as-of time; processing: validate ISO pairs and link rate/macro claims; output: cited FX research report. Internal event `asai.research.forex_research.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `forex_research_runs` and `forex_research_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `currency_master, economic_calendar`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Non-ISO pair is rejected; future source fact is excluded by as-of.
- Status: Planned.

### ASAI-046 — Central-bank monitoring
- Purpose: Track official central-bank communications and decisions.
- Implementation: `asai.research.central_bank_monitoring.CentralBankMonitoringService`; `run(request: CentralBankMonitoringServiceRequest) -> CentralBankMonitoringServiceResult`.
- Contract: Input: bank UUID, official document URL, published time; processing: verify official domain and extract decision metadata; output: central-bank observation. Internal event `asai.research.central_bank_monitoring.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `central_bank_monitoring_runs` and `central_bank_monitoring_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `central_bank_registry, source_registry`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Nonofficial domain fails verification; missing publication time quarantines.
- Status: Planned.

### ASAI-047 — Earnings research
- Purpose: Collect company earnings releases and reported metrics.
- Implementation: `asai.research.earnings_research.EarningsResearchService`; `run(request: EarningsResearchServiceRequest) -> EarningsResearchServiceResult`.
- Contract: Input: company UUID, fiscal period, source, metrics; processing: validate period and revision against issuer source; output: earnings research record. Internal event `asai.research.earnings_research.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `earnings_research_runs` and `earnings_research_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `company_master, financial_memory`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Invalid fiscal period is rejected; duplicate issuer revision is idempotent.
- Status: Planned.

### ASAI-048 — Market-event detection
- Purpose: Detect defined events from validated research and market facts.
- Implementation: `asai.research.market_event_detection.MarketEventDetectionService`; `run(request: MarketEventDetectionServiceRequest) -> MarketEventDetectionServiceResult`.
- Contract: Input: event ruleset, fact IDs, as-of time; processing: evaluate registered predicates and deduplicate; output: event candidate with evidence. Internal event `asai.research.market_event_detection.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `market_event_detection_runs` and `market_event_detection_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `rules_registry, research_store, market_data_store`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Unknown ruleset is rejected; identical evidence does not duplicate event.
- Status: Planned.

### ASAI-049 — Source verification
- Purpose: Assess source identity, provenance, and integrity.
- Implementation: `asai.research.source_verification.SourceVerificationService`; `run(request: SourceVerificationServiceRequest) -> SourceVerificationServiceResult`.
- Contract: Input: source URL, publisher metadata, content hash; processing: validate registry, domain, signature/hash where available; output: verification result and reasons. Internal event `asai.research.source_verification.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `source_verification_runs` and `source_verification_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `source_registry, domain_policy`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Unregistered publisher fails; content-hash mismatch fails verification.
- Status: Planned.

### ASAI-050 — Research reporting
- Purpose: Render a traceable report from cited research records.
- Implementation: `asai.research.research_reporting.ResearchReportingService`; `run(request: ResearchReportingServiceRequest) -> ResearchReportingServiceResult`.
- Contract: Input: topic, item UUIDs, audience, as-of time; processing: assemble cited findings and unresolved conflicts; output: versioned research report. Internal event `asai.research.research_reporting.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `research_reporting_runs` and `research_reporting_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `research_store, authorization`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Uncited item is excluded; inaccessible item is redacted.
- Status: Planned.



All capabilities in this fragment are forward-looking construction requirements. Processing is **paper-only** unless a future, explicit qualification changes that scope. Proposals cannot execute orders. Market orders carry unbounded price risk and are not approved by current controls.

## ANALYSIS

