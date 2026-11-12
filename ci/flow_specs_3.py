"""Subset 3 of the reviewed ASAI flow specifications."""
from __future__ import annotations

import ast
import base64
import zlib

FLOW_SPECS_PART_3: dict[str, tuple[str, tuple[str, ...]]] = ast.literal_eval(
    zlib.decompress(base64.b85decode(b"c-ozh!ES><3`Bn=H;TlPdv5uID$3n*z|a-J-r6QTRQdNTC{$b`Rk^KZcE)dhi^xveVM7*1)PX#-=(xv}0!y&zGDfo~TpV^EFFqGlww%l%r|M%$=lr&MQCNV<e?$img^S8S3Y*rdEUVosh!hiDBU4c7m6m}0i(?JKCRl$y#nYd*;gqgh0&{b(=+w?*GW%`ibpw}mLEiG5m5;uA^Lr8}=(6#}*#zVklFE%3xtV)Lj0_XIPBsIrjBUi8#XL4vl;!;aY5cC#")).decode("utf-8")
)
