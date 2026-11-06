"""Bounded consumer errors; transport exception text never leaves the owner."""


class HermesFabricError(RuntimeError):
    def __init__(self, code: str, *, effect_unknown: bool = False):
        super().__init__(code)
        self.code = code
        self.effect_unknown = effect_unknown


class CodecError(HermesFabricError):
    pass
