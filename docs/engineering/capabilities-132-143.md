# ASAI capabilities 132–143

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-132 — Memory monitoring
- **Purpose:** detect memory pressure and leaks.
- **Implementation:** Proposed package/class `asai.resource.memory.MemoryMonitor.sample(service: ServiceRef) -> MemorySample`.
- **Contract:** RSS,heap,limit,restarts -> pressure/trend; `resource.memory.sampled.v1`.
- **Data and memory:** PostgreSQL `memory_samples,leak_findings,service_limits; raw 90d, findings 2y`.
- **Dependencies and permissions:** `observability.agent,resource.recovery; read metrics only`.
- **Failure handling:** missing agent => unknown; no unauthorized restart.
- **Acceptance tests:** monotonic heap leak detected; zero limit is invalid.
- **Status:** Planned.

### ASAI-133 — Storage monitoring
- **Purpose:** protect durable capacity and journal integrity.
- **Implementation:** Proposed package/class `asai.resource.storage.StorageMonitor.sample(volume: VolumeRef) -> StorageSample`.
- **Contract:** capacity,used,inodes,latency -> threshold state; `resource.storage.sampled.v1`.
- **Data and memory:** PostgreSQL `storage_samples,volume_policies,storage_alerts; raw 90d, alerts 2y`.
- **Dependencies and permissions:** `observability.agent,treasury.ledger; read-only`.
- **Failure handling:** unknown/near-full blocks noncritical writes, preserves journals.
- **Acceptance tests:** inode exhaustion alerts despite free bytes; read-only volume triggers suspension.
- **Status:** Planned.

### ASAI-134 — Network monitoring
- **Purpose:** detect connectivity and data-path failures.
- **Implementation:** Proposed package/class `asai.resource.network.NetworkMonitor.probe(path: NetworkPath) -> NetworkSample`.
- **Contract:** latency,loss,DNS,TLS result -> health state; `resource.network.sampled.v1`.
- **Data and memory:** PostgreSQL `network_samples,network_incidents,endpoint_policies; 90d/2y`.
- **Dependencies and permissions:** `observability.agent,marketdata.ingest; probe-only`.
- **Failure handling:** failed probe makes dependent feed unverified.
- **Acceptance tests:** TLS mismatch blocks endpoint; packet-loss threshold alerts.
- **Status:** Planned.

### ASAI-135 — Compute allocation
- **Purpose:** allocate finite compute by criticality and budget.
- **Implementation:** Proposed package/class `asai.resource.allocation.ComputeAllocator.allocate(request: ComputeRequest) -> AllocationDecision`.
- **Contract:** workload priority,quota,cost,capacity -> grant/queue/deny; `resource.compute.allocated.v1`.
- **Data and memory:** PostgreSQL `compute_quotas,allocations,allocation_events; 2y`.
- **Dependencies and permissions:** `resource.cpu,resource.memory,resource.budget; scheduler authority only`.
- **Failure handling:** unknown capacity denies discretionary grants.
- **Acceptance tests:** ledger workload preempts backtest; over-quota request queues.
- **Status:** Planned.

### ASAI-136 — Model-resource selection
- **Purpose:** select approved model meeting task and resource bounds.
- **Implementation:** Proposed package/class `asai.resource.models.ModelSelector.select(task: ModelTask) -> ModelSelection`.
- **Contract:** task class,latency,cost,entitlement,policy -> model or deny; `resource.model.selected.v1`.
- **Data and memory:** PostgreSQL `model_catalog,model_policies,selection_audits; 2y`.
- **Dependencies and permissions:** `survival.ai_cost,resource.budget,identity; select only approved models`.
- **Failure handling:** missing price/entitlement denies nonessential selection.
- **Acceptance tests:** expensive model rejected over budget; expired model approval rejected.
- **Status:** Planned.

### ASAI-137 — Background-task management
- **Purpose:** govern asynchronous jobs without starving critical work.
- **Implementation:** Proposed package/class `asai.resource.background.BackgroundTaskManager.enqueue(task: BackgroundTask) -> TaskReceipt`.
- **Contract:** typed task,priority,idempotency,deadline -> queued/running state; `resource.background.queued.v1`.
- **Data and memory:** PostgreSQL `background_tasks,task_runs,dead_letters; 90d/2y`.
- **Dependencies and permissions:** `resource.allocation,identity; enqueue scoped jobs only`.
- **Failure handling:** queue outage rejects noncritical jobs; critical jobs alert.
- **Acceptance tests:** duplicate key runs once; expired low-priority task is cancelled.
- **Status:** Planned.

