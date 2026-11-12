# ASAI capabilities 001–007

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-001 — Independent reasoning
- Purpose: Derive auditable conclusions from supplied evidence.
- Implementation: `asai.brain.independent_reasoning.IndependentReasoningService`; `run(request: IndependentReasoningServiceRequest) -> IndependentReasoningServiceResult`.
- Contract: Input: question and evidence UUIDs; processing: normalize claims, apply registered rules, preserve premise links; output: conclusion, confidence, and premise list. Internal event `asai.brain.independent_reasoning.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `independent_reasoning_runs` and `independent_reasoning_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `evidence_store, rule_engine`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Contradictory sources yield `inconclusive`; missing evidence UUID is rejected.
- Status: Planned.

### ASAI-002 — Multi-step thinking
- Purpose: Construct bounded reasoning plans.
- Implementation: `asai.brain.multi_step_thinking.MultiStepThinkingService`; `run(request: MultiStepThinkingServiceRequest) -> MultiStepThinkingServiceResult`.
- Contract: Input: goal, constraints, and 1–20 step limit; processing: build and cycle-check a dependency DAG; output: ordered steps and blocked dependencies. Internal event `asai.brain.multi_step_thinking.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `multi_step_thinking_runs` and `multi_step_thinking_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `goal_registry, rule_engine`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: A dependency cycle is rejected; a 21-step plan is rejected.
- Status: Planned.

### ASAI-003 — Decision-making
- Purpose: Rank explicit analytical options.
- Implementation: `asai.brain.decision_making.DecisionMakingService`; `run(request: DecisionMakingServiceRequest) -> DecisionMakingServiceResult`.
- Contract: Input: options, weighted criteria, and evidence IDs; processing: validate weights then score and retain ties; output: ranked recommendation and score breakdown. Internal event `asai.brain.decision_making.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `decision_making_runs` and `decision_making_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `reasoning, uncertainty`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Equal top scores remain tied; weights totaling 1.2 fail.
- Status: Planned.

### ASAI-004 — Strategic planning
- Purpose: Draft non-executable objective roadmaps.
- Implementation: `asai.brain.strategic_planning.StrategicPlanningService`; `run(request: StrategicPlanningServiceRequest) -> StrategicPlanningServiceResult`.
- Contract: Input: approved objective UUID, horizon days, assumptions; processing: derive milestones/KPIs against constraints; output: versioned strategy draft. Internal event `asai.brain.strategic_planning.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `strategic_planning_runs` and `strategic_planning_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `goal_registry, scenario_model`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Horizon zero is rejected; an unapproved objective is rejected.
- Status: Planned.

### ASAI-005 — Goal management
- Purpose: Track internal analytical goals.
- Implementation: `asai.brain.goal_management.GoalManagementService`; `run(request: GoalManagementServiceRequest) -> GoalManagementServiceResult`.
- Contract: Input: title, owner UUID, due time, requested state; processing: enforce open/blocked/completed/cancelled transitions; output: versioned goal and transition receipt. Internal event `asai.brain.goal_management.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `goal_management_runs` and `goal_management_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `identity, audit_log`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Completed→open is rejected; stale version update conflicts.
- Status: Planned.

### ASAI-006 — Context awareness
- Purpose: Assemble as-of analytical context.
- Implementation: `asai.brain.context_awareness.ContextAwarenessService`; `run(request: ContextAwarenessServiceRequest) -> ContextAwarenessServiceResult`.
- Contract: Input: subject UUIDs, scoped requester, as-of timestamp; processing: retrieve authorized facts and rank recency; output: provenanced context snapshot. Internal event `asai.brain.context_awareness.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `context_awareness_runs` and `context_awareness_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `memory_retrieval, authorization`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Future fact is excluded at as-of time; unauthorized fact is absent.
- Status: Planned.

### ASAI-007 — Uncertainty evaluation
- Purpose: Quantify evidence confidence and gaps.
- Implementation: `asai.brain.uncertainty_evaluation.UncertaintyEvaluationService`; `run(request: UncertaintyEvaluationServiceRequest) -> UncertaintyEvaluationServiceResult`.
- Contract: Input: claims, source reliability, sample metadata; processing: bound confidence and identify missing support; output: per-claim interval and gap list. Internal event `asai.brain.uncertainty_evaluation.completed.v1` carries `run_id`, input hash, result reference, and status.
- Data and memory: PostgreSQL `uncertainty_evaluation_runs` and `uncertainty_evaluation_items`; UUID PKs, `run_id` FK, input/result SHA-256, append-only status history; retain records 7 years unless source retention is shorter.
- Dependencies and permissions: `source_registry, statistics`; read only named upstream records and insert/update only its two tables; no deployment, brokerage, custody, or trading authority.
- Failure handling: Validate typed input before persistence; invalid rows are quarantined with a reason, upstream timeout yields `degraded`, and no inferred output is emitted.
- Acceptance tests: Reliability 1.3 is rejected; missing reliability returns `unknown`.
- Status: Planned.

