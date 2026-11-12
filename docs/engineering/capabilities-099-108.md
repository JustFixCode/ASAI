# ASAI capabilities 099–108

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-099 — Correlation-based exposure control
- Purpose: Produce a traceable, paper-only correlation-adjusted paper exposure limits; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.correlationexposurecontroller`; class `CorrelationExposureController`; function signature `evaluate(request: CorrelationRequest, *, actor_id: UUID) -> CorrelationAdjustedpaperexposurelimitsresult`.
- Contract: Input `CorrelationRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `CorrelationBasedExposureControlCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_correlation_exposure, correlation_limit_breach` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `CorrelationRepository` is read-only; `audit.EventWriter` may append `CorrelationBasedExposureControlCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for non-PSD matrix or missing series; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) non-PSD matrix is rejected. (2) missing pair correlation flags unavailable.
- Status: Planned.

### ASAI-100 — Portfolio closure management
- Purpose: Produce a traceable, paper-only paper portfolio closure plan/status; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.portfolioclosuremanager`; class `PortfolioClosureManager`; function signature `close(request: ClosureRequest, *, actor_id: UUID) -> Paperportfolioclosureplan/StatusResult`.
- Contract: Input `ClosureRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PortfolioClosureManagementCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_portfolio_closure, closure_step` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `ApprovalService` is read-only; `audit.EventWriter` may append `PortfolioClosureManagementCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for open orders or absent approval; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) open paper order blocks closure. (2) second closure request is idempotent.
- Status: Planned.


## RISK

### ASAI-101 — Maximum-loss enforcement
- **Purpose:** deny orders whose stressed loss breaches ceiling.
- **Implementation:** Proposed package/class `asai.risk.loss.MaximumLossEnforcer.evaluate(intent: OrderIntent, snapshot: RiskSnapshot) -> LossDecision`.
- **Contract:** Decimal intent, verified marks, fees and slippage -> stressed loss and allow/deny; `risk.maximum_loss.checked.v1`.
- **Data and memory:** PostgreSQL `risk_limits,risk_evaluations,order_rejections; immutable snapshot FK, 7y`.
- **Dependencies and permissions:** `marketdata.snapshot,treasury.ledger,execution.intent; read and deny-intent only`.
- **Failure handling:** stale/unverified marks => SUSPEND, never assume safety.
- **Acceptance tests:** rejects loss plus fees over cap; stale mark denies nominally safe order.
- **Status:** Planned.

### ASAI-102 — Daily-loss protection
- **Purpose:** lock new exposure after daily loss budget.
- **Implementation:** Proposed package/class `asai.risk.daily.DailyLossGuard.assess(account_id: UUID, at: datetime) -> DailyLossDecision`.
- **Contract:** fills, fees, verified marks and trading-day boundary -> remaining budget/lock; `risk.daily_loss.locked.v1`.
- **Data and memory:** PostgreSQL `daily_loss_windows,daily_loss_components,risk_locks; unique ledger/date, 7y`.
- **Dependencies and permissions:** `treasury.ledger,marketdata.snapshot,risk.suspension; account-lock only`.
- **Failure handling:** clock ambiguity or duplicate fill locks pending reconciliation.
- **Acceptance tests:** realised loss plus fees crosses threshold; late correction cannot auto-unlock.
- **Status:** Planned.

### ASAI-103 — Position-risk calculation
- **Purpose:** measure each position under adverse scenarios.
- **Implementation:** Proposed package/class `asai.risk.position.PositionRiskCalculator.calculate(position: Position, scenarios: ScenarioSet) -> PositionRisk`.
- **Contract:** quantity, multiplier, mark and scenarios -> Decimal max loss/vector; `risk.position.calculated.v1`.
- **Data and memory:** PostgreSQL `position_risk_snapshots,risk_scenarios,market_snapshot_refs; hashes, 7y`.
- **Dependencies and permissions:** `positions,marketdata.snapshot,liquidity; read-only`.
- **Failure handling:** missing scenario or stale mark => UNKNOWN and block increase.
- **Acceptance tests:** futures multiplier is applied; stale bid/ask blocks increase.
- **Status:** Planned.

### ASAI-104 — Portfolio-risk calculation
- **Purpose:** measure aggregate exposure without implicit offsets.
- **Implementation:** Proposed package/class `asai.risk.portfolio.PortfolioRiskCalculator.calculate(portfolio: Portfolio, scenarios: ScenarioSet) -> PortfolioRisk`.
- **Contract:** positions, liabilities, correlations, liquidation curves -> stressed equity/breaches; `risk.portfolio.calculated.v1`.
- **Data and memory:** PostgreSQL `portfolio_risk_snapshots,portfolio_exposures,offset_approvals; 7y`.
- **Dependencies and permissions:** `positions,treasury.ledger,risk.correlation; publish breach only`.
- **Failure handling:** unpriced holding or unapproved offset suspends exposure.
- **Acceptance tests:** liabilities reduce stressed equity; unapproved pair is not netted.
- **Status:** Planned.

### ASAI-105 — Leverage restrictions
- **Purpose:** cap account and instrument leverage.
- **Implementation:** Proposed package/class `asai.risk.leverage.LeverageGuard.check(intent: OrderIntent, equity: Decimal) -> LeverageDecision`.
- **Contract:** gross notional, verified net liquidation equity, margin and policy -> projected ratio; `risk.leverage.checked.v1`.
- **Data and memory:** PostgreSQL `leverage_limits,leverage_checks,margin_snapshots; 7y`.
- **Dependencies and permissions:** `treasury.reconciliation,marketdata.snapshot,execution.intent; deny only`.
- **Failure handling:** nonpositive equity or unknown margin denies increase.
- **Acceptance tests:** fees/slippage breach gross cap; unrealised gain is not cash equity.
- **Status:** Planned.

### ASAI-106 — Drawdown protection
- **Purpose:** limit peak-to-trough net-liquidation drawdown.
- **Implementation:** Proposed package/class `asai.risk.drawdown.DrawdownGuard.update(equity: EquitySnapshot) -> DrawdownDecision`.
- **Contract:** reconciled equity after liabilities/liquidation cost -> tier/restriction; `risk.drawdown.updated.v1`.
- **Data and memory:** PostgreSQL `equity_snapshots,high_water_marks,drawdown_actions; monotonic, 7y`.
- **Dependencies and permissions:** `treasury.reconciliation,risk.suspension; tier restriction only`.
- **Failure handling:** stale equity cannot reset drawdown; suspend increase.
- **Acceptance tests:** exact threshold activates tier; out-of-order snapshot cannot lower peak.
- **Status:** Planned.

### ASAI-107 — Liquidity protection
- **Purpose:** ensure positions can exit inside impact bounds.
- **Implementation:** Proposed package/class `asai.risk.liquidity.LiquidityGuard.evaluate(intent: OrderIntent, book: OrderBook) -> LiquidityDecision`.
- **Contract:** size, depth, volume, spread and participation -> resize/deny and liquidation cost; `risk.liquidity.checked.v1`.
- **Data and memory:** PostgreSQL `liquidity_snapshots,liquidity_checks,impact_model_versions; 7y`.
- **Dependencies and permissions:** `marketdata.orderbook,positions; constrain quantity only`.
- **Failure handling:** one-sided/stale book denies new exposure.
- **Acceptance tests:** oversize order is resized; thin exit horizon is denied.
- **Status:** Planned.

### ASAI-108 — Volatility protection
- **Purpose:** reduce risk during volatility shocks.
- **Implementation:** Proposed package/class `asai.risk.volatility.VolatilityGuard.assess(instrument_id: UUID, series: PriceSeries) -> VolatilityDecision`.
- **Contract:** verified prices/implied vol -> annualised volatility/multiplier/halt; `risk.volatility.updated.v1`.
- **Data and memory:** PostgreSQL `volatility_observations,volatility_states,volatility_policy_versions; 7y`.
- **Dependencies and permissions:** `marketdata.snapshot,risk.suspension; no execution authority`.
- **Failure handling:** insufficient/discontinuous series => unknown and suspend increase.
- **Acceptance tests:** gap shock halts exposure; new listing is not zero volatility.
- **Status:** Planned.

