from functools import wraps
from .hvc20_cffi import *
from ctypes import c_int

# __all__ = ('setup', 'initialize', 'set_hv', 'set_dac20', 'finalize',)


def wrap_stdcall_raise(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return_value = f(*args, **kwargs)

        if isinstance(return_value, int):
            return_code = return_value
            return_value = None
        else:
            return_code, return_value = return_value

        if return_code != 0:
            raise Exception(f"FFI Error Code {return_code} in {f.__name__}")

        return return_value

    return wrapper


@wrap_stdcall_raise
def initialize(handle: int = 0):
    return lib.GDS_SUP_Initialize(handle)


@wrap_stdcall_raise
def finalize():
    return lib.GDS_SUP_Finalize()


@wrap_stdcall_raise
def setup():
    return lib.GDS_SUP_Setup()


@wrap_stdcall_raise
def set_hv(address: int, voltage: int, period: int):
    # return lib.GDS_SUP_SetHV(c_int(address), c_int(voltage), c_int(period))
    return lib.GDS_SUP_SetHV(address, voltage, period)


@wrap_stdcall_raise
def set_dac20(address: int, voltage: int):
    return lib.GDS_SUP_SetDAC20(address, voltage)


@wrap_stdcall_raise
def burst():
    return lib.GDS_SUP_Burst()


@wrap_stdcall_raise
def test_communication():
    input = hvc20_ffi.new("int *")
    print(input)
    return lib.GDS_SUP_TestCommunication(input)


@wrap_stdcall_raise
def get_lib_info():
    return lib.GDS_SUP_GetLibInfo()


@wrap_stdcall_raise
def reset():
    return lib.GDS_SUP_Reset()
