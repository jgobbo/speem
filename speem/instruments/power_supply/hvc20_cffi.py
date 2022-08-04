from pathlib import Path
from cffi import FFI

__all__ = ('hvc20_ffi', 'lib',)

hvc20_ffi = FFI()
LIB_PATH = Path(__file__).parent.absolute() / 'lib'
INC_PATH = LIB_PATH

with open(str(INC_PATH / 'hvc20.h')) as f:
    hvc20_ffi.cdef(f.read())

lib = hvc20_ffi.dlopen(str(INC_PATH / 'Supply_HVC20.dll'))