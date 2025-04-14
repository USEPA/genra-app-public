"""Convenience collection of FP classes"""


from genraweb.lib.fp.fpchem import FPChem
from genraweb.lib.fp.fphtpp import FPHTPP_MCF7, FPHTPP_U2OS
from genraweb.lib.fp.fpmrgnhttr import FPhttr, FPMrgnhttr
from genraweb.lib.fp.fpphyschem import FPPhysChem
from genraweb.lib.fp.fptoxcast import (FPToxcast, FPToxcastVendorATG,
                                       FPToxcastVendorBSK, FPToxcastVendorNVS)
from genraweb.lib.fp.fptoxcast4 import FPToxcast4
from genraweb.lib.fp.fptoxref import FPToxref
from genraweb.lib.fp.fppesticide import FPPesticide
from genraweb.lib.fp.genfputils import FPGen

(
    FPChem,
    FPhttr,
    FPMrgnhttr,
    FPPhysChem,
    FPToxcast,
    FPToxcastVendorATG,
    FPToxcastVendorBSK,
    FPToxcastVendorNVS,
    FPToxcast4,
    FPToxref,
    FPHTPP_MCF7,
    FPHTPP_U2OS,
    FPPesticide,
    FPGen,
)
