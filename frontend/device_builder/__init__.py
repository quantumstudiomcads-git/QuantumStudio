"""Device Builder v0.1 public API.

The model remains Qt-free; UI symbols are loaded lazily.
"""
from .model import Device, DeviceRegion, RegionRole

__all__ = ["DeviceBuilderWorkspace", "Device", "DeviceRegion", "RegionRole",
           "DeviceAssembly", "assemble_device", "validate_device"]

def __getattr__(name):
    if name == "DeviceBuilderWorkspace":
        from .workspace import DeviceBuilderWorkspace
        return DeviceBuilderWorkspace
    if name in {"DeviceAssembly", "assemble_device", "validate_device"}:
        from .assembly import DeviceAssembly, assemble_device, validate_device
        return {
            "DeviceAssembly": DeviceAssembly,
            "assemble_device": assemble_device,
            "validate_device": validate_device,
        }[name]
    raise AttributeError(name)
