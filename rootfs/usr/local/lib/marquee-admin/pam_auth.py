"""Minimal PAM password check via ctypes (no extra packages needed).

Must run as root so pam_unix can read /etc/shadow.
"""
from ctypes import (CDLL, CFUNCTYPE, POINTER, Structure, byref, c_char_p, c_int,
                    c_size_t, c_void_p, cast, sizeof)
from ctypes.util import find_library

_libc = CDLL(find_library("c"))
_libpam = CDLL(find_library("pam") or "libpam.so.0")

_calloc = _libc.calloc
_calloc.restype = c_void_p
_calloc.argtypes = [c_size_t, c_size_t]
_strdup = _libc.strdup
_strdup.restype = c_void_p
_strdup.argtypes = [c_char_p]

PAM_PROMPT_ECHO_OFF = 1
PAM_PROMPT_ECHO_ON = 2


class PamHandle(Structure):
    _fields_ = [("handle", c_void_p)]


class PamMessage(Structure):
    _fields_ = [("msg_style", c_int), ("msg", c_char_p)]


class PamResponse(Structure):
    _fields_ = [("resp", c_void_p), ("resp_retcode", c_int)]


CONV_FUNC = CFUNCTYPE(c_int, c_int, POINTER(POINTER(PamMessage)),
                      POINTER(POINTER(PamResponse)), c_void_p)


class PamConv(Structure):
    _fields_ = [("conv", CONV_FUNC), ("appdata_ptr", c_void_p)]


_start = _libpam.pam_start
_start.restype = c_int
_start.argtypes = [c_char_p, c_char_p, POINTER(PamConv), POINTER(PamHandle)]
_auth = _libpam.pam_authenticate
_auth.restype = c_int
_auth.argtypes = [PamHandle, c_int]
_acct = _libpam.pam_acct_mgmt
_acct.restype = c_int
_acct.argtypes = [PamHandle, c_int]
_end = _libpam.pam_end
_end.restype = c_int
_end.argtypes = [PamHandle, c_int]


def authenticate(username: str, password: str, service: str = "marquee-admin") -> bool:
    pw = password.encode()

    @CONV_FUNC
    def conv(n_messages, messages, p_response, _app_data):
        addr = _calloc(n_messages, sizeof(PamResponse))
        response = cast(addr, POINTER(PamResponse))
        p_response[0] = response
        for i in range(n_messages):
            if messages[i].contents.msg_style in (PAM_PROMPT_ECHO_OFF, PAM_PROMPT_ECHO_ON):
                response[i].resp = _strdup(pw)
                response[i].resp_retcode = 0
        return 0

    handle = PamHandle()
    pam_conv = PamConv(conv, 0)
    if _start(service.encode(), username.encode(), byref(pam_conv), byref(handle)) != 0:
        return False
    rc = -1
    try:
        rc = _auth(handle, 0)
        if rc == 0:
            rc = _acct(handle, 0)
        return rc == 0
    finally:
        _end(handle, rc)

