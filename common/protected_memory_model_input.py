"""Exact packet compiler only. Model/bytes validation confers no authority."""
from common.memory_native_wire import SUFFIX, canonical, parse, WireRefused

class MemoryModelInputRefused(ValueError):
    def __init__(self): super().__init__('protected_memory_model_input_refused')

def compile_memory_model_input(packet, *, model):
    try:
        if (type(packet) is not bytes or not 1 <= len(packet) <= 65536
                or b'\0' in packet or not packet.endswith(SUFFIX) or packet.count(SUFFIX) != 1
                or type(model) is not str or model not in ('glm-5.3', 'glm-5.3-flash')):
            raise ValueError
        return canonical({'model':model, 'input':packet.decode('utf-8'), 'stream':False, 'max_output_tokens':8192})
    except (ValueError, TypeError, UnicodeError): raise MemoryModelInputRefused() from None

def decode_memory_model_input(raw, *, expected_packet, expected_model):
    try:
        expected = compile_memory_model_input(expected_packet, model=expected_model)
        if type(raw) is not bytes or raw != expected: raise ValueError
        return parse(raw, 400000)
    except (ValueError, TypeError, UnicodeError): raise MemoryModelInputRefused() from None
