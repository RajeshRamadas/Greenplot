/** Where a record of a given entity type lives in the portal. */
export function linkFor(type: string | null | undefined, id: string | null | undefined): string | null {
  if (!type || !id) return null;
  switch (type) {
    case "maintenance_task":
    case "maintenance":
      return `/maintenance/${id}`;
    case "complaint":
      return `/complaints/${id}`;
    case "ticket":
      return `/tickets/${id}`;
    case "signup_request":
      return `/settings`;
    case "inspection":
      return `/inspections/${id}`;
    case "incident":
      return `/incidents/${id}`;
    case "property":
      return `/properties/${id}`;
    case "asset":
      return `/assets/${id}`;
    case "sos":
      return `/incidents`;
    case "visitor":
      return `/visitors`;
    case "notice":
      return `/notices`;
    case "invoice":
    case "payment":
      return `/billing`;
    case "vendor":
      return `/vendors`;
    case "staff":
      return `/staff`;
    case "patrol_run":
      return `/patrol`;
    default:
      return null;
  }
}
