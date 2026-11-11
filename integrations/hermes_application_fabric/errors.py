"""Bounded consumer errors; transport exception text never leaves the owner."""
import re


class HermesFabricError(RuntimeError):
    def __init__(self, code: str, *, effect_unknown: bool = False):
        if type(code) is not str or re.fullmatch(r"hermes_fabric_[a-z0-9_]{1,80}", code) is None:
            code = "hermes_fabric_internal_error"
        super().__init__(code)
        self.code = code
        self.effect_unknown = effect_unknown


class CodecError(HermesFabricError):
    pass
