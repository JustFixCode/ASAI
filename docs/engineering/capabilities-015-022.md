# ASAI capabilities 015–022

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-015 — Financial memory
- Purpose: Retain source-attributed financial facts.
- Implementation: `asai.memory.financial_memory.FinancialMemoryService`; `run(request: FinancialMemoryServiceRequest) -> FinancialMemoryServiceResult`.
- Contract: Input: instrument UUID, metric, decimal value, currency, period, source; processing: validate units and source revisions; output: financial fact ID. Internal event `asai.memory.financial_memory.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `financial_memory_runs` and `financial_memory_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `instrument_master, currency, source_registry`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Missing currency is rejected; duplicate source revision is idempotent.
- Status: Planned.

### ASAI-016 — Decision memory
- Purpose: Archive decisions and dispositions.
- Implementation: `asai.memory.decision_memory.DecisionMemoryService`; `run(request: DecisionMemoryServiceRequest) -> DecisionMemoryServiceResult`.
- Contract: Input: decision UUID and accepted/rejected/deferred disposition; processing: snapshot evidence hashes and disposition; output: immutable archive entry. Internal event `asai.memory.decision_memory.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `decision_memory_runs` and `decision_memory_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `decision_store, evidence_store`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Unsupported disposition is rejected; second archive returns existing entry.
- Status: Planned.

### ASAI-017 — Operational memory
- Purpose: Record recoverable workflow state.
- Implementation: `asai.memory.operational_memory.OperationalMemoryService`; `run(request: OperationalMemoryServiceRequest) -> OperationalMemoryServiceResult`.
- Contract: Input: registered run type, correlation UUID, input hash; processing: enforce legal transition state machine; output: run ledger entry. Internal event `asai.memory.operational_memory.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `operational_memory_runs` and `operational_memory_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `workflow_registry, audit_log`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: `succeeded→running` is rejected; repeated correlation returns existing run.
- Status: Planned.

### ASAI-018 — Experience retrieval
- Purpose: Retrieve permitted prior episodes.
- Implementation: `asai.memory.experience_retrieval.ExperienceRetrievalService`; `run(request: ExperienceRetrievalServiceRequest) -> ExperienceRetrievalServiceResult`.
- Contract: Input: query, as-of timestamp, scopes, limit 1–50; processing: search lexical/vector indexes then ACL-filter; output: ranked excerpts and provenance. Internal event `asai.memory.experience_retrieval.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `experience_retrieval_runs` and `experience_retrieval_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `embedding_index, authorization`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Empty query is rejected; restricted episode never appears.
- Status: Planned.

### ASAI-019 — Memory consolidation
- Purpose: Propose semantic candidates from closed episodes.
- Implementation: `asai.memory.memory_consolidation.MemoryConsolidationService`; `run(request: MemoryConsolidationServiceRequest) -> MemoryConsolidationServiceResult`.
- Contract: Input: window start/end and consolidation policy; processing: cluster duplicates with mandatory episode links; output: reviewable candidate batch. Internal event `asai.memory.memory_consolidation.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `memory_consolidation_runs` and `memory_consolidation_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `episodic_repository, semantic_graph`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Candidate without episode link is rejected; future window is rejected.
- Status: Planned.

### ASAI-020 — Memory integrity
- Purpose: Find checksum, FK, version, and retention faults.
- Implementation: `asai.memory.memory_integrity.MemoryIntegrityService`; `run(request: MemoryIntegrityServiceRequest) -> MemoryIntegrityServiceResult`.
- Contract: Input: table/time scope; processing: scan integrity constraints without repair; output: finding report. Internal event `asai.memory.memory_integrity.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `memory_integrity_runs` and `memory_integrity_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `memory_repositories, retention_policy`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Altered checksum produces critical finding; retention-held row is not purgeable.
- Status: Planned.


## MATH

### ASAI-021 — Arithmetic engine
- Purpose: Perform deterministic high-precision arithmetic.
- Implementation: `asai.math.arithmetic_engine.ArithmeticEngineService`; `run(request: ArithmeticEngineServiceRequest) -> ArithmeticEngineServiceResult`.
- Contract: Input: operation, Decimal operands, precision policy; processing: use Decimal with configured rounding; output: value and rounding metadata. Internal event `asai.math.arithmetic_engine.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `arithmetic_engine_runs` and `arithmetic_engine_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `decimal_policy, formula_registry`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Division by zero errors; float operand is rejected.
- Status: Planned.

### ASAI-022 — Statistical analysis
- Purpose: Compute descriptive statistics.
- Implementation: `asai.math.statistical_analysis.StatisticalAnalysisService`; `run(request: StatisticalAnalysisServiceRequest) -> StatisticalAnalysisServiceResult`.
- Contract: Input: finite Decimal series and ddof; processing: calculate count, mean, median, variance, standard deviation; output: named metric report. Internal event `asai.math.statistical_analysis.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `statistical_analysis_runs` and `statistical_analysis_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years.
- Dependencies and permissions: `arithmetic_engine`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation precedes persistence; invalid input quarantines with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: NaN input is rejected; one value with ddof=1 has unavailable variance.
- Status: Planned.

