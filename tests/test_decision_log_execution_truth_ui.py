"""Static UI contracts for proposal, queue, and fill truth in the decision log."""

from pathlib import Path


HTML = (Path(__file__).resolve().parent.parent / "app" / "static" / "index.html").read_text()


def _slice(start: str, end: str) -> str:
    begin = HTML.index(start)
    return HTML[begin : HTML.index(end, begin)]


def test_decision_badges_distinguish_verified_fills_queue_rejection_and_unknown() -> None:
    presentation = _slice("function _decisionPresentation(d, isZh)",
                          "function _decisionActionChip(h, kind, isZh)")

    assert "EXECUTED / FILLED" in presentation
    assert "已执行 / 已成交" in presentation
    assert "QUEUED — NOT YET EXECUTED" in presentation
    assert "已排队 — 尚未执行" in presentation
    assert "NOT APPLIED / REJECTED" in presentation
    assert "未应用 / 已拒绝" in presentation
    assert "SETTLED — NO TRADE" in presentation
    assert "LEGACY EXECUTION — UNVERIFIED" in presentation
    assert "LEGACY STATUS UNKNOWN" in presentation

    # Accepted lifecycle states come from target_status; decision_effective is not fill proof.
    assert "targetStatus === 'queued'" in presentation
    assert "targetStatus !== 'executed'" in presentation
    assert "replace(/[^a-z0-9_-]/g, '')" in presentation
    assert "replace(/_/g, ' ')" in presentation
    assert "decision_effective" not in presentation


def test_only_execution_records_create_fill_chips() -> None:
    render = _slice("function renderDecisions()", "function _decisionPresentation(d, isZh)")
    presentation = _slice("function _decisionPresentation(d, isZh)",
                          "function _decisionActionChip(h, kind, isZh)")

    assert "var trades = truth.executed.map" in render
    assert "var recorded = Array.isArray(d.executed)" in presentation
    assert "evidenceStatus === 'receipt_verified'" in presentation
    assert "var executed = receiptVerified ? recorded : []" in presentation
    assert "executed: executed" in presentation
    assert "effective_holdings" not in render
    assert "d.executed || []" not in render


def test_queued_targets_and_rejected_proposals_cannot_look_owned() -> None:
    presentation = _slice("function _decisionPresentation(d, isZh)",
                          "function _decisionActionChip(h, kind, isZh)")
    actions = _slice("function _decisionActionChip(h, kind, isZh)",
                     "window.toggleDecisionLog")

    assert "Array.isArray(d.effective_holdings)" in presentation
    assert "Proposed target positions — not current holdings" in presentation
    assert "拟议目标仓位 — 非当前持仓" in presentation
    assert "Rejected proposal — audit only, not holdings" in presentation
    assert "已拒绝提案 — 仅供审计，并非持仓" in presentation
    assert "rows = proposed;" in presentation
    assert "PENDING ADD" in actions and "待加仓" in actions
    assert "EXISTING HOLD" in actions and "现有持仓" in actions


def test_legacy_decisions_degrade_without_claiming_a_fill() -> None:
    presentation = _slice("function _decisionPresentation(d, isZh)",
                          "function _decisionActionChip(h, kind, isZh)")

    assert "Array.isArray(d.executed)" in presentation
    assert "Array.isArray(d.holdings)" in presentation
    assert "Legacy decision snapshot — execution status unknown" in presentation
    assert "历史决策快照 — 执行状态未知" in presentation
    assert "neither fill evidence nor proof of no trade" in presentation


def test_zero_fill_receipt_is_settled_no_trade_and_settlement_date_is_shown() -> None:
    render = _slice("function renderDecisions()", "function _decisionPresentation(d, isZh)")
    presentation = _slice("function _decisionPresentation(d, isZh)",
                          "function _decisionActionChip(h, kind, isZh)")

    assert "receiptVerified && targetStatus === 'executed'" in presentation
    assert "SETTLED — NO TRADE" in presentation
    assert "required no buy or sell" in presentation
    assert "settledAsOf = d.settled_asof || null" in presentation
    assert "fmtDate(truth.settledAsOf)" in render
    actions = _slice("function _decisionActionChip(h, kind, isZh)",
                     "window.toggleDecisionLog")
    assert "kind === 'nochange'" in actions
    assert "NO TRADE / HOLD" in actions


def test_pending_invalid_and_unavailable_states_are_visible() -> None:
    notice = _slice("function _pendingTruthNoticeHtml()", "function _pendingOrdersHtml()")

    for value in (
        "status === 'invalid'",
        "status === 'unavailable'",
        "comparison === 'account_unavailable'",
        "comparison === 'prices_unavailable'",
        "comparison === 'transaction_pending'",
        "comparison === 'constraint_snapshot_mismatch'",
    ):
        assert value in notice
    assert "pend.invalid" in HTML
    assert "pend.account_unavailable" in HTML
    assert "pend.transaction_pending" in HTML


def test_pending_order_action_uses_backend_side_with_legacy_fallback() -> None:
    side = _slice("function _pendingOrderSide(o)", "function _pendingOrdersHtml()")
    pending = _slice("function _pendingOrdersHtml()", "function renderTrades()")

    assert "o.side || o.action" in side
    assert "return 'sell'" in side
    assert "return 'hold'" in side
    assert "return 'buy'" in side  # old pending-order rows did not persist a side
    assert "var side = _pendingOrderSide(o)" in pending
    assert 'mm-side-chip ' + "' + side + '" in pending
    assert "t('trades.hold')" in pending
    assert "t('pend.no_trade_lbl')" in pending
    assert "t('pend.awaiting_lbl')" in pending
    assert "o.fill_after ?" in pending
    assert '<span class="mm-side-chip buy">' not in pending
