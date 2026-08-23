"""Public Qt-free Device Template API."""

from .adsorbate_surface import SurfaceAdsorbateTemplate
from .base import DeviceTemplate, TemplateBuildResult
from .registry import TemplateRegistry
from .tunnel_junction import TunnelJunctionTemplate
from .two_probe import LateralTwoProbeTemplate
from .vertical_stack import VerticalStackTemplate

DEFAULT_TEMPLATE_REGISTRY = TemplateRegistry((
    VerticalStackTemplate(),
    LateralTwoProbeTemplate(),
    TunnelJunctionTemplate(),
    SurfaceAdsorbateTemplate(),
))

__all__ = [
    "DEFAULT_TEMPLATE_REGISTRY", "DeviceTemplate", "LateralTwoProbeTemplate",
    "SurfaceAdsorbateTemplate", "TemplateBuildResult", "TemplateRegistry",
    "TunnelJunctionTemplate", "VerticalStackTemplate",
]
