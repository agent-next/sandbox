"""Patch PyOpenGL 3.1.0's osmesa module for pyrender 0.1.45.

pyrender's OSMesa platform imports OSMesaCreateContextAttribs and the
OSMESA_* attribute constants, which exist in libOSMesa 22.3 (the pinned
libosmesa6 Debian package) but are not wrapped by PyOpenGL 3.1.0 — the
version pyrender==0.1.45 requires. Import this module before creating a
pyrender.OffscreenRenderer; it fills the missing names via ctypes.

Constant values are the public ABI from /usr/include/GL/osmesa.h
(libosmesa6-dev 22.3.6-1+deb12u2).
"""
import ctypes
import ctypes.util
import os

os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")

import OpenGL.osmesa as _osmesa  # noqa: E402

_CONSTS = {
    "OSMESA_FORMAT": 0x22,
    "OSMESA_DEPTH_BITS": 0x30,
    "OSMESA_PROFILE": 0x33,
    "OSMESA_CORE_PROFILE": 0x34,
    "OSMESA_COMPAT_PROFILE": 0x35,
    "OSMESA_CONTEXT_MAJOR_VERSION": 0x36,
    "OSMESA_CONTEXT_MINOR_VERSION": 0x37,
    "OSMESA_RGBA": 0x1908,
    "OSMESA_BGRA": 0x1908,
}

for _name, _val in _CONSTS.items():
    if not hasattr(_osmesa, _name):
        setattr(_osmesa, _name, _val)

if not hasattr(_osmesa, "OSMesaCreateContextAttribs"):
    _lib_path = ctypes.util.find_library("OSMesa") or "libOSMesa.so.8"
    _lib = ctypes.CDLL(_lib_path)
    _fn = _lib.OSMesaCreateContextAttribs
    _fn.restype = ctypes.c_void_p
    _fn.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_void_p]

    def _create_context_attribs(attribs, sharelist):
        # pyrender passes an OpenGL.arrays GLintArray (numpy-backed)
        if hasattr(attribs, "ctypes") and hasattr(attribs.ctypes, "data_as"):
            attribs = attribs.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
        return _fn(attribs, sharelist)

    _osmesa.OSMesaCreateContextAttribs = _create_context_attribs

# PyOpenGL's OSMesa platform wraps OSMesaGetCurrentContext with the opaque
# pointer type OSMesaContext, a ctypes.POINTER subclass — unhashable on
# CPython 3.12, which breaks contextdata.getValue('extensions'). Rebind the
# platform's GetCurrentContext to a c_void_p restype (hashable int).
from OpenGL import platform as _platform  # noqa: E402

_plat = _platform.PLATFORM
_raw_get = _plat.GL.OSMesaGetCurrentContext
_raw_get.restype = ctypes.c_void_p
_plat.GetCurrentContext = _raw_get
