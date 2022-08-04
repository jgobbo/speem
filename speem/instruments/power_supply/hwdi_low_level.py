from functools import wraps
from .hwdi_cffi import lib

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
            raise Exception(f'FFI Error Code {return_code} in {f.__name__}')

        return return_value

    return wrapper

@wrap_stdcall_raise
def connect():
    return lib.SC_HDWI_Connect()

@wrap_stdcall_raise
def create_buffer():
    return lib.SC_HWDI_CreateBuffer()

@wrap_stdcall_raise
def create_device():
    return lib.SC_HWDI_CreateDevice()

@wrap_stdcall_raise
def disconnect():
    return lib.SC_HWDI_Disconnect()

@wrap_stdcall_raise
def dispose_buffer():
    return lib.SC_HWDI_DisposeBuffer()

@wrap_stdcall_raise
def dispose_device():
    return lib.SC_HWDI_DisposeDevice()

@wrap_stdcall_raise
def get_buffer_data():
    return lib.SC_HWDI_GetBufferData()

@wrap_stdcall_raise
def get_buffer_size():
    return lib.SC_HWDI_GetBufferSize()

@wrap_stdcall_raise
def get_error_message():
    return lib.SSC_HWDI_GetErrorMessage()

@wrap_stdcall_raise
def get_library_version():
    return lib.SC_HWDI_GetLibraryVersion()

@wrap_stdcall_raise
def get_properties():
    return lib.SC_HWDI_GetProperties()

@wrap_stdcall_raise
def get_property_manifest():
    return lib.SC_HWDI_GetPropertyManifest()

@wrap_stdcall_raise
def read():
    return lib.SC_HWDI_Read()

@wrap_stdcall_raise
def read_all():
    return lib.SC_HWDI_ReadAll()

@wrap_stdcall_raise
def read_byte():
    return lib.SC_HWDI_ReadByte()

@wrap_stdcall_raise
def reset_transmission():
    return lib.SC_HWDI_ResetTransmission()

@wrap_stdcall_raise
def set_properties():
    return lib.SC_HWDI_SetProperties()

@wrap_stdcall_raise
def write():
    return lib.SC_HWDI_Write() 