### ASAI-138 — Service-cost optimisation
- **Purpose:** identify safe cost reductions from measured usage.
- **Implementation:** Proposed package/class `asai.resource.optimisation.ServiceCostOptimiser.propose(scope: ServiceScope) -> OptimisationProposal`.
- **Contract:** usage,cost,SLI,commitments -> nonbinding savings proposal; `resource.cost_optimisation.proposed.v1`.
- **Data and memory:** PostgreSQL `service_cost_profiles,optimisation_proposals,approval_records; 7y`.
- **Dependencies and permissions:** `survival.infrastructure,survival.ai_cost; read/propose only`.
- **Failure handling:** incomplete cost or SLI data yields no automatic change.
- **Acceptance tests:** proposal preserves latency SLI; unapproved proposal changes nothing.
- **Status:** Planned.

### ASAI-139 — Resource-failure recovery
- **Purpose:** recover services via authorized runbooks and verify health.
- **Implementation:** Proposed package/class `asai.resource.recovery.RecoveryCoordinator.recover(incident: Incident) -> RecoveryResult`.
- **Contract:** incident,runbook,scope,approval -> staged recovery/verification; `resource.recovery.completed.v1`.
- **Data and memory:** PostgreSQL `incidents,recovery_runs,runbook_versions; 2y`.
- **Dependencies and permissions:** `observability.agent,identity,risk.suspension; runbook-scoped authority`.
- **Failure handling:** failed verification keeps service degraded and trading protected.
- **Acceptance tests:** bad restart rolls back safely; missing runbook cannot restart.
- **Status:** Planned.

### ASAI-140 — Resource-budget enforcement
- **Purpose:** enforce CPU, memory, storage, and spend quotas.
- **Implementation:** Proposed package/class `asai.resource.budget.ResourceBudgetGate.check(request: ResourceRequest) -> BudgetDecision`.
- **Contract:** usage,quota,cost forecast,criticality -> grant/throttle/deny; `resource.budget.checked.v1`.
- **Data and memory:** PostgreSQL `resource_budgets,budget_usage,budget_decisions; 2y`.
- **Dependencies and permissions:** `resource monitors,survival costs; throttle/deny only`.
- **Failure handling:** missing usage fails closed for discretionary work.
- **Acceptance tests:** storage quota denies batch; critical reconciliation remains reserved.
- **Status:** Planned.

## LEARNING

### ASAI-141 — Trade-outcome learning
- **Purpose:** derive labelled outcomes from reconciled closed trades.
- **Implementation:** Proposed package/class `asai.learning.outcomes.TradeOutcomeLearner.record(trade: ClosedTrade) -> OutcomeRecord`.
- **Contract:** confirmed fills, realised P&L, fees, context -> immutable outcome; `learning.trade_outcome.recorded.v1`.
- **Data and memory:** PostgreSQL `trade_outcomes,trade_contexts,label_versions; 7y`.
- **Dependencies and permissions:** `treasury.pnl,marketdata.snapshot; read/write learning store only`.
- **Failure handling:** unreconciled trade is withheld from learning.
- **Acceptance tests:** fees alter label; duplicate fill creates one outcome.
- **Status:** Planned.

### ASAI-142 — Prediction-error learning
- **Purpose:** measure forecast error against verified future observations.
- **Implementation:** Proposed package/class `asai.learning.prediction_error.PredictionErrorLearner.compare(prediction: Prediction) -> ErrorRecord`.
- **Contract:** versioned forecast and verified realised value -> Decimal error/calibration; `learning.prediction_error.recorded.v1`.
- **Data and memory:** PostgreSQL `predictions,prediction_errors,observation_refs; 7y`.
- **Dependencies and permissions:** `marketdata.snapshot,identity; read models/data only`.
- **Failure handling:** missing/stale outcome leaves error pending.
- **Acceptance tests:** directionally wrong forecast recorded; revised observation supersedes version.
- **Status:** Planned.

### ASAI-143 — Strategy-performance learning
- **Purpose:** evaluate strategies net of costs and risk.
- **Implementation:** Proposed package/class `asai.learning.strategy.StrategyPerformanceLearner.evaluate(strategy_id: UUID) -> StrategyScore`.
- **Contract:** reconciled outcomes, fees, exposure, benchmark -> versioned score; `learning.strategy_performance.evaluated.v1`.
- **Data and memory:** PostgreSQL `strategy_scores,strategy_runs,benchmark_snapshots; 7y`.
- **Dependencies and permissions:** `treasury.pnl,risk.portfolio; analysis only`.
- **Failure handling:** insufficient sample returns inconclusive.
- **Acceptance tests:** negative gross becomes worse net fees; paper and real scores remain separate.
- **Status:** Planned.

