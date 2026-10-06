"""Per-layout feature switches for customers (residents) and vendors.

Everyone signs in to the same app; the role decides the view. On top of the
role's permission matrix, a layout admin can switch whole features off for
residents or vendors (tenant setting ``role_features``). A switched-off feature
removes its permissions, so it disappears from menus and is refused by the API.
"""

from app.models.enums import Role

# feature key -> label, description, permissions it grants, other features it needs
ROLE_FEATURES: dict[str, dict[str, dict]] = {
    Role.RESIDENT: {
        "tickets": {
            "label": "Service tickets",
            "description": "Raise service requests, follow them and confirm the fix",
            "permissions": ["tickets.read", "tickets.create"],
        },
        "property": {
            "label": "My property",
            "description": "Plot details, household members and the property's history",
            "permissions": ["properties.read", "residents.read"],
        },
        "maintenance": {
            "label": "Maintenance history",
            "description": "Work done on their property, with proof of work reports",
            "permissions": ["maintenance.read", "maintenance.acknowledge", "reports.proof"],
        },
        "property_watch": {
            "label": "Property Watch",
            "description": "Request inspection visits and read inspection reports",
            "permissions": ["inspections.read", "inspections.request"],
        },
        "complaints": {
            "label": "Complaints",
            "description": "The older complaint form, alongside service tickets",
            "permissions": ["complaints.read", "complaints.create"],
        },
        "visitors": {
            "label": "Visitors",
            "description": "Pre-approve guests and approve visitors at the gate",
            "permissions": ["visitors.read", "visitors.preapprove"],
        },
        "vehicles": {
            "label": "Vehicles",
            "description": "Register household vehicles",
            "permissions": ["vehicles.read", "vehicles.manage"],
        },
        "billing": {
            "label": "Dues & payments",
            "description": "See dues, pay online and download receipts",
            "permissions": ["billing.read", "payments.create"],
        },
        "notices": {"label": "Notices", "description": "Announcements, alerts and events", "permissions": ["notices.read"]},
        "sos": {"label": "SOS", "description": "Emergency alert to the guards and office", "permissions": ["sos.raise"]},
        "incidents": {
            "label": "Incident reports",
            "description": "Report security incidents and follow them",
            "permissions": ["incidents.read", "incidents.create"],
        },
        "records": {"label": "Records search", "description": "Search their own records", "permissions": ["records.search"]},
    },
    Role.VENDOR: {
        "tickets": {
            "label": "Service tickets",
            "description": "Receive customer tickets, accept or reject, and submit the work",
            "permissions": ["tickets.read", "tickets.work"],
            "requires": ["jobs"],
        },
        "jobs": {
            "label": "Work orders",
            "description": "Assigned jobs with checklist, materials and evidence capture",
            "permissions": ["maintenance.read", "maintenance.work"],
        },
        "scan": {"label": "Scan asset", "description": "Find an asset and its open jobs by QR/NFC", "permissions": ["assets.scan"]},
        "proof_reports": {
            "label": "Proof of work reports",
            "description": "Download PDF reports of completed jobs",
            "permissions": ["reports.proof"],
        },
        "offline": {"label": "Offline mode", "description": "Queue work without signal and sync later", "permissions": ["sync.use"]},
        "records": {"label": "Records search", "description": "Search their job records", "permissions": ["records.search"]},
    },
}

CONFIGURABLE_ROLES = tuple(ROLE_FEATURES)


def feature_state(settings: dict | None, role: str) -> dict[str, bool]:
    """Every feature for the role → on/off (default on)."""
    cfg = ((settings or {}).get("role_features") or {}).get(role) or {}
    return {key: bool(cfg.get(key, True)) for key in ROLE_FEATURES.get(role, {})}


def enabled_features(settings: dict | None, role: str) -> list[str]:
    return [k for k, on in feature_state(settings, role).items() if on]


def disabled_permissions(settings: dict | None, role: str) -> frozenset[str]:
    """Permissions granted only by switched-off features (a permission stays if any enabled feature grants it)."""
    feats = ROLE_FEATURES.get(role)
    if not feats:
        return frozenset()
    state = feature_state(settings, role)
    on: set[str] = set()
    off: set[str] = set()
    for key, f in feats.items():
        (on if state[key] else off).update(f["permissions"])
    return frozenset(off - on)
