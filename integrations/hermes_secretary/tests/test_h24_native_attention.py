"""H24-03 static adapter fixtures: no Hermes import, credentials or activation."""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from control_plane.wake_events import SourceKind, mint_obligation, parse_obligation
from integrations.hermes_secretary import native_attention_boundary as boundary
from integrations.hermes_secretary.native_attention_boundary import (
    AttentionProjection, BUILD_BASE, CurrentAttention, EffectEvidence, EffectState,
    Eligibility, HERMES_PIN, NativeBinding, NativeKind, NativeObservation,
    NativeOccurrence, ObservationMode, ProjectionStatus, ROUTINE_ROUTES,
    occurrence_key, project_native_attention,
)


NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
SESSION = "00000000-0000-4000-8000-000000024003"
NEXT_SESSION = "00000000-0000-4000-8000-000000024004"
BINDING = NativeBinding("fixture-secretary", "mmsecretary", "JOB-24003", SESSION,
                        7, BUILD_BASE, "America/Cancun")


def stamp(seconds: int = 0) -> str:
    return (NOW + timedelta(seconds=seconds)).isoformat()


# Actual pinned HookRegistry context shape. None of this message/response text
# conveys authentication, current role, event sequence or canonical attention.
HOOK_FIXTURE = {
    "event_type": "agent:end",
    "context": {"platform": "slack", "user_id": "fixture-user", "chat_id": "fixture-room",
                "thread_id": "", "chat_type": "group", "session_id": SESSION,
                "message": "Status only", "response": "No change",
                "model": "fixture-no-model", "provider": "fixture-no-provider"},
}
# Selected actual cron.executions row fields; scheduled_instant is the native
# persisted UTC slot, NOT a next_run_at recomputation or local cron expression.
CRON_FIXTURE = {
    "id": "a" * 32, "job_id": "native-job-7", "source": "builtin",
    "process_id": "b" * 32, "pid": 1234, "status": "completed",
    "scheduled_instant": stamp(-60), "claimed_at": stamp(-60),
    "started_at": stamp(-59), "finished_at": stamp(-2),
}


class StaticOwner:
    """Explicit no-network test double, NOT an installed authentication adapter.

    Only the exact fixture object is authenticated; copied/spoofed payloads are
    refused. Current source/role/effect evidence is supplied separately.
    """
    def __init__(self, *, cron: bool = False):
        self.notice = dict(CRON_FIXTURE if cron else HOOK_FIXTURE)
        event = NativeOccurrence(
            NativeKind.CRON if cron else NativeKind.HOOK,
            CRON_FIXTURE["id"] if cron else "native-event-7",
            BINDING, "cron:occurrence" if cron else "agent:end", 19,
            stamp(-60), stamp(3600),
            "slack-secretary-ping-scan" if cron else None,
            CRON_FIXTURE["job_id"] if cron else None,
            CRON_FIXTURE["scheduled_instant"] if cron else None,
        )
        self.observation = NativeObservation(ObservationMode.EVENT, BINDING, event, stamp(-1))
        attention = mint_obligation(
            source_kind="agent_dialogue_attention", source_ref="agent_dialogue_attention:" + "c" * 64,
            wake_kind="dialogue_turn_pending", declared_target_seat="ceo",
            root_job_id=BINDING.original_root, workstream="executive",
            source_workstream="WS:H24-03", source_created_at=stamp(-90), emitted_at=stamp(-1),
        )
        self.current = CurrentAttention(
            BINDING, event, 21, 31, 35, stamp(), stamp(180),
            Eligibility.ELIGIBLE, Eligibility.ELIGIBLE, Eligibility.ELIGIBLE,
            attention, EffectEvidence(attention.obligation_id, EffectState.ABSENT, None, None),
            native_execution_status="completed" if cron else None,
        )
        self.auth_reads = 0
        self.current_reads = 0

    def authenticate(self, notice: object):
        self.auth_reads += 1
        return self.observation if notice is self.notice else None

    def read_current(self, observation: NativeObservation):
        self.current_reads += 1
        return self.current

    def set_occurrence(self, **changes):
        event = replace(self.observation.occurrence, **changes)
        self.observation = replace(self.observation, occurrence=event)
        self.current = replace(self.current, retained_occurrence=event,
                               native_watermark=max(self.current.native_watermark, event.event_sequence))
        return event

    def set_attention(self, attention):
        self.current = replace(self.current, attention=attention,
                               effect=EffectEvidence(attention.obligation_id, EffectState.ABSENT, None, None))

    def set_effect(self, state: EffectState, *, original=None):
        oid = self.current.attention.obligation_id
        command = oid if state is EffectState.REQUESTED else oid + ":A1"
        self.current = replace(self.current, effect=EffectEvidence(
            oid, state, original or self.observation.occurrence, command))


