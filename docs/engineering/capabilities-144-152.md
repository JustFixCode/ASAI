# ASAI capabilities 144–152

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-144 — Market-condition learning
- **Purpose:** label regimes from verified market features.
- **Implementation:** Proposed package/class `asai.learning.regimes.MarketConditionLearner.classify(snapshot: MarketSnapshot) -> RegimeLabel`.
- **Contract:** verified price,volatility,liquidity features -> labelled regime/confidence; `learning.market_condition.labelled.v1`.
- **Data and memory:** PostgreSQL `regime_labels,feature_snapshots,regime_model_versions; 7y`.
- **Dependencies and permissions:** `marketdata.snapshot,risk.volatility; read-only`.
- **Failure handling:** missing features yields unknown regime.
- **Acceptance tests:** stale book yields unknown; high-volatility regime label is reproducible.
- **Status:** Planned.

### ASAI-145 — Risk-outcome learning
- **Purpose:** link risk decisions to subsequent realised outcomes.
- **Implementation:** Proposed package/class `asai.learning.risk.RiskOutcomeLearner.link(decision: RiskDecision) -> RiskOutcome`.
- **Contract:** risk check, later fills/P&L/violations -> effectiveness record; `learning.risk_outcome.linked.v1`.
- **Data and memory:** PostgreSQL `risk_outcomes,risk_decision_refs,outcome_links; 7y`.
- **Dependencies and permissions:** `risk modules,treasury.pnl; analysis only`.
- **Failure handling:** unresolved outcome remains open, not success.
- **Acceptance tests:** rejected order has counterfactual excluded; breach outcome links exact policy version.
- **Status:** Planned.

### ASAI-146 — Experience comparison
- **Purpose:** compare like-for-like historical decisions without leakage.
- **Implementation:** Proposed package/class `asai.learning.experience.ExperienceComparator.compare(query: ExperienceQuery) -> ExperienceSet`.
- **Contract:** current features, time cutoff, mode and similarity policy -> ranked prior cases; `learning.experience.compared.v1`.
- **Data and memory:** PostgreSQL `experiences,feature_vectors,comparison_audits; 7y`.
- **Dependencies and permissions:** `learning outcomes,marketdata; read-only`.
- **Failure handling:** future-dated/other-mode records excluded.
- **Acceptance tests:** excludes outcomes after cutoff; paper case cannot rank real decision.
- **Status:** Planned.

### ASAI-147 — Model-performance tracking
- **Purpose:** track approved model accuracy, drift, cost and latency.
- **Implementation:** Proposed package/class `asai.learning.models.ModelPerformanceTracker.measure(model_id: UUID) -> ModelMetrics`.
- **Contract:** predictions,labels,resource usage,model version -> metrics/drift; `learning.model_performance.measured.v1`.
- **Data and memory:** PostgreSQL `model_metrics,drift_events,model_versions; 7y`.
- **Dependencies and permissions:** `prediction_error,resource.models; analysis only`.
- **Failure handling:** insufficient labels marks metrics provisional.
- **Acceptance tests:** drift alert after threshold; version change starts new series.
- **Status:** Planned.

### ASAI-148 — Knowledge updating
- **Purpose:** version curated knowledge with provenance and review.
- **Implementation:** Proposed package/class `asai.learning.knowledge.KnowledgeUpdater.propose(change: KnowledgeChange) -> KnowledgeRevision`.
- **Contract:** source evidence,scope,review state -> proposed/approved revision; `learning.knowledge.revision_proposed.v1`.
- **Data and memory:** PostgreSQL `knowledge_items,knowledge_revisions,provenance_refs; retain revisions indefinitely`.
- **Dependencies and permissions:** `identity,learning quality; propose only, no live policy mutation`.
- **Failure handling:** unverifiable source cannot approve.
- **Acceptance tests:** conflicting source requires review; revision preserves prior version.
- **Status:** Planned.

### ASAI-149 — Controlled strategy improvement
- **Purpose:** permit only offline, reviewed strategy changes with gates.
- **Implementation:** Proposed package/class `asai.learning.improvement.StrategyImprover.propose(candidate: StrategyCandidate) -> ImprovementProposal`.
- **Contract:** baseline,offline tests,risk constraints,approval -> proposal; `learning.strategy_improvement.proposed.v1`.
- **Data and memory:** PostgreSQL `strategy_candidates,offline_evaluations,improvement_approvals; 7y`.
- **Dependencies and permissions:** `strategy performance,risk modules,identity; no autonomous deployment/trading`.
- **Failure handling:** failed or missing gates deny proposal.
- **Acceptance tests:** candidate must beat baseline net costs; approval does not enable real trading.
- **Status:** Planned.

### ASAI-150 — Learning-quality evaluation
- **Purpose:** audit label, data, and experiment quality before use.
- **Implementation:** Proposed package/class `asai.learning.quality.LearningQualityEvaluator.evaluate(dataset: DatasetVersion) -> QualityReport`.
- **Contract:** provenance,completeness,leakage,split metrics -> pass/fail report; `learning.quality.evaluated.v1`.
- **Data and memory:** PostgreSQL `dataset_versions,quality_reports,quality_findings; 7y`.
- **Dependencies and permissions:** `learning stores,identity; read/audit only`.
- **Failure handling:** failed audit quarantines dataset/model update.
- **Acceptance tests:** detects target leakage; rejects mixed simulated and real labels.
- **Status:** Planned.


## AUTONOMY

### ASAI-151 — Autonomous task scheduling
- **Purpose:** proposes bounded work; it cannot execute trades or mutate configuration.
- **Implementation:** Proposed Python package `asai.autonomy.autonomous_task_scheduling`; class `AutonomousTaskSchedulingService`; `evaluate(input: TaskProposalV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `TaskProposalV1` containing task proposals, validates schema, identity, freshness and policy, then emits named internal event `TaskScheduledV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `autonomous_task_scheduling_records`, `autonomous_task_scheduling_events`, `autonomous_task_scheduling_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) deadline before earliest time. (2) execution task without authorisation.
- **Status:** Planned.

### ASAI-152 — Task prioritisation
- **Purpose:** ranks work deterministically with visible safety and deadline factors.
- **Implementation:** Proposed Python package `asai.autonomy.task_prioritisation`; class `TaskPrioritisationService`; `evaluate(input: PriorityContextV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `PriorityContextV1` containing priority factors, validates schema, identity, freshness and policy, then emits named internal event `TaskPrioritisedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `task_prioritisation_records`, `task_prioritisation_events`, `task_prioritisation_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) risk-latch task outranks research. (2) missing factor becomes unknown.
- **Status:** Planned.

