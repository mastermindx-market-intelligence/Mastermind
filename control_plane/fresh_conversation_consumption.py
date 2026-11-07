"""Read-only same-original Keep recovery, independent of any turn request."""
from common import fresh_conversation_contract as wire


def read_consumption(owner, principal, request):
    owner._current(principal, read_only=True)
    reference = request.get("reference")
    if reference is None:
        from control_plane.fresh_conversation_turn import _original_root
        from control_plane.fresh_conversation_reference import _reference
        from control_plane.fresh_conversation_admission import read_creation_restriction
        root = _original_root(owner, principal, request)
        material = read_creation_restriction(owner._runtime, root)
        creation = owner._runtime.store.unique_root_created_event(root.job_id)
        reference = _reference(root, creation, material)
    window = owner.read_reference(principal, reference)
    initial = window["initial_result"]
    if (window["reference"]["work_ref"] != request["work_ref"] or initial is None
            or initial["digest"] != request["initial_digest"]):
        raise ValueError("CONVERSATION_INITIAL_RESULT_CHANGED")
    consumption = window["initial_consumption"]
    owner._current(principal, read_only=True)
    # ABSENT means no matching immutable receipt was observed NOW. It never
    # clears an attempted Keep pointer or authorizes reconsume/resend.
    value = dict(schema="mastermind.executive.fresh_conversation_turn_data.v1",
        work_ref=request["work_ref"], operation_key=request.get("operation_key"),
        reference=request.get("reference"), turn_key=None,
        state="CONSUMED" if consumption else "ABSENT", effect="COMMITTED" if consumption else "NONE",
        initial_consumption=consumption, locator=window["locator"], result=None,
        parent_consumed=False, can_send=False)
    return wire.validate_turn_data(value, request)
