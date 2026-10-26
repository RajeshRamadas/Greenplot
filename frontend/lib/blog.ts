/**
 * Guides for plot owners, one page each at /blog/<slug>.
 * Prices are read from SERVICES so a price change updates the guides too.
 */
import { serviceBySlug, TERRAIN_NOTE } from "@/lib/services";
import { rupees } from "@/lib/site";

export interface Post {
  slug: string;
  title: string;
  description: string;
  /** ISO date first published. */
  published: string;
  /** Service pages this guide links to at the end. */
  services: string[];
  sections: { heading?: string; paragraphs: string[]; bullets?: string[] }[];
}

const cleaning = serviceBySlug("plot-cleaning");
const inspection = serviceBySlug("property-inspection");
const garden = serviceBySlug("garden-landscape");

const estimate = (sqft: number) => (cleaning?.price ? rupees(Math.max(sqft * cleaning.price.perSqft, cleaning.price.minimum)) : "on request");

export const POSTS: Post[] = [
  {
    slug: "plot-cleaning-cost-bangalore",
    title: "How much does plot cleaning cost in Bangalore?",
    description: "Plot cleaning prices in Bangalore per sq ft, what changes the price, and when an annual plan works out cheaper than paying per visit.",
    published: "2026-10-26",
    services: ["plot-cleaning", "property-inspection"],
    sections: [
      {
        paragraphs: [
          "Plot cleaning in Bangalore is usually priced by the size of the plot. The price also depends on how overgrown the plot is, whether there is construction waste to remove, and whether a vehicle can reach it.",
          cleaning?.price
            ? `At GreenPlot, a basic cleaning visit costs ${rupees(cleaning.price.perSqft)} per sq ft, with a minimum of ${rupees(cleaning.price.minimum)} a visit.`
            : "Message us for a quote for your plot.",
        ],
      },
      {
        heading: "Typical prices by plot size",
        paragraphs: ["These are basic estimates for one cleaning visit on level ground that a vehicle can reach."],
        bullets: [`30 x 40 (1,200 sq ft): ${estimate(1200)}`, `30 x 50 (1,500 sq ft): ${estimate(1500)}`, `40 x 60 (2,400 sq ft): ${estimate(2400)}`, `50 x 80 (4,000 sq ft): ${estimate(4000)}`],
      },
      {
        heading: "What makes it cost more",
        paragraphs: [TERRAIN_NOTE],
        bullets: ["Waist-high grass and shrubs that need cutting before clearing", "Dumped construction waste that has to be carried away", "Slopes, rocky ground or no road access", "Large trees that need trimming"],
      },
      {
        heading: "Per visit or an annual plan?",
        paragraphs: [
          cleaning?.amc?.length
            ? `If you need the plot cleaned more than three or four times a year, an annual maintenance contract (AMC) is cheaper. Our ${cleaning.amc[0].name} plan includes ${cleaning.amc[0].summary.toLowerCase()} from ${rupees(cleaning.amc[0].perSqftYear)} per sq ft a year, and every plan comes with a photo report after each visit.`
            : "If you need the plot cleaned more than three or four times a year, ask us about an annual plan.",
          "Most vacant plots in Bangalore need cleaning every three months, and every one to two months during and after the monsoon.",
        ],
      },
    ],
  },
  {
    slug: "nri-guide-bangalore-plot",
    title: "NRI guide: looking after your Bangalore plot from abroad",
    description: "How owners living abroad keep their Bangalore plot clean, protected and documented without travelling, and what to ask a maintenance company.",
    published: "2026-10-26",
    services: ["property-inspection", "plot-cleaning", "fencing-gates"],
    sections: [
      {
        paragraphs: [
          "A vacant plot that nobody visits slowly becomes a problem. Weeds grow, people dump waste, boundary stones go missing and, in the worst cases, someone starts using the land. If you live abroad, the answer is a simple routine and someone you can trust to follow it.",
        ],
      },
      {
        heading: "A routine that works",
        paragraphs: ["This is what we suggest to owners who cannot visit."],
        bullets: [
          "An inspection visit at least every three months, with photos of every boundary",
          "Cleaning before and after the monsoon, and more often if the plot is next to open land",
          "A fence or at least clear boundary markers, so the plot's edges are never in doubt",
          "All photos and reports stored in one place, so you have a record if you sell or build",
        ],
      },
      {
        heading: "What to ask a maintenance company",
        paragraphs: ["Before you pay anyone, ask how you will know each visit really happened."],
        bullets: ["Do you send before and after photos from every visit, with the time?", "Who checks the work before it is marked done?", "Can I see all past visits in one place?", "How do I pay from abroad, and do I get a receipt?"],
      },
      {
        heading: "How GreenPlot does it",
        paragraphs: [
          inspection?.price
            ? `Our Property Watch inspection starts at ${rupees(inspection.price.perSqft)} per sq ft a visit. Every visit is photographed, checked by a supervisor and sent to you on WhatsApp or email, and you pay online.`
            : "Every visit is photographed, checked by a supervisor and sent to you on WhatsApp or email, and you pay online.",
        ],
      },
    ],
  },
  {
    slug: "protect-vacant-plot-encroachment",
    title: "How to protect a vacant plot from encroachment",
    description: "Practical steps Bangalore plot owners can take to keep their land secure: boundaries, fencing, regular visits and keeping your records in order.",
    published: "2026-10-26",
    services: ["fencing-gates", "property-inspection"],
    sections: [
      {
        paragraphs: [
          "Encroachment usually starts small: a pile of building material, a temporary shed, a path across the corner of the plot. It is much easier to stop early, and the best protection is a plot that clearly looks owned and looked after.",
        ],
      },
      {
        heading: "Five steps that help",
        paragraphs: [],
        bullets: [
          "Keep the boundary stones visible and photograph them on every visit",
          "Put up a fence or compound wall, with a gate that locks",
          "Fix a board with the owner's name or a contact number",
          "Visit, or have someone visit, at least every three months",
          "Keep your sale deed, khata and tax receipts safe and up to date",
        ],
      },
      {
        heading: "If something has already happened",
        paragraphs: [
          "Photograph it straight away, note the date, and speak to a property lawyer before you act. Dated photos from regular visits are useful evidence that the plot was clear before.",
        ],
      },
    ],
  },
  {
    slug: "pre-monsoon-plot-checklist",
    title: "Pre-monsoon checklist for Bangalore plot owners",
    description: "What to do to your plot before the Bangalore monsoon: clearing, drainage, trees, fencing and the checks that save money later.",
    published: "2026-10-26",
    services: ["plot-cleaning", "garden-landscape", "fencing-gates"],
    sections: [
      {
        paragraphs: [
          "Bangalore's rains make weeds grow fast and expose any weak fence or blocked drain. A little work before the monsoon, usually in April or May, saves a much bigger cleaning bill later.",
        ],
      },
      {
        heading: "The checklist",
        paragraphs: [],
        bullets: [
          "Clear weeds, dry grass and debris so water can drain",
          "Make sure the plot does not block the drain along the road",
          "Trim trees and branches that hang over neighbours or power lines",
          "Check fence posts and gates, and repair anything loose before the wind and rain",
          "Book a cleaning visit for just after the monsoon",
        ],
      },
      {
        heading: "Plots with gardens",
        paragraphs: [
          garden?.amc?.length
            ? `If your plot has a lawn or trees, a garden plan keeps it under control through the rains. Our ${garden.amc[garden.amc.length - 1].name} garden plan includes tree pruning before the monsoon.`
            : "If your plot has a lawn or trees, plan pruning before the monsoon.",
        ],
      },
    ],
  },
];

export const postBySlug = (slug: string) => POSTS.find((p) => p.slug === slug);
