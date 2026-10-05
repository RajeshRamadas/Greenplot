"""Role/permission matrix (requirements §24).

Permissions are coarse capabilities; row-level scoping (a resident only seeing their
own property, staff only seeing assigned jobs) is enforced in app.services.access.
"""

from app.models.enums import Role

R = Role
ALL_TENANT_ROLES = {R.RESIDENT, R.GUARD, R.STAFF, R.SUPERVISOR, R.VENDOR, R.LAYOUT_ADMIN}
MANAGERS = {R.SUPERVISOR, R.LAYOUT_ADMIN}
FIELD = {R.STAFF, R.VENDOR}

PERMISSIONS: dict[str, set[Role]] = {
    # platform
    "tenants.manage": {R.SUPER_ADMIN},
    # people & properties
    "users.read": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    "users.manage": {R.LAYOUT_ADMIN},
    "layouts.manage": {R.LAYOUT_ADMIN},
    "properties.read": ALL_TENANT_ROLES - {R.VENDOR},
    "properties.manage": {R.LAYOUT_ADMIN},
    "residents.read": {R.LAYOUT_ADMIN, R.SUPERVISOR, R.GUARD, R.RESIDENT},
    "residents.manage": {R.LAYOUT_ADMIN},
    # maintenance
    "maintenance.read": ALL_TENANT_ROLES - {R.GUARD},
    "maintenance.create": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    "maintenance.assign": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    "maintenance.work": {R.STAFF, R.VENDOR, R.SUPERVISOR},
    "maintenance.review": {R.SUPERVISOR, R.LAYOUT_ADMIN},
    "maintenance.cancel": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    "maintenance.acknowledge": {R.RESIDENT},
    "maintenance.configure": {R.LAYOUT_ADMIN},
    "schedules.manage": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    # inspections / property watch
    "inspections.read": ALL_TENANT_ROLES - {R.GUARD, R.VENDOR},
    "inspections.manage": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    "inspections.perform": {R.STAFF, R.SUPERVISOR},
    "inspections.request": {R.RESIDENT, R.LAYOUT_ADMIN, R.SUPERVISOR},
    # complaints
    "complaints.read": ALL_TENANT_ROLES - {R.GUARD},
    "complaints.create": {R.RESIDENT, R.LAYOUT_ADMIN, R.SUPERVISOR, R.STAFF, R.GUARD},
    "complaints.manage": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    # assets
    "assets.read": ALL_TENANT_ROLES - {R.RESIDENT},
    "assets.manage": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    # staff & vendors
    "staff.read": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    "staff.manage": {R.LAYOUT_ADMIN},
    "attendance.self": {R.STAFF, R.GUARD, R.SUPERVISOR},
    "vendors.read": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    "vendors.manage": {R.LAYOUT_ADMIN},
    # security
    "visitors.read": {R.GUARD, R.LAYOUT_ADMIN, R.SUPERVISOR, R.RESIDENT},
    "visitors.manage": {R.GUARD, R.LAYOUT_ADMIN},
    "visitors.preapprove": {R.RESIDENT, R.LAYOUT_ADMIN},
    "vehicles.read": {R.GUARD, R.LAYOUT_ADMIN, R.SUPERVISOR, R.RESIDENT},
    "vehicles.manage": {R.LAYOUT_ADMIN, R.RESIDENT},
    "vehicles.log": {R.GUARD, R.LAYOUT_ADMIN},
    "patrol.read": {R.GUARD, R.LAYOUT_ADMIN, R.SUPERVISOR},
    "patrol.manage": {R.LAYOUT_ADMIN},
    "patrol.perform": {R.GUARD},
    "incidents.read": {R.GUARD, R.LAYOUT_ADMIN, R.SUPERVISOR, R.RESIDENT},
    "incidents.create": {R.GUARD, R.LAYOUT_ADMIN, R.SUPERVISOR, R.RESIDENT, R.STAFF},
    "incidents.manage": {R.GUARD, R.LAYOUT_ADMIN, R.SUPERVISOR},
    "sos.raise": ALL_TENANT_ROLES - {R.VENDOR},
    "sos.respond": {R.GUARD, R.LAYOUT_ADMIN, R.SUPERVISOR},
    # billing
    "billing.read": {R.LAYOUT_ADMIN, R.RESIDENT},
    "billing.manage": {R.LAYOUT_ADMIN},
    "payments.create": {R.RESIDENT, R.LAYOUT_ADMIN},
    "payments.record": {R.LAYOUT_ADMIN},
    # communication
    "notices.read": ALL_TENANT_ROLES,
    "notices.manage": {R.LAYOUT_ADMIN},
    # records, reports, audit
    "media.upload": ALL_TENANT_ROLES,
    "records.search": ALL_TENANT_ROLES - {R.GUARD},
    "reports.read": {R.LAYOUT_ADMIN, R.SUPERVISOR},
    "reports.proof": {R.LAYOUT_ADMIN, R.SUPERVISOR, R.RESIDENT, R.VENDOR, R.STAFF},
    "dashboard.read": ALL_TENANT_ROLES,
    "audit.read": {R.LAYOUT_ADMIN},
    "settings.manage": {R.LAYOUT_ADMIN},
    "sync.use": ALL_TENANT_ROLES,
}


def has_permission(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())


def permissions_for(role: str) -> list[str]:
    return sorted(p for p, roles in PERMISSIONS.items() if role in roles)
