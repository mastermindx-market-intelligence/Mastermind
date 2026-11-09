"""Installed App type/policy validation stays on the integration side."""

def bind_installed_read_pair(owner):
    from control_plane.installed_principal_read_binding import _issue_installed_read_pair
    return _issue_installed_read_pair(owner, validator=_validate_installed_read_pair)


def _validate_installed_read_pair(owner):
    # Reuse the one existing exact-AppPolicies/resource-policy validator.
    from integrations.session_bridge.runtime_return import _trusted_read_pair
    return _trusted_read_pair(owner)
