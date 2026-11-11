# ASAI capabilities 121–131

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-121 — Survival-state monitoring
- **Purpose:** classify survival from verified liquidation equity.
- **Implementation:** Proposed package/class `asai.survival.state.SurvivalMonitor.evaluate(snapshot: SurvivalSnapshot) -> SurvivalState`.
- **Contract:** reconciled assets, liabilities, liquidation costs, obligations -> HEALTHY/UNKNOWN/DEAD; `survival.state.evaluated.v1`.
- **Data and memory:** PostgreSQL `survival_snapshots,survival_states,survival_evidence_refs; transitions indefinite`.
- **Dependencies and permissions:** `treasury.reconciliation,risk.liquidity,survival.costs; restriction state only`.
- **Failure handling:** stale/unverified data => UNKNOWN/suspend, never death alone.
- **Acceptance tests:** costs/liabilities constrain equity; stale bank is not death.
- **Status:** Planned.

### ASAI-122 — Operating-cost calculation
- **Purpose:** forecast committed operating costs.
- **Implementation:** Proposed package/class `asai.survival.costs.OperatingCostCalculator.calculate(as_of: datetime) -> CostForecast`.
- **Contract:** approved invoices,contracts,schedules -> 30/90-day Decimal forecast; `survival.operating_cost.calculated.v1`.
- **Data and memory:** PostgreSQL `cost_commitments,cost_forecasts,cost_assumptions; 7y`.
- **Dependencies and permissions:** `treasury.expenses,contracts; read-only`.
- **Failure handling:** unknown renewal is flagged, not zero.
- **Acceptance tests:** quarterly bill appears in 90-day forecast; missing renewal price is unverified.
- **Status:** Planned.

### ASAI-123 — Infrastructure-cost monitoring
- **Purpose:** monitor hosting/platform cost variance.
- **Implementation:** Proposed package/class `asai.survival.infrastructure.InfrastructureCostMonitor.ingest(record: UsageCharge) -> CostSignal`.
- **Contract:** provider charge,tag,rate -> attributed variance; `survival.infrastructure_cost.updated.v1`.
- **Data and memory:** PostgreSQL `infrastructure_usage,infrastructure_charges,budget_variances; 7y`.
- **Dependencies and permissions:** `providers.billing,survival.costs; billing-read only`.
- **Failure handling:** untagged/delayed charge goes suspense forecast.
- **Acceptance tests:** rate rise is detected; untagged compute is flagged.
- **Status:** Planned.

### ASAI-124 — AI-cost monitoring
- **Purpose:** measure model usage and cap discretionary spend.
- **Implementation:** Proposed package/class `asai.survival.ai_cost.AiCostMonitor.record(usage: ModelUsage) -> AiCostStatus`.
- **Contract:** provider,model,tokens,price card -> accrual/threshold; `survival.ai_cost.updated.v1`.
- **Data and memory:** PostgreSQL `model_usage_records,ai_price_cards,ai_cost_rollups; 7y`.
- **Dependencies and permissions:** `providers.ai_billing,resource.budget; publish budget signal only`.
- **Failure handling:** unknown price card blocks nonessential calls.
- **Acceptance tests:** input/output rates price correctly; cap suspends discretionary model.
- **Status:** Planned.

### ASAI-125 — Data-cost monitoring
- **Purpose:** track data-license cost and entitlement use.
- **Implementation:** Proposed package/class `asai.survival.data_cost.DataCostMonitor.assess(entitlement: DataEntitlement) -> DataCostStatus`.
- **Contract:** vendor entitlement,usage,rate,expiry -> cost/compliance; `survival.data_cost.updated.v1`.
- **Data and memory:** PostgreSQL `data_entitlements,data_usage,data_cost_rollups; license evidence, 7y`.
- **Dependencies and permissions:** `providers.data_billing,marketdata.entitlements; read-only`.
- **Failure handling:** expired/unverifiable entitlement blocks use.
- **Acceptance tests:** service accounts exceed user license; renewal enters runway forecast.
- **Status:** Planned.

### ASAI-126 — Survival-runway calculation
- **Purpose:** estimate conservative time to reserve exhaustion.
- **Implementation:** Proposed package/class `asai.survival.runway.RunwayCalculator.calculate(state: FinancialState) -> RunwayResult`.
- **Contract:** reconciled cash,reserve,obligations,costs -> days/months/confidence; `survival.runway.calculated.v1`.
- **Data and memory:** PostgreSQL `runway_calculations,burn_rate_components,reserve_allocations; 7y`.
- **Dependencies and permissions:** `treasury.cash,survival.costs,treasury.reconciliation; read-only`.
- **Failure handling:** unverified cash/obligations => unknown runway.
- **Acceptance tests:** paper funds excluded; unreconciled bank returns unknown.
- **Status:** Planned.

