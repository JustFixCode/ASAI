# ASAI capabilities 109–120

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-109 — Correlated-risk protection
- **Purpose:** cap common-factor concentration.
- **Implementation:** Proposed package/class `asai.risk.correlation.CorrelationGuard.evaluate(portfolio: Portfolio) -> CorrelationDecision`.
- **Contract:** notionals and approved matrix -> factor exposure/incremental cap; `risk.correlation.checked.v1`.
- **Data and memory:** PostgreSQL `correlation_models,factor_exposures,correlation_checks; checksums, 7y`.
- **Dependencies and permissions:** `positions,marketdata.reference,risk.portfolio; deny only`.
- **Failure handling:** expired/incomplete matrix prohibits increase.
- **Acceptance tests:** issuer-linked pair breaches cap; instrument absent from matrix is denied.
- **Status:** Planned.

### ASAI-110 — Emergency trading suspension
- **Purpose:** fail-close autonomous trading in emergencies.
- **Implementation:** Proposed package/class `asai.risk.suspension.EmergencySuspendor.activate(reason: SuspensionReason, scope: Scope) -> Suspension`.
- **Contract:** signed trigger/authorized request -> atomic scoped suspension; while active, every new submission and every amendment is denied; cancellation is permitted only where it is safe and the venue explicitly supports it; `risk.trading_suspended.v1`.
- **Data and memory:** PostgreSQL `trading_suspensions,suspension_events,operator_authorizations; active records indefinite`.
- **Dependencies and permissions:** `execution.gateway,identity; deny all new submissions and amendments; cancellation request only under the safe, venue-supported rule`.
- **Failure handling:** gate outage denies new submissions/amendments; conflicting resume remains suspended; uncertain cancellation support denies cancellation.
- **Acceptance tests:** queued new order and amendment are blocked after activation; safe venue-supported cancellation is forwarded, unsupported cancellation denied; single unauthorized resume rejected.
- **Status:** Planned.

## TREASURY

### ASAI-111 — Initial-capital registration
- **Purpose:** register verified starting funds in one ledger mode.
- **Implementation:** Proposed package/class `asai.treasury.capital.InitialCapitalRegistrar.register(request: CapitalRegistration) -> JournalBatch`.
- **Contract:** mode,currency,Decimal amount,evidence -> balanced capital journal; `treasury.initial_capital.registered.v1`.
- **Data and memory:** PostgreSQL `capital_registrations,journal_entries,ledger_accounts; evidence unique, 7y`.
- **Dependencies and permissions:** `treasury.ledger,identity; approved capital post only`.
- **Failure handling:** duplicate/unverified deposit posts nothing.
- **Acceptance tests:** paper registration never touches real ledger; evidence cannot be reused cross-mode.
- **Status:** Planned.

### ASAI-112 — Available-cash tracking
- **Purpose:** calculate conservative spendable cash.
- **Implementation:** Proposed package/class `asai.treasury.cash.AvailableCashCalculator.calculate(ledger_id: UUID) -> CashAvailability`.
- **Contract:** posted balances, settlement, reserve and limits -> available Decimal cash; `treasury.available_cash.calculated.v1`.
- **Data and memory:** PostgreSQL `cash_availability_snapshots,cash_encumbrances,reserve_allocations; 7y`.
- **Dependencies and permissions:** `treasury.ledger,treasury.reserve; read-only calculator`.
- **Failure handling:** unknown settlement/reconciliation => zero cash.
- **Acceptance tests:** excludes unrealised profit; excludes operating reserve.
- **Status:** Planned.

### ASAI-113 — Realised-profit accounting
- **Purpose:** post confirmed closing-fill P&L.
- **Implementation:** Proposed package/class `asai.treasury.pnl.RealisedPnlPoster.post(fill: ConfirmedFill) -> JournalBatch`.
- **Contract:** idempotent fill, costs, lot method -> matched closures and balanced journal; `treasury.realised_pnl.posted.v1`.
- **Data and memory:** PostgreSQL `tax_lots,lot_closures,journal_entries; external IDs, 7y`.
- **Dependencies and permissions:** `execution.confirmations,treasury.ledger; realised accounts only`.
- **Failure handling:** partial/duplicate fill held for reconciliation.
- **Acceptance tests:** FIFO sale splits two lots; duplicate fill posts once.
- **Status:** Planned.

### ASAI-114 — Unrealised-profit accounting
- **Purpose:** value open positions without creating cash.
- **Implementation:** Proposed package/class `asai.treasury.marking.UnrealisedPnlMarker.mark(position: Position, mark: VerifiedMark) -> JournalBatch`.
- **Contract:** open lot, verified mark, policy -> non-cash valuation journal; `treasury.unrealised_pnl.marked.v1`.
- **Data and memory:** PostgreSQL `valuation_marks,unrealised_pnl_entries,mark_policy_versions; 7y`.
- **Dependencies and permissions:** `marketdata.snapshot,treasury.ledger; valuation accounts only`.
- **Failure handling:** stale mark posts no gain and remains unknown.
- **Acceptance tests:** gain stays non-cash; expired source is rejected.
- **Status:** Planned.

