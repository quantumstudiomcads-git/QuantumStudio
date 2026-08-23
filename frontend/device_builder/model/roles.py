from enum import Enum

class RegionRole(str, Enum):
    ELECTRODE = "electrode"
    CHANNEL = "channel"
    ACTIVE_LAYER = "active_layer"
    SUBSTRATE = "substrate"
    DIELECTRIC = "dielectric"
    CONTACT = "contact"
    GATE = "gate"
    ADSORBATE = "adsorbate"
    INTERFACE = "interface"
    OTHER = "other"

ROLE_LABELS = {
    RegionRole.ELECTRODE: "Electrode", RegionRole.CHANNEL: "Channel",
    RegionRole.ACTIVE_LAYER: "Active Layer", RegionRole.SUBSTRATE: "Substrate",
    RegionRole.DIELECTRIC: "Dielectric", RegionRole.CONTACT: "Contact",
    RegionRole.GATE: "Gate", RegionRole.ADSORBATE: "Adsorbate",
    RegionRole.INTERFACE: "Interface", RegionRole.OTHER: "Other",
}

def role_label(role):
    return ROLE_LABELS[RegionRole(role)]
