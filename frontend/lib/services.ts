/**
 * The services shown on the public website, one page each at /services/<slug>.
 * Screenshots live in public/showcase/ and come from the sample layout (python -m app.seed).
 */

export interface Service {
  slug: string;
  name: string;
  /** One line under the heading. */
  promise: string;
  intro: string;
  included: { title: string; text: string }[];
  /** What the person paying sees once a job is done. */
  proof: string[];
  shot: { src: string; alt: string; caption: string };
  /** Sample before and after photos, for services that are proven with photos. */
  beforeAfter?: string;
  /** Sample photo for services that have no before and after. */
  cover?: { src: string; alt: string };
  /** Picture on the services overview card. */
  thumb: string;
  goodFor: string[];
  /** Basic price on level, easy-to-reach ground; difficult terrain is quoted extra (see TERRAIN_NOTE). */
  price?: Price;
  /** Annual maintenance contract plans, cheapest first. */
  amc?: AmcPlan[];
}

export interface AmcPlan {
  name: string;
  /** Short line under the plan name, e.g. "4 cleanings a year". */
  summary: string;
  includes: string[];
  /** Rupees per square foot of plot for the whole year. */
  perSqftYear: number;
  /** Lowest yearly charge, in rupees. */
  minimumYear: number;
  popular?: boolean;
}

export interface Price {
  /** Rupees per square foot of plot. */
  perSqft: number;
  /** What the rate covers, e.g. "per visit". */
  per: string;
  /** Lowest charge for one visit or month, in rupees. */
  minimum: number;
}

export const TERRAIN_NOTE =
  "The basic rate is for level plots we can reach by road. Difficult terrain, such as slopes, rocky ground, waist-high overgrowth, dumped construction waste or no vehicle access, is charged extra. We quote the extra after a site visit, before any work starts.";

