import type { Area, City } from "@/lib/cities";
import { type Service, SERVICES, TERRAIN_NOTE } from "@/lib/services";
import { rupees } from "@/lib/site";

export interface Faq {
  q: string;
  a: string;
}

const priceAnswer = (s: Service, where: string) =>
  s.price
    ? `${s.name} ${where} starts at ${rupees(s.price.perSqft)} per sq ft ${s.price.per}, with a minimum of ${rupees(s.price.minimum)}.${s.amc?.length ? ` Annual plans start at ${rupees(s.amc[0].perSqftYear)} per sq ft a year.` : ""} ${TERRAIN_NOTE}`
    : `We quote ${s.name.toLowerCase()} ${where} after understanding your layout and what you need. Message us on WhatsApp for a quote.`;

/** Questions answered on each service page. */
export function serviceFaqs(s: Service, city: City): Faq[] {
  const where = `in ${city.name}`;
  return [
    { q: `How much does ${s.name.toLowerCase()} cost ${where}?`, a: priceAnswer(s, where) },
    { q: "How do I know the work was really done?", a: `When a job is done you get: ${s.proof.join("; ")}. Photos are taken on site by our team and stored with their time.` },
    {
      q: `Which areas of ${city.name} do you cover?`,
      a: `We work across ${city.name}, including ${city.areas.map((a) => a.name).join(", ")}. If your plot is somewhere else, message us and we will tell you if we can reach it.`,
    },
    { q: `Do I need to be in ${city.name} to book?`, a: "No. Most of our owners live in another city or abroad. You book and pay online or on WhatsApp, and every visit is reported with photos." },
  ];
}

/** Questions answered on each area page. */
export function areaFaqs(area: Area, city: City): Faq[] {
  const cleaning = SERVICES.find((s) => s.slug === "plot-cleaning");
  return [
    { q: `Do you clean plots in ${area.name}?`, a: `Yes. We clean and look after plots across ${area.name}, including ${area.localities.join(", ")}.` },
    ...(cleaning ? [{ q: `How much does plot cleaning cost in ${area.name}?`, a: priceAnswer(cleaning, `in ${area.name}`) }] : []),
    { q: "How often should a vacant plot be cleaned?", a: "Most owners choose every three months. Plots next to open land or construction usually need cleaning every one to two months, especially after the monsoon." },
    { q: `I live outside ${city.name}. How will I know the work was done?`, a: "Every visit is recorded with before and after photos, a checklist and the time. You get the report on WhatsApp or email and can check it any time in the app." },
  ];
}
