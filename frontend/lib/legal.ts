/**
 * Business details shown on the legal pages (privacy, terms, refunds, delivery, contact).
 * Razorpay checks that the business name, address and phone match the ones on the merchant account.
 */
export const BUSINESS = {
  brand: "GreenPlot",
  legalName: "UDO TECHNOLOGIES LLP",
  address: "18, Kempanna Layout, Ramachandrapura, Jalahalli Post, Bangalore, Karnataka, India - 560013",
  city: "Bangalore",
  state: "Karnataka",
  email: "hello@greenplot.in",
  phone: "+91 81055 68225",
  hours: "Monday to Saturday, 9:00 AM to 6:00 PM IST",
  // Leave empty until a Grievance Officer is named; the contact block then shows only how to reach them.
  grievanceOfficer: "",
  grievanceEmail: "hello@greenplot.in",
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
