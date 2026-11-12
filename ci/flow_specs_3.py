"""Subset 3 of the reviewed ASAI flow specifications."""
from __future__ import annotations

import ast
import base64
import zlib

FLOW_SPECS_PART_3: dict[str, tuple[str, tuple[str, ...]]] = ast.literal_eval(
    zlib.decompress(base64.b85decode('c-oaw%}&EG41Sf}%A~d2xgqfY197*!#vM`9IN0exLcBXpAyqGv*v+x?{rK}&<6|ZnuqSONl#z1lFylR@)JAS~K22WLb8H@VcUL|)2ODM542J3+Q+l;pyQLEuBIOU35m?|PJd(hM^|1RzI+_^XXSPT8Wc70?kHQ!4NH%<q2AqQ_MF)fb%(D<U)8Gt3=%5#J6tl;mMR3BARs%hTpf@WTZGga>PS}sDCX4-olE+yv+a@q8X<0Y;%PQII_a=8G;^Y$rAE_1Npd}9dSIQL#8(??*Yrd?#%?>;a3!wTXS59RvFZCK(A#=Tt1y>iSY2B{5L<@rr-l7ecizSPfBF4V(Oz17Om}S;tsCslB&yh9zUM;@wAA4vB3j'.encode("ascii"))).decode("utf-8")
)
