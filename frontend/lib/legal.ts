/**
 * Business details shown on the legal pages (privacy, terms, refunds, delivery, contact).
 * Replace every "[ ... ]" value with the registered details before going live: Razorpay
 * checks that the business name, address and phone match the ones on the merchant account.
 */
export const BUSINESS = {
  brand: "GreenPlot",
  legalName: "[Registered business name]",
  address: "[Registered office address, City, State, PIN]",
  city: "[City]",
  state: "[State]",
  email: "hello@greenplot.in",
  phone: "[Support phone number]",
  hours: "Monday to Saturday, 9:00 AM to 6:00 PM IST",
  grievanceOfficer: "[Grievance Officer's name]",
  grievanceEmail: "grievance@greenplot.in",
  updated: "18 October 2026",
};

/** Bump when the Terms or Privacy Policy change in a way users must accept again. */
export const TERMS_VERSION = "2026-10-18";

export const LEGAL_PAGES = [
  { href: "/terms", label: "Terms & Conditions" },
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/refund-policy", label: "Refund & Cancellation" },
  { href: "/service-delivery", label: "Service Delivery" },
  { href: "/contact", label: "Contact Us" },
];