### ASAI-115 — Fee accounting
- **Purpose:** accrue and reconcile all activity fees.
- **Implementation:** Proposed package/class `asai.treasury.fees.FeePoster.post(fee: FeeNotice) -> JournalBatch`.
- **Contract:** fee ID,currency,linked event,amount -> classified balanced journal; `treasury.fee.posted.v1`.
- **Data and memory:** PostgreSQL `fee_notices,fee_allocations,journal_entries; provider ID unique, 7y`.
- **Dependencies and permissions:** `execution.confirmations,treasury.ledger; fee accounts only`.
- **Failure handling:** unknown/unmatched fee goes suspense.
- **Acceptance tests:** commission allocates across partial fills; changed duplicate is quarantined.
- **Status:** Planned.

### ASAI-116 — Expense accounting
- **Purpose:** record approved operating expenses without unauthorized payment.
- **Implementation:** Proposed package/class `asai.treasury.expenses.ExpensePoster.record(invoice: ApprovedInvoice) -> JournalBatch`.
- **Contract:** invoice,vendor,budget,approval,limit -> expense/payable; `treasury.expense.recorded.v1`.
- **Data and memory:** PostgreSQL `vendor_invoices,expense_approvals,payables,journal_entries; hash unique, 7y`.
- **Dependencies and permissions:** `identity,treasury.ledger,treasury.cash; record payable only`.
- **Failure handling:** missing approval/over-limit creates no payment instruction.
- **Acceptance tests:** over-limit invoice rejected; recording does not move cash.
- **Status:** Planned.

### ASAI-117 — Deposit tracking
- **Purpose:** track inbound funding to verification.
- **Implementation:** Proposed package/class `asai.treasury.deposits.DepositTracker.observe(event: BankCredit) -> DepositState`.
- **Contract:** external ID,account,currency,amount,evidence -> pending/verified/rejected; `treasury.deposit.verified.v1`.
- **Data and memory:** PostgreSQL `deposits,deposit_evidence,reconciliation_links; provider ID unique, 7y`.
- **Dependencies and permissions:** `bank.ingest,treasury.capital; read feed/request approved post`.
- **Failure handling:** ambiguous sender/reversal remains unavailable.
- **Acceptance tests:** pending credit is not capital; reversal removes availability.
- **Status:** Planned.

### ASAI-118 — Withdrawal tracking
- **Purpose:** track authorized outbound withdrawals.
- **Implementation:** Proposed package/class `asai.treasury.withdrawals.WithdrawalTracker.request(request: WithdrawalRequest) -> WithdrawalState`.
- **Contract:** beneficiary,amount,limit,approvals,mode -> requested/settled state; `treasury.withdrawal.requested.v1`.
- **Data and memory:** PostgreSQL `withdrawals,beneficiaries,withdrawal_approvals,cash_encumbrances; 7y`.
- **Dependencies and permissions:** `treasury.cash,identity,bank.payment; within-limit instruction only`.
- **Failure handling:** insufficient cash or changed beneficiary rejects.
- **Acceptance tests:** unrealised-funded withdrawal rejected; post-approval beneficiary change holds.
- **Status:** Planned.

### ASAI-119 — Double-entry accounting
- **Purpose:** preserve segregated balanced journals.
- **Implementation:** Proposed package/class `asai.treasury.ledger.JournalPoster.post(batch: JournalBatch) -> PostedBatch`.
- **Contract:** idempotency key,mode,dated Decimal lines -> posted batch; `treasury.journal.posted.v1`.
- **Data and memory:** PostgreSQL `ledgers,chart_of_accounts,journal_batches,journal_entries; separate simulated/paper/real, 7y`.
- **Dependencies and permissions:** `identity,PostgreSQL transaction module; source-scoped post`.
- **Failure handling:** imbalance/mixed-mode rolls back batch.
- **Acceptance tests:** one-cent imbalance rejected; paper/real mix rejected.
- **Status:** Planned.

### ASAI-120 — Independent balance reconciliation
- **Purpose:** verify internal balances against external statements.
- **Implementation:** Proposed package/class `asai.treasury.reconciliation.BalanceReconciler.reconcile(source: ExternalStatement) -> ReconciliationResult`.
- **Contract:** statement and internal as-of balance -> matched/break/unverified; `treasury.reconciliation.completed.v1`.
- **Data and memory:** PostgreSQL `external_statements,reconciliation_runs,reconciliation_breaks,evidence_blobs; checksums, 7y`.
- **Dependencies and permissions:** `bank.ingest,venue.ingest,treasury.ledger; flag only`.
- **Failure handling:** stale/malformed/unmatched source fails closed.
- **Acceptance tests:** fee variance detected; old statement cannot verify balance.
- **Status:** Planned.

## SURVIVAL

