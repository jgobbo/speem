from pathlib import Path
from cffi import FFI

__all__ = ('ffi', 'lib',)

scienta_7048_ffi = FFI()
LIB_PATH = Path(__file__).parent.absolute() / 'lib'
INC_PATH = LIB_PATH

with open(str(INC_PATH / 'ses_7048.h')) as f:
    scienta_7048_ffi.cdef(f.read())

ffi = scienta_7048_ffi
lib = ffi.dlopen(str(INC_PATH / 'Supply_7048_Serial.dll'))
#lib = ffi.dlopen(str(INC_PATH / 'Supply_Dummy.dll'))