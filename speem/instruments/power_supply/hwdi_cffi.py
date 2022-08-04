from pathlib import Path
from cffi import FFI

__all__ = ('hwdi_ffi', 'lib',)

hwdi_ffi = FFI()
LIB_PATH = Path(__file__).parent.absolute() / 'lib'
INC_PATH = LIB_PATH

with open(str(INC_PATH / 'hwdi.h')) as f:
    hwdi_ffi.cdef(f.read())

lib = hwdi_ffi.dlopen(str(INC_PATH / 'HWDI_Network1.dll'))