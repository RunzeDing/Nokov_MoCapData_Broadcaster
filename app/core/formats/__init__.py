"""Outbound packet formats.

Importing this package registers every built-in encoder in
:data:`app.core.formats.base.REGISTRY`.
"""

from __future__ import annotations

from .base import (  # noqa: F401
    DTYPES,
    DTYPE_LABELS,
    ENDIANNESS,
    Encoder,
    EncodeContext,
    FieldSpec,
    packet_quantities,
    packet_quantity_map,
    ParamSpec,
    quantities,
    quantity_map,
    REGISTRY,
    convert_value,
    get_format,
    hex_dump,
    list_formats,
    pack_value,
    register,
)

# Register the built-in formats (side-effect imports, order defines menu order).
from . import stq14  # noqa: E402,F401
from . import stq20  # noqa: E402,F401
from . import custom_bin  # noqa: E402,F401

__all__ = [
    "DTYPES",
    "DTYPE_LABELS",
    "ENDIANNESS",
    "Encoder",
    "EncodeContext",
    "FieldSpec",
    "packet_quantities",
    "packet_quantity_map",
    "ParamSpec",
    "quantities",
    "quantity_map",
    "REGISTRY",
    "convert_value",
    "get_format",
    "hex_dump",
    "list_formats",
    "pack_value",
    "register",
]
