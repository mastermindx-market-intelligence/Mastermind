"""Grok Bot link (GBL) package — lane GBL of integrations/mmos/gbl/.

Bridge core (``bridge_service``), routine nudge wrapper (``nudge``) and the
per-environment team.message sender (``message_send``).  Contract shapes and
laws live in ``common/gbl_contract.py`` (GBL-1); this package owns no new
store, queue or registry (the no-rebuild law, FACTS B12).
"""
