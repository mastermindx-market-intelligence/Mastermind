"""Fixed facade imported only by the installed protected Control composition.

Ordinary CLI OperatorOwner has no path to these nominal capabilities. This
module does not authenticate a dict, install a service or read arbitrary paths.
"""
from control_plane.memory_native_issuer import (
    NativeCaseCapability, NativeCaseRefused, NativeCaseUnknown,
    prepare_case, current_input, authorize_result_disclosure, read_original_case,
)