export const SERVICES: Service[] = [
  {
    slug: "plot-cleaning",
    amc: [
      { name: "Basic", summary: "4 cleanings a year", includes: ["Quarterly weed and debris clearing", "Photo report after every visit"], perSqftYear: 7.5, minimumYear: 5000 },
      { name: "Standard", summary: "6 cleanings a year", includes: ["Cleaning every two months", "Photo report after every visit", "2 Property Watch inspections"], perSqftYear: 11, minimumYear: 8000, popular: true },
      { name: "Premium", summary: "12 cleanings a year", includes: ["Monthly cleaning", "Photo report after every visit", "Quarterly Property Watch inspection", "Priority visit within 48 hours on request"], perSqftYear: 20, minimumYear: 15000 },
    ],
    price: { perSqft: 2, per: "per visit", minimum: 1500 },
    beforeAfter: "/showcase/plot-cleaning-ba.jpg",
    thumb: "/showcase/plot-cleaning-card.jpg",
    name: "Plot Cleaning",
    promise: "Your plot kept clean and visible, every month, with photos to prove it.",
    intro:
      "Vacant plots collect weeds, debris and dumped waste fast. We clear them on a schedule you choose, and every visit is recorded with photos, a checklist and the time, so you know the work happened even if you live in another city.",
    included: [
      { title: "Weed removal", text: "Weeds and wild growth cleared across the plot and along the boundary." },
      { title: "Debris clearing", text: "Construction waste, litter and dumped material removed and disposed of." },
      { title: "Boundary cleaning", text: "Boundary stones and markers cleared so the plot edges stay visible." },
      { title: "Recurring upkeep", text: "Monthly or quarterly visits, created automatically from a schedule." },
    ],
    proof: ["Photos of the cleaned plot", "Completed cleaning checklist", "Time of each visit, and location if you require it", "Bill and receipt for the job"],
    shot: {
      src: "/showcase/plot-cleaning.jpg",
      alt: "A finished plot cleaning job with before and after photos, checklist and payment",
      caption: "A finished cleaning job in GreenPlot: photos, checklist, notes, supervisor approval and payment on one page.",
    },
    goodFor: ["Vacant plots", "Owners living away", "Plots under sale"],
  },
  {
    slug: "garden-landscape",
    amc: [
      { name: "Basic", summary: "Visit every two weeks", includes: ["Mowing, weeding and watering", "Hedge trimming every month"], perSqftYear: 17, minimumYear: 18000 },
      { name: "Standard", summary: "Weekly visit", includes: ["Mowing, weeding and watering", "Hedge trimming and pruning", "Seasonal planting twice a year"], perSqftYear: 32, minimumYear: 30000, popular: true },
      { name: "Premium", summary: "Weekly visit plus tree care", includes: ["Everything in Standard", "Tree pruning before the monsoon", "Manure and pest control every quarter"], perSqftYear: 38, minimumYear: 36000 },
    ],
    price: { perSqft: 3, per: "per month", minimum: 2000 },
    beforeAfter: "/showcase/garden-landscape-ba.jpg",
    thumb: "/showcase/garden-landscape-card.jpg",
    name: "Garden & Landscape",
    promise: "Lawns, hedges, trees and parks looked after on schedule.",
    intro:
      "Common parks and avenue trees are the first thing visitors see. Gardeners get a weekly or monthly job with a checklist, record what they did with photos, and a supervisor signs it off, so the association can see every park is cared for.",
    included: [
      { title: "Lawn care", text: "Mowing, edging and weeding of lawns and common green areas." },
      { title: "Hedges and trees", text: "Hedge trimming, pruning and tree care along roads and parks." },
      { title: "Planting", text: "Seasonal planting, bed preparation and plantation drives." },
      { title: "Watering", text: "Regular watering and clippings removed from the site." },
    ],
    proof: ["Before and after photos of each area", "Gardening checklist ticked on site", "Supervisor approval", "Recurring schedule you can see"],
    shot: {
      src: "/showcase/garden-landscape.jpg",
      alt: "A finished lawn mowing and hedge trimming job with before and after photos",
      caption: "Park B's lawn and hedge job: what was found, what was done and the photos to show it.",
    },
    goodFor: ["Layout parks", "Avenue trees", "Plot owners' gardens"],
  },
  {
    slug: "property-inspection",
    amc: [
      { name: "Basic", summary: "4 inspections a year", includes: ["Quarterly Property Watch visit", "Condition report with photos"], perSqftYear: 2, minimumYear: 2500 },
      { name: "Standard", summary: "12 inspections a year", includes: ["Monthly Property Watch visit", "Condition report with photos", "Alert when anything needs attention"], perSqftYear: 5.5, minimumYear: 6000, popular: true },
      { name: "Premium", summary: "12 inspections plus cleaning", includes: ["Monthly Property Watch visit", "2 plot cleanings a year", "Repairs arranged for you, quoted before work"], perSqftYear: 9, minimumYear: 10000 },
    ],
    price: { perSqft: 0.5, per: "per visit", minimum: 750 },
    cover: { src: "/showcase/property-inspection-cover.jpg", alt: "An inspector photographing a plot's gate and boundary stones" },
    thumb: "/showcase/property-inspection-card.jpg",
    name: "Property Inspection",
    promise: "Know the condition of your property without visiting it.",
    intro:
      "Property Watch visits check your plot or house point by point (boundary, gate, fencing, vegetation, water and drainage) and record its condition with photos. The office can turn any problem found into a repair job in one step, and you get a report of every visit.",
    included: [
      { title: "Scheduled visits", text: "Monthly or quarterly inspections, or one before a sale or registration." },
      { title: "Point-by-point check", text: "Each point marked good, needs attention or issue, with notes." },
      { title: "Evidence", text: "Photos taken on site, with the date and time of the visit." },
      { title: "History", text: "Every inspection kept against the property, so you can see changes over time." },
    ],
    proof: ["Condition of each inspection point", "Photos from the visit", "Overall condition and findings", "Follow-up jobs for anything found"],
    shot: {
      src: "/showcase/property-inspection.jpg",
      alt: "A Property Watch inspection with the condition of each point",
      caption: "A Property Watch report as the owner sees it: every point checked, with the one thing that needs attention.",
    },
    goodFor: ["NRI owners", "Absentee owners", "Before a sale"],
  },
  {
    slug: "fencing-gates",
    beforeAfter: "/showcase/fencing-gates-ba.jpg",
    thumb: "/showcase/fencing-gates-card.jpg",
    name: "Fencing & Gates",
    promise: "Gates that close and fences that hold, repaired and recorded.",
    intro:
      "Broken gates and sagging fences are the most common complaints in a layout. Each repair is assigned to staff or a trusted vendor, and the job is only signed off with before and after photos and a tested checklist. Gates can carry a QR code that is scanned on site to prove the right gate was serviced.",
    included: [
      { title: "Gate servicing", text: "Hinges lubricated, alignment adjusted, locks and latches tested." },
      { title: "Fence repair", text: "Sagging or broken fencing repaired along boundaries." },
      { title: "Vendor jobs", text: "Specialist fabrication handed to vendors, tracked to completion." },
      { title: "Preventive care", text: "Gates serviced on a schedule before they fail." },
    ],
    proof: ["Before and after photos", "Completed, tested checklist", "QR scan and materials used, where recorded", "Supervisor sign-off"],
    shot: {
      src: "/showcase/fencing-gates.jpg",
      alt: "A finished gate repair job with QR scan, materials and photos",
      caption: "The main gate job: scanned on site, checklist done, materials recorded and approved.",
    },
    goodFor: ["Layout entrance gates", "Plot boundary fences", "Compound walls"],
  },
  {
    slug: "maintenance-repairs",
    beforeAfter: "/showcase/maintenance-repairs-ba.jpg",
    thumb: "/showcase/maintenance-repairs-card.jpg",
    name: "Maintenance & Repairs",
    promise: "Leaks, lights and breakdowns fixed, with a record of every job.",
    intro:
      "Residents report a problem from their phone, the office assigns it, and the person doing the work records what they found and fixed. Owners see each step, pay for chargeable jobs online, and the job closes only when it is proven and paid.",
    included: [
      { title: "Plumbing", text: "Leaks, pipes, taps and water lines repaired and pressure tested." },
      { title: "Electrical", text: "Streetlights, pumps and wiring faults fixed safely." },
      { title: "Civil and painting", text: "Small civil repairs and painting in common areas." },
      { title: "Asset servicing", text: "Pumps, motors and other assets serviced on schedule." },
    ],
    proof: ["Status updates from report to closure", "Before and after photos", "Work notes: issue found and outcome", "Online bill and receipt"],
    shot: {
      src: "/showcase/maintenance-repairs.jpg",
      alt: "A finished pipe repair job with photos, notes and a paid bill",
      caption: "A leaking pipe at Plot 117: reported, fixed, tested, approved and paid.",
    },
    goodFor: ["Residents", "Plot owners", "Association common areas"],
  },
  {
    slug: "staff-vendors",
    cover: { src: "/showcase/staff-vendors-cover.jpg", alt: "A field team in uniform with a hedge trimmer, broom and toolbox" },
    thumb: "/showcase/staff-vendors-card.jpg",
    name: "Staff & Vendors",
    promise: "Everyone who works in your layout, organised in one place.",
    intro:
      "Gardeners, cleaners, guards and outside vendors each get their own app view with today's jobs. Supervisors assign work, see who is on shift and approve completed jobs, and the association sees how quickly each job is done.",
    included: [
      { title: "Staff and shifts", text: "Staff profiles, shifts and attendance in one list." },
      { title: "Vendors", text: "Contractors with their trades, contacts and assigned jobs." },
      { title: "Assignments", text: "Jobs assigned to a person or vendor, with due dates and reminders." },
      { title: "Approvals", text: "Supervisors review proof before any job is marked done." },
    ],
    proof: ["Who did each job and when", "Jobs waiting for approval", "Overdue work flagged", "Ratings from residents"],
    shot: {
      src: "/showcase/staff-vendors.jpg",
      alt: "The staff list with shifts and roles",
      caption: "Staff, shifts and roles for the sample layout.",
    },
    goodFor: ["Associations", "Facility managers", "Developers"],
  },
];

export const serviceBySlug = (slug: string) => SERVICES.find((s) => s.slug === slug);