### ASAI-127 — Reserve management
- **Purpose:** segregate and protect operating reserve.
- **Implementation:** Proposed package/class `asai.survival.reserve.ReserveManager.allocate(request: ReserveAllocation) -> ReserveDecision`.
- **Contract:** ledger,amount,target,approval -> protected balance; `survival.reserve.allocated.v1`.
- **Data and memory:** PostgreSQL `reserve_policies,reserve_allocations,reserve_release_requests; approvals, 7y`.
- **Dependencies and permissions:** `treasury.ledger,treasury.cash,identity; policy-limited designation/release`.
- **Failure handling:** cross-ledger/no approval denies release.
- **Acceptance tests:** order gate excludes reserve; automatic release rejected.
- **Status:** Planned.

### ASAI-128 — Economic self-assessment
- **Purpose:** assess ongoing viability conservatively.
- **Implementation:** Proposed package/class `asai.survival.economics.EconomicAssessor.assess(input: EconomicEvidence) -> EconomicAssessment`.
- **Contract:** reconciled assets/liabilities,costs,reserve,obligations -> evidence-backed viability; `survival.economic_assessment.completed.v1`.
- **Data and memory:** PostgreSQL `economic_assessments,obligation_schedules,assessment_evidence; state evidence indefinite`.
- **Dependencies and permissions:** `treasury.reconciliation,survival.runway,risk.liquidity; read-only`.
- **Failure handling:** missing evidence => INSUFFICIENT_EVIDENCE, not dead.
- **Acceptance tests:** net liquidation below obligations is nonviable; missing custodian statement is not death.
- **Status:** Planned.

### ASAI-129 — Survival-mode activation
- **Purpose:** constrain costs and autonomous risk under low runway.
- **Implementation:** Proposed package/class `asai.survival.mode.SurvivalModeController.activate(trigger: SurvivalTrigger) -> ModeActivation`.
- **Contract:** verified trigger/policy -> atomic restrictions; `survival.mode.activated.v1`.
- **Data and memory:** PostgreSQL `survival_mode_activations,mode_restrictions,mode_audit_events; active indefinite`.
- **Dependencies and permissions:** `risk.suspension,resource.budget,identity; deny discretionary work/new autonomous risk`.
- **Failure handling:** partial activation fails closed; uncertain data cannot relax.
- **Acceptance tests:** blocks new autonomous orders; unverified estimate alone cannot activate.
- **Status:** Planned.

### ASAI-130 — Financial death protocol
- **Purpose:** irreversibly stop trading on verified financial death.
- **Implementation:** Planned package/class `asai.survival.death.FinancialDeathProtocol.latch(evidence: DeathEvidence) -> DeathRecord`; no implementation is authorised by this specification.
- **Contract:** reconciled assets, liabilities, realistic liquidation costs and attestations -> the single canonical immutable PostgreSQL `governance_trading_latch` row for the identity with state `DEAD`; it blocks every new submission and amendment; cancellation is permitted only where safe and venue-supported; `survival.financial_death.latched.v1`.
- **Data and memory:** PostgreSQL `governance_trading_latch,death_records,death_evidence,dead_latch_events`; canonical latch and WORM audit are preserved indefinitely, subject to legal holds.
- **Dependencies and permissions:** `treasury.reconciliation,risk.suspension,identity; permanent deny with no unlatch, override, or liquidation authority`.
- **Failure handling:** stale/missing data suspends, cannot conclude death; no auto-refund, bypass, automatic live action, or liquidation. Any liquidation capability is future design only, requires a separate explicit policy change, and has no implementation under current policy.
- **Acceptance tests:** net equity below liabilities atomically creates the one canonical `DEAD` latch and blocks new submission/amendment; stale liability feed cannot latch; unsupported or unsafe cancellation is denied.
- **Status:** Planned.

## RESOURCE

### ASAI-131 — CPU monitoring
- **Purpose:** detect CPU saturation before critical degradation.
- **Implementation:** Proposed package/class `asai.resource.cpu.CpuMonitor.sample(host: HostRef) -> CpuSample`.
- **Contract:** authenticated counters/timestamp -> utilization,saturation,alert; `resource.cpu.sampled.v1`.
- **Data and memory:** PostgreSQL `cpu_samples,resource_alerts,resource_thresholds; raw 90d, rollups 2y`.
- **Dependencies and permissions:** `observability.agent; metrics-read only`.
- **Failure handling:** missing telemetry blocks discretionary expansion.
- **Acceptance tests:** 95% sustained alerts; counter reset is not negative usage.
- **Status:** Planned.