class NativeAttentionTests(unittest.TestCase):
    def project(self, owner=None, *, binding=BINDING, notice=None, now=NOW):
        owner = owner or StaticOwner()
        result = project_native_attention(owner.notice if notice is None else notice,
                                          source=owner, binding=binding, now=now)
        self.assertIsInstance(result, AttentionProjection)
        self.assertFalse(result.new_cognition)
        self.assertFalse(result.new_submission)
        return result

    def assert_status(self, result, status, reason=None):
        self.assertEqual(result.status, status)
        if reason:
            self.assertEqual(result.reason, reason)
        if status is not ProjectionStatus.PROPOSED:
            self.assertIsNone(result.proposed_obligation)

    def test_present_owner_verified_attention_proposes_one_incumbent_id(self):
        owner = StaticOwner()
        result = self.project(owner)
        self.assert_status(result, ProjectionStatus.PROPOSED, "OWNER_VERIFIED_ATTENTION")
        self.assertEqual(result.proposed_obligation.obligation_id, owner.current.attention.obligation_id)
        self.assertEqual(parse_obligation(result.proposed_obligation.to_dict()), result.proposed_obligation)
        self.assertEqual((owner.auth_reads, owner.current_reads), (1, 1))
        self.assertEqual(result.observed_occurrence, owner.observation.occurrence)

    def test_actual_cron_row_identity_is_retained(self):
        owner = StaticOwner(cron=True)
        result = self.project(owner)
        self.assert_status(result, ProjectionStatus.PROPOSED)
        self.assertEqual(result.observed_occurrence.occurrence_id, CRON_FIXTURE["id"])
        self.assertEqual(result.evidence.occurrence_key,
                         ("hermes_cron", BINDING.profile_id, CRON_FIXTURE["job_id"], CRON_FIXTURE["scheduled_instant"]))

    def test_duplicate_observation_coalesces_on_canonical_source(self):
        owner = StaticOwner()
        first = self.project(owner)
        owner.current = replace(owner.current, previous=first.evidence)
        self.assert_status(self.project(owner), ProjectionStatus.NO_CHANGE, "SEMANTIC_SNAPSHOT_UNCHANGED")

    def test_later_cron_occurrence_same_attention_is_no_change(self):
        owner = StaticOwner(cron=True)
        first = self.project(owner)
        owner.current = replace(owner.current, previous=first.evidence)
        owner.set_occurrence(occurrence_id="d" * 32, event_sequence=20, scheduled_instant=stamp(-30))
        result = self.project(owner)
        self.assertNotEqual(first.evidence.occurrence_key, result.evidence.occurrence_key)
        self.assert_status(result, ProjectionStatus.NO_CHANGE, "SEMANTIC_SNAPSHOT_UNCHANGED")

    def test_observation_and_display_time_changes_do_not_spend_cognition(self):
        owner = StaticOwner()
        initial = self.project(owner)
        owner.current = replace(owner.current, previous=initial.evidence,
                                attention=replace(owner.current.attention, emitted_at=stamp()))
        owner.observation = replace(owner.observation, observed_at=stamp())
        result = self.project(owner)
        self.assert_status(result, ProjectionStatus.NO_CHANGE)
        self.assertEqual(initial.evidence.fingerprint, result.evidence.fingerprint)

    def test_delayed_still_current_event_is_eligible(self):
        owner = StaticOwner()
        owner.set_occurrence(occurred_at=stamp(-3600))
        self.assert_status(self.project(owner), ProjectionStatus.PROPOSED)

    def test_old_event_after_current_resolution_proposes_nothing(self):
        owner = StaticOwner()
        owner.current = replace(owner.current, work_eligibility=Eligibility.INELIGIBLE,
                                native_watermark=90, source_watermark=90)
        self.assert_status(self.project(owner), ProjectionStatus.INELIGIBLE)

    def test_reordered_event_cannot_replace_retained_native_occurrence(self):
        owner = StaticOwner()
        owner.observation = replace(owner.observation, occurrence=replace(
            owner.observation.occurrence, event_sequence=18, occurrence_id="older-native-event"))
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "ORIGINAL_OCCURRENCE_MISMATCH")

    def test_missed_event_recovers_from_newer_source_snapshot(self):
        owner = StaticOwner()
        original = owner.observation.occurrence
        owner.observation = replace(owner.observation, mode=ObservationMode.SOURCE_SNAPSHOT)
        owner.current = replace(owner.current, native_watermark=300, source_watermark=400)
        result = self.project(owner)
        self.assert_status(result, ProjectionStatus.PROPOSED)
        self.assertEqual(result.observed_occurrence, original)
        self.assertEqual(result.observed_occurrence.event_sequence, 19)

    def test_restart_recovery_preserves_origin_and_canonical_id(self):
        before = StaticOwner(cron=True)
        first = self.project(before)
        current_binding = replace(BINDING, session_id=NEXT_SESSION, session_generation=8)
        restarted = StaticOwner(cron=True)
        restarted.observation = replace(restarted.observation, mode=ObservationMode.SOURCE_SNAPSHOT,
                                         binding=current_binding)
        restarted.current = replace(restarted.current, binding=current_binding)
        result = self.project(restarted, binding=current_binding)
        self.assert_status(result, ProjectionStatus.PROPOSED)
        self.assertEqual(result.proposed_obligation.obligation_id, first.proposed_obligation.obligation_id)
        self.assertEqual(result.observed_occurrence, first.observed_occurrence)
        self.assertEqual(result.observed_occurrence.origin.session_generation, 7)

    def test_restart_with_prior_wake_request_does_not_propose_again(self):
        owner = StaticOwner()
        owner.set_effect(EffectState.REQUESTED)
        owner.current = replace(owner.current, previous=None)
        result = self.project(owner)
        self.assert_status(result, ProjectionStatus.NO_CHANGE, "ORIGINAL_EFFECT_ALREADY_ADMITTED")
        self.assertEqual(result.original_effect.command_id, owner.current.attention.obligation_id)

    def test_old_hook_generation_is_rejected_even_when_authenticated(self):
        owner = StaticOwner()
        newer = replace(BINDING, session_generation=8, session_id=NEXT_SESSION)
        owner.observation = replace(owner.observation, binding=newer)
        owner.current = replace(owner.current, binding=newer)
        self.assert_status(self.project(owner, binding=newer), ProjectionStatus.REJECTED, "STALE_SESSION_GENERATION")

    def test_snapshot_cannot_claim_future_generation(self):
        owner = StaticOwner()
        owner.set_occurrence(origin=replace(BINDING, session_generation=8))
        owner.observation = replace(owner.observation, mode=ObservationMode.SOURCE_SNAPSHOT)
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "FUTURE_SESSION_GENERATION")

    def test_unknown_and_possible_send_preserve_original_effect_after_new_fire(self):
        for state in (EffectState.POSSIBLE_SEND, EffectState.UNKNOWN):
            with self.subTest(state=state):
                owner = StaticOwner(cron=True)
                original = owner.observation.occurrence
                owner.set_effect(state)
                effect = owner.current.effect
                owner.set_occurrence(occurrence_id="e" * 32, event_sequence=22,
                                     scheduled_instant=stamp(-10))
                result = self.project(owner)
                self.assert_status(result, ProjectionStatus.RECONCILE_REQUIRED, "ORIGINAL_EFFECT_UNKNOWN")
                self.assertIs(result.original_effect, effect)
                self.assertEqual(result.original_effect.original_occurrence, original)
                self.assertEqual(result.original_effect.command_id, effect.command_id)

    def test_unknown_native_execution_requires_native_reconcile(self):
        owner = StaticOwner(cron=True)
        owner.current = replace(owner.current, native_execution_status="unknown")
        result = self.project(owner)
        self.assert_status(result, ProjectionStatus.RECONCILE_REQUIRED, "NATIVE_CRON_EFFECT_UNKNOWN")
        self.assertEqual(result.observed_occurrence.occurrence_id, CRON_FIXTURE["id"])

    def test_restart_and_changed_source_build_do_not_rekey_unknown_send(self):
        owner = StaticOwner(cron=True)
        owner.set_effect(EffectState.UNKNOWN)
        original = owner.current.effect
        next_binding = replace(BINDING, session_generation=8, session_id=NEXT_SESSION,
                               source_revision="d" * 40)
        owner.observation = replace(owner.observation, mode=ObservationMode.SOURCE_SNAPSHOT,
                                    binding=next_binding)
        owner.current = replace(owner.current, binding=next_binding)
        result = self.project(owner, binding=next_binding)
        self.assert_status(result, ProjectionStatus.RECONCILE_REQUIRED, "ORIGINAL_EFFECT_UNKNOWN")
        self.assertIs(result.original_effect, original)
        self.assertEqual(result.original_effect.original_occurrence.origin, BINDING)

    def test_origin_identity_never_uses_reconnecting_session_generation(self):
        owner = StaticOwner()
        origin = owner.observation.occurrence
        key = occurrence_key(origin)
        self.assertIn(BINDING.original_root, key)
        self.assertIn(BINDING.session_id, key)
        self.assertIn(str(origin.event_sequence), key)
        changed = replace(origin, origin=replace(BINDING, session_generation=8))
        self.assertNotEqual(key, occurrence_key(changed))

    def test_requested_delivered_and_resolved_are_not_new_submissions(self):
        for state in (EffectState.REQUESTED, EffectState.DELIVERED, EffectState.RESOLVED):
            with self.subTest(state=state):
                owner = StaticOwner()
                owner.set_effect(state)
                self.assert_status(self.project(owner), ProjectionStatus.NO_CHANGE)

    def test_unreadable_effect_is_not_absence_even_without_local_history(self):
        owner = StaticOwner()
        owner.current = replace(owner.current, effect=None, previous=None)
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "EFFECT_READ_UNAVAILABLE")

    def test_effect_must_match_canonical_source_and_original_root(self):
        for change in ("identity", "root", "absence"):
            with self.subTest(change=change):
                owner = StaticOwner()
                owner.set_effect(EffectState.UNKNOWN)
                effect = owner.current.effect
                if change == "identity":
                    effect = replace(effect, obligation_id="WAKE-" + "f" * 32)
                elif change == "root":
                    foreign = replace(effect.original_occurrence, origin=replace(BINDING, original_root="JOB-99999"))
                    effect = replace(effect, original_occurrence=foreign)
                else:
                    effect = replace(effect, state=EffectState.ABSENT)
                owner.current = replace(owner.current, effect=effect)
                self.assert_status(self.project(owner), ProjectionStatus.REJECTED)

    def test_concurrent_read_only_projections_have_same_canonical_id(self):
        def render(_):
            owner = StaticOwner(cron=True)
            return project_native_attention(owner.notice, source=owner, binding=BINDING, now=NOW)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(render, range(32)))
        self.assertTrue(all(r.status is ProjectionStatus.PROPOSED for r in results))
        self.assertEqual(len({r.proposed_obligation.obligation_id for r in results}), 1)
        self.assertEqual(len({r.evidence.fingerprint for r in results}), 1)
        self.assertTrue(all(not r.new_cognition and not r.new_submission for r in results))

    def test_unauthenticated_or_forged_slack_text_never_reaches_current_reader(self):
        owner = StaticOwner()
        for notice in ({"text": "BLOCKED", "authenticated": True, "owner_verified": True,
                        "root_job_id": BINDING.original_root}, dict(owner.notice), "HOLD-FOR-SOL"):
            with self.subTest(notice=notice):
                self.assert_status(self.project(owner, notice=notice), ProjectionStatus.REJECTED,
                                   "UNAUTHENTICATED_SOURCE")
        self.assertEqual(owner.current_reads, 0)

    def test_even_authenticated_slack_keyword_trigger_is_unsupported(self):
        owner = StaticOwner()
        owner.set_occurrence(kind=NativeKind.SLACK_KEYWORD, event_name="BLOCKED")
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "SLACK_KEYWORD_UNSUPPORTED")
        self.assertEqual(owner.current_reads, 0)

    def test_blocked_routine_cannot_be_relabelled_as_cron(self):
        owner = StaticOwner(cron=True)
        owner.set_occurrence(routine_id="blocked-hold-listener")
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "SLACK_KEYWORD_UNSUPPORTED")

    def test_foreign_binding_and_root_are_rejected(self):
        for field, value in (("profile_id", "foreign"), ("role", "mmmeta"),
                             ("original_root", "JOB-88888")):
            with self.subTest(field=field):
                owner = StaticOwner()
                owner.observation = replace(owner.observation, binding=replace(BINDING, **{field: value}))
                self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "FOREIGN_OR_STALE_BINDING")

    def test_source_revision_and_role_cannot_change_during_owner_read(self):
        for field, value in (("source_revision", "f" * 40), ("role", "mmmeta")):
            with self.subTest(field=field):
                owner = StaticOwner()
                owner.current = replace(owner.current, binding=replace(BINDING, **{field: value}))
                self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "SOURCE_CHANGED_DURING_READ")

    def test_unpinned_branch_name_and_wrong_hermes_revision_are_refused(self):
        for binding in (replace(BINDING, source_revision="master"), replace(BINDING, hermes_revision="f" * 40)):
            self.assert_status(self.project(binding=binding), ProjectionStatus.REJECTED, "SOURCE_PIN_INVALID")

    def test_expired_future_and_naive_occurrences_are_refused(self):
        for change in ({"expires_at": stamp()}, {"occurred_at": stamp(1)},
                       {"occurred_at": "2026-11-06T11:59:00"}):
            with self.subTest(change=change):
                owner = StaticOwner()
                owner.set_occurrence(**change)
                self.assert_status(self.project(owner), ProjectionStatus.REJECTED)

    def test_stale_observation_and_stale_snapshot_are_refused(self):
        owner = StaticOwner()
        owner.set_occurrence(occurred_at=stamp(-900))
        owner.observation = replace(owner.observation, observed_at=stamp(-600))
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "OBSERVATION_STALE")
        owner = StaticOwner()
        owner.current = replace(owner.current, expires_at=stamp())
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "CURRENT_SOURCE_STALE_OR_FUTURE")

    def test_unbounded_snapshot_ttl_and_backdated_read_are_refused(self):
        for change in ({"expires_at": stamp(301)}, {"read_at": stamp(-10)}, {"read_at": stamp(1)}):
            owner = StaticOwner()
            owner.current = replace(owner.current, **change)
            self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "CURRENT_SOURCE_STALE_OR_FUTURE")

    def test_missing_or_nonpositive_sequences_are_refused(self):
        for change in ({"native_watermark": 18}, {"source_event_sequence": True},
                       {"source_event_sequence": 0}, {"source_watermark": 30}):
            owner = StaticOwner()
            owner.current = replace(owner.current, **change)
            self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "EVENT_SEQUENCE_UNVERIFIED")

    def test_current_work_runtime_and_role_eligibility_all_required(self):
        for field in ("role_qualified", "work_eligibility", "runtime_eligibility"):
            for state, status in ((Eligibility.INELIGIBLE, ProjectionStatus.INELIGIBLE),
                                  (Eligibility.UNKNOWN, ProjectionStatus.REJECTED)):
                with self.subTest(field=field, state=state):
                    owner = StaticOwner()
                    owner.current = replace(owner.current, **{field: state})
                    self.assert_status(self.project(owner), status)

    def test_no_attention_no_reconnect_cognition(self):
        owner = StaticOwner()
        owner.current = replace(owner.current, attention=None, effect=None)
        owner.observation = replace(owner.observation, mode=ObservationMode.SOURCE_SNAPSHOT)
        self.assert_status(self.project(owner), ProjectionStatus.INELIGIBLE, "NO_CANONICAL_ATTENTION")
        self.assertEqual(owner.current_reads, 1)

    def test_ineligible_observation_cannot_cache_away_later_eligible_attention(self):
        owner = StaticOwner()
        owner.current = replace(owner.current, work_eligibility=Eligibility.INELIGIBLE)
        held = self.project(owner)
        self.assert_status(held, ProjectionStatus.INELIGIBLE)
        self.assertIsNone(held.evidence)
        owner.current = replace(owner.current, work_eligibility=Eligibility.ELIGIBLE,
                                previous=held.evidence)
        self.assert_status(self.project(owner), ProjectionStatus.PROPOSED)

    def test_valid_runtime_attention_preserves_exact_event_sequence(self):
        owner = StaticOwner()
        attention = mint_obligation(
            source_kind="executive_runtime_event", source_ref="runtime:job:JOB-24004:31",
            wake_kind="review_required", declared_target_seat="ceo", job_id="JOB-24004",
            root_job_id=BINDING.original_root, source_created_at=stamp(-90), emitted_at=stamp(-1),
        )
        owner.set_attention(attention)
        self.assert_status(self.project(owner), ProjectionStatus.PROPOSED)
        owner.current = replace(owner.current, source_event_sequence=32)
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "CANONICAL_EVENT_SEQUENCE_MISMATCH")

    def test_valid_inbox_attention_remains_incumbent_schema(self):
        owner = StaticOwner()
        owner.set_attention(mint_obligation(
            source_kind="executive_inbox_attention", source_ref="eia-0123456789ab",
            wake_kind="job_failed", declared_target_seat="ceo", job_id="JOB-24004",
            root_job_id=BINDING.original_root, source_created_at=stamp(-90), emitted_at=stamp(-1),
        ))
        self.assert_status(self.project(owner), ProjectionStatus.PROPOSED)

    def test_forged_wake_id_and_foreign_canonical_root_fail_schema(self):
        for change in ({"obligation_id": "WAKE-" + "f" * 32}, {"root_job_id": "JOB-88888"}):
            owner = StaticOwner()
            owner.current = replace(owner.current, attention=replace(owner.current.attention, **change))
            self.assert_status(self.project(owner), ProjectionStatus.REJECTED)

    def test_same_occurrence_source_with_changed_meaning_is_conflict(self):
        owner = StaticOwner()
        initial = self.project(owner)
        owner.current = replace(owner.current, previous=initial.evidence,
                                attention=replace(owner.current.attention, declared_target_seat="coo"))
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "OCCURRENCE_SOURCE_CONFLICT")

    def test_different_canonical_source_is_not_suppressed_by_same_text(self):
        owner = StaticOwner()
        first = self.project(owner)
        owner.current = replace(owner.current, previous=first.evidence)
        fields = owner.current.attention.to_dict()
        fields.pop("schema")
        fields.pop("obligation_id")
        fields["source_ref"] = "agent_dialogue_attention:" + "d" * 64
        fields.pop("evidence_refs")
        owner.set_attention(mint_obligation(**fields))
        result = self.project(owner)
        self.assert_status(result, ProjectionStatus.PROPOSED)
        self.assertNotEqual(result.proposed_obligation.obligation_id, first.proposed_obligation.obligation_id)

    def test_dst_repeated_hour_uses_actual_native_utc_instants(self):
        owner = StaticOwner(cron=True)
        first = owner.set_occurrence(scheduled_instant="2026-11-01T01:30:00-06:00")
        second = replace(first, occurrence_id="f" * 32, scheduled_instant="2026-11-01T01:30:00-07:00")
        self.assertNotEqual(occurrence_key(first), occurrence_key(second))
        self.assertEqual(occurrence_key(first)[-1], "2026-11-01T07:30:00+00:00")
        self.assertEqual(occurrence_key(second)[-1], "2026-11-01T08:30:00+00:00")
        # A second native occurrence alone does not change canonical attention.
        initial = self.project(owner)
        owner.current = replace(owner.current, previous=initial.evidence)
        owner.set_occurrence(occurrence_id=second.occurrence_id, scheduled_instant=second.scheduled_instant)
        self.assert_status(self.project(owner), ProjectionStatus.NO_CHANGE)

    def test_profile_timezone_difference_never_recalculates_schedule(self):
        owner = StaticOwner(cron=True)
        first = self.project(owner)
        instant = datetime.fromisoformat(CRON_FIXTURE["scheduled_instant"])
        for zone in ("America/Cancun", "America/Denver", "America/Los_Angeles"):
            with self.subTest(zone=zone):
                owner.set_occurrence(scheduled_instant=instant.astimezone(ZoneInfo(zone)).isoformat())
                result = self.project(owner)
                self.assert_status(result, ProjectionStatus.PROPOSED)
                self.assertEqual(result.evidence.occurrence_key, first.evidence.occurrence_key)
                self.assertEqual(result.proposed_obligation.obligation_id, first.proposed_obligation.obligation_id)

    def test_naive_cron_slot_or_synthetic_execution_id_is_refused(self):
        for change in ({"scheduled_instant": "2026-11-01T01:30:00"},
                       {"occurrence_id": "slack-ts-123.45"}, {"cron_job_id": None}):
            owner = StaticOwner(cron=True)
            owner.set_occurrence(**change)
            self.assert_status(self.project(owner), ProjectionStatus.REJECTED)

    def test_all_seven_routes_match_inert_catalog(self):
        path = Path(__file__).parents[1] / "routines" / "jobs.json"
        before = path.read_bytes()
        catalog = json.loads(before)
        routes = {r.routine_id: r for r in ROUTINE_ROUTES}
        self.assertEqual(len(routes), 7)
        self.assertFalse(catalog["installed"])
        self.assertEqual(catalog["hermes_pin"], HERMES_PIN)
        for job in catalog["jobs"]:
            with self.subTest(routine=job["id"]):
                route = routes[job["id"]]
                self.assertEqual(route.native_schedule, job["hermes_schedule"])
                self.assertFalse(job["enabled"])
                self.assertEqual(job["state"], "paused")
                self.assertEqual(route.wake_source is not None,
                                 job["wake_binding"]["obligation"] is not None and route.supported)
        self.assertEqual(path.read_bytes(), before)

    def test_four_eligible_routines_and_two_nonwake_routines(self):
        for route in ROUTINE_ROUTES:
            if not route.supported:
                continue
            with self.subTest(routine=route.routine_id):
                owner = StaticOwner(cron=True)
                owner.set_occurrence(routine_id=route.routine_id)
                expected = ProjectionStatus.PROPOSED if route.wake_source else ProjectionStatus.INELIGIBLE
                self.assert_status(self.project(owner), expected)

    def test_routine_cannot_promote_non_dialogue_attention(self):
        owner = StaticOwner(cron=True)
        owner.set_attention(mint_obligation(
            source_kind="executive_inbox_attention", source_ref="eia-0123456789ab",
            wake_kind="job_failed", declared_target_seat="ceo", root_job_id=BINDING.original_root,
            source_created_at=stamp(-90), emitted_at=stamp(-1),
        ))
        self.assert_status(self.project(owner), ProjectionStatus.REJECTED, "ROUTINE_SOURCE_MISMATCH")

    def test_adapter_errors_are_closed_bounded_and_sanitized(self):
        owner = StaticOwner()
        with patch.object(owner, "authenticate", side_effect=RuntimeError("private-auth-detail")) as read:
            result = self.project(owner)
            self.assert_status(result, ProjectionStatus.REJECTED, "AUTH_SOURCE_UNAVAILABLE")
            read.assert_called_once()
        with patch.object(owner, "read_current", side_effect=RuntimeError("private-source-detail")) as read:
            result = self.project(owner)
            self.assert_status(result, ProjectionStatus.REJECTED, "CURRENT_SOURCE_UNAVAILABLE")
            read.assert_called_once()
        self.assertNotIn("private", repr(result))

    def test_projection_performs_no_file_or_process_mutation(self):
        owner = StaticOwner()
        with patch("builtins.open", side_effect=AssertionError("unexpected IO")), \
             patch("pathlib.Path.write_text", side_effect=AssertionError("unexpected write")), \
             patch("subprocess.Popen", side_effect=AssertionError("unexpected process")):
            self.assert_status(self.project(owner), ProjectionStatus.PROPOSED)

    def test_boundary_imports_only_stdlib_and_pure_wake_schema(self):
        tree = ast.parse(Path(boundary.__file__).read_text())
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module)
        self.assertLessEqual(modules, {"__future__", "dataclasses", "datetime", "enum",
                                      "hashlib", "re", "typing", "uuid", "zoneinfo",
                                      "control_plane.wake_events"})


if __name__ == "__main__":
    unittest.main()
