# ASAI capabilities 008–014

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-008 — Alternative thinking
- Purpose: Produce differentiated hypotheses.
- Implementation: `asai.brain.alternative_thinking.AlternativeThinkingService`; `run(request: AlternativeThinkingServiceRequest) -> AlternativeThinkingServiceResult`.
- Contract: Input: question, evidence UUIDs, limit 1–5; processing: generate nonduplicate hypotheses and counterevidence; output: ranked alternatives with citations. Internal event `asai.brain.alternative_thinking.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `alternative_thinking_runs` and `alternative_thinking_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `reasoning, evidence_store`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Duplicate hypothesis is collapsed; limit six is rejected.
- Status: Planned.

### ASAI-009 — Decision explanation
- Purpose: Render recorded decision traces.
- Implementation: `asai.brain.decision_explanation.DecisionExplanationService`; `run(request: DecisionExplanationServiceRequest) -> DecisionExplanationServiceResult`.
- Contract: Input: decision UUID and technical/plain audience; processing: resolve scores, premises, uncertainty, ACL redaction; output: cited explanation. Internal event `asai.brain.decision_explanation.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `decision_explanation_runs` and `decision_explanation_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `decision_store, authorization`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Missing score row fails integrity; restricted premise is redacted.
- Status: Planned.

### ASAI-010 — Priority management
- Purpose: Order analytical backlog transparently.
- Implementation: `asai.brain.priority_management.PriorityManagementService`; `run(request: PriorityManagementServiceRequest) -> PriorityManagementServiceResult`.
- Contract: Input: work UUIDs and urgency/impact/dependency weights; processing: validate policy and deterministic-sort scores; output: ranked backlog with rationale. Internal event `asai.brain.priority_management.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `priority_management_runs` and `priority_management_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `work_queue, goal_registry`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Equal scores tie-break by UUID; duplicate work ID is rejected.
- Status: Planned.


## MEMORY

### ASAI-011 — Episodic memory
- Purpose: Store immutable timestamped analytical events.
- Implementation: `asai.memory.episodic_memory.EpisodicMemoryService`; `run(request: EpisodicMemoryServiceRequest) -> EpisodicMemoryServiceResult`.
- Contract: Input: actor UUID, occurred_at, event type, payload reference; processing: validate chronology and append event; output: episode UUID and checksum. Internal event `asai.memory.episodic_memory.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `episodic_memory_runs` and `episodic_memory_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `identity, audit_log`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Updating an episode is rejected; actor FK failure is rejected.
- Status: Planned.

### ASAI-012 — Semantic memory
- Purpose: Version entities and asserted facts.
- Implementation: `asai.memory.semantic_memory.SemanticMemoryService`; `run(request: SemanticMemoryServiceRequest) -> SemanticMemoryServiceResult`.
- Contract: Input: subject UUID, controlled predicate, JSON object, source UUID; processing: validate ontology and validity interval; output: fact version and provenance. Internal event `asai.memory.semantic_memory.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `semantic_memory_runs` and `semantic_memory_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `ontology, source_registry`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Unknown predicate is rejected; overlapping same-source validity is rejected.
- Status: Planned.

### ASAI-013 — Strategic memory
- Purpose: Preserve strategy assumptions and measured outcomes.
- Implementation: `asai.memory.strategic_memory.StrategicMemoryService`; `run(request: StrategicMemoryServiceRequest) -> StrategicMemoryServiceResult`.
- Contract: Input: approved draft UUID and outcome metrics; processing: link assumptions to immutable measurements; output: strategy-memory record. Internal event `asai.memory.strategic_memory.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `strategic_memory_runs` and `strategic_memory_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `strategy_planner, metric_store`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Unknown draft is rejected; supersession cycle is rejected.
- Status: Planned.

### ASAI-014 — Mathematical memory
- Purpose: Register safe formulas and lineage.
- Implementation: `asai.memory.mathematical_memory.MathematicalMemoryService`; `run(request: MathematicalMemoryServiceRequest) -> MathematicalMemoryServiceResult`.
- Contract: Input: name, expression AST, typed variables; processing: parse safe AST and version formula; output: formula version and validation report. Internal event `asai.memory.mathematical_memory.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `mathematical_memory_runs` and `mathematical_memory_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain 7 years unless source retention is shorter.
- Dependencies and permissions: `safe_math_parser, audit_log`; read named upstream records and write only its tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Typed validation occurs before persistence; invalid rows quarantine with reason, timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Unsafe `__import__` AST is rejected; undefined variable is rejected.
- Status: Planned.

