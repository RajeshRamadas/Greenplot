/**
 * Cities and areas with their own pages at /<city> and /<city>/<area>.
 * To open a new city, add it here with live: false, fill in its areas and photos, then set live: true.
 * Only live cities are linked, listed in the sitemap and built as pages.
 */

export interface Area {
  slug: string;
  name: string;
  /** Where the area is and why plots there need looking after. Written for this area only. */
  intro: string;
  /** Localities and layouts nearby that the area page covers. */
  localities: string[];
  /** What owners here most often ask for, in their words. */
  needs: string[];
}

export interface City {
  slug: string;
  name: string;
  state: string;
  live: boolean;
  intro: string;
  areas: Area[];
}

export const CITIES: City[] = [
  {
    slug: "bangalore",
    name: "Bangalore",
    state: "Karnataka",
    live: true,
    intro:
      "Bangalore has thousands of vacant plots in layouts on every side of the city, and many of their owners live in another city or abroad. GreenPlot cleans, fences, inspects and looks after these plots on a schedule, and sends photos of every visit so you know the work was done.",
    areas: [
      {
        slug: "devanahalli",
        name: "Devanahalli",
        intro:
          "Devanahalli, near Kempegowda International Airport in North Bangalore, has some of the city's largest plotted layouts. Many plots here were bought as long-term investments and stay vacant for years, so weeds, dumped waste and missing boundary stones are common.",
        localities: ["Devanahalli town", "Vijayapura Road", "Sadahalli", "Chikkajala", "Venkatagirikote"],
        needs: ["Regular plot cleaning so the plot stays visible and saleable", "Boundary stones and fencing kept intact", "Photo reports for owners who live abroad"],
      },
      {
        slug: "sarjapur-road",
        name: "Sarjapur Road",
        intro:
          "Sarjapur Road runs south-east from the Outer Ring Road towards Sarjapur town, with new plotted layouts growing on both sides. Plots near busy construction sites fill up with debris quickly, and owners often need help keeping them clear between visits.",
        localities: ["Dommasandra", "Kodathi", "Muthanallur", "Sarjapur town", "Hadosiddapura"],
        needs: ["Construction debris and litter cleared", "Plot fencing and gates repaired", "A monthly check while the owner plans to build"],
      },
      {
        slug: "electronic-city",
        name: "Electronic City and Hosur Road",
        intro:
          "Electronic City and the layouts along Hosur Road are popular with people who work in the tech parks nearby. Plots here sit between busy roads and new apartments, so dumped waste and fast weed growth after the rains are the usual problems.",
        localities: ["Electronic City Phase 1 and 2", "Hebbagodi", "Bommasandra", "Huskur"],
        needs: ["Weed and waste clearing after the monsoon", "Quick repairs to gates and compound walls", "Photo proof for owners who rarely visit"],
      },
      {
        slug: "anekal",
        name: "Anekal and Chandapura",
        intro:
          "Anekal, Chandapura and Attibele, near the Karnataka and Tamil Nadu border, have many affordable plotted layouts. Plots are often far from the owner's home, so regular cleaning and a reliable person to check on the plot matter most.",
        localities: ["Chandapura", "Anekal town", "Attibele", "Jigani"],
        needs: ["Scheduled cleaning so the plot does not turn into a dumping spot", "Inspection visits with a condition report", "Fence repair along open boundaries"],
      },
      {
        slug: "kanakapura-road",
        name: "Kanakapura Road",
        intro:
          "Kanakapura Road runs south from the city past the NICE Road junction, with green, open layouts and a fast-growing number of plots. Plots near open land grow thick grass and shrubs quickly, so owners usually want cleaning several times a year.",
        localities: ["Konanakunte", "Talaghattapura", "Thataguni", "Harohalli"],
        needs: ["Grass and shrub clearing several times a year", "Garden upkeep for plots with trees", "Boundary checks to prevent encroachment"],
      },
      {
        slug: "mysore-road",
        name: "Mysore Road",
        intro:
          "Mysore Road and the Bangalore-Mysore expressway have opened up plotted layouts from Kengeri out to Bidadi. Many of these plots are bought by families planning to build later, and they need simple, regular upkeep until then.",
        localities: ["Kengeri", "Kumbalgodu", "Bidadi", "Rajarajeshwari Nagar"],
        needs: ["Plot cleaning on a quarterly plan", "Fencing to mark and protect the plot", "Photo updates before a planned sale or construction"],
      },
      {
        slug: "bannerghatta-road",
        name: "Bannerghatta Road",
        intro:
          "Bannerghatta Road runs south towards the national park, with layouts in Gottigere, Kalena Agrahara and beyond. Owners here often have a plot and a home close by, and want gardens, gates and common areas looked after properly.",
        localities: ["Gottigere", "Kalena Agrahara", "Hulimavu", "Bannerghatta town"],
        needs: ["Garden and landscape maintenance", "Gate and fence repairs", "Small repairs in layout common areas"],
      },
      {
        slug: "whitefield-hoskote",
        name: "Whitefield and Hoskote",
        intro:
          "East of Whitefield, layouts stretch along Old Madras Road towards Hoskote. Plots here are popular with buyers who work in Whitefield, and vacant ones quickly gather waste from the busy roads around them.",
        localities: ["Kadugodi", "Budigere Cross", "Hoskote town", "Soukya Road"],
        needs: ["Waste and debris clearing", "Inspections with photos for owners living away", "Fencing and gate work"],
      },
      {
        slug: "hennur-thanisandra",
        name: "Hennur and Thanisandra",
        intro:
          "Hennur, Thanisandra and the Bagalur Road layouts in North-east Bangalore mix new homes with plots that are still empty. Owners usually want the empty plot kept tidy so it does not bother the neighbours who already live there.",
        localities: ["Hennur", "Thanisandra", "Kothanur", "Bagalur Road"],
        needs: ["Monthly cleaning to keep neighbours happy", "Compound wall and gate repairs", "Garden upkeep for corner plots"],
      },
      {
        slug: "yelahanka",
        name: "Yelahanka",
        intro:
          "Yelahanka in North Bangalore has established layouts close to the airport road, with plots that have often been held for many years. Older plots need boundary checks and clearing of tall growth before the owner can sell or build.",
        localities: ["Yelahanka New Town", "Jakkur", "Kogilu", "Attur"],
        needs: ["Clearing tall growth on long-vacant plots", "Boundary and encroachment checks", "Photo reports before a sale"],
      },
      {
        slug: "doddaballapur-road",
        name: "Doddaballapur Road",
        intro:
          "Doddaballapur Road runs north-west from Yelahanka through Rajanukunte, with spacious plotted layouts and farm plots. Bigger plots need more work, so owners here often choose an annual plan instead of paying per visit.",
        localities: ["Rajanukunte", "Doddaballapur town"],
        needs: ["Annual cleaning plans for large plots", "Fencing for long open boundaries", "Regular inspection visits"],
      },
      {
        slug: "tumkur-road",
        name: "Tumkur Road and Nelamangala",
        intro:
          "Tumkur Road, past the BIEC exhibition centre towards Nelamangala, has industrial areas and growing plotted layouts. Plots near the highway collect waste quickly, and owners want a team that turns up on schedule without being chased.",
        localities: ["Madanayakanahalli", "Nelamangala", "Makali", "Dabaspet"],
        needs: ["Scheduled cleaning with photo proof", "Gate and fence repairs", "Inspection visits for owners living away"],
      },
    ],
  },
];

export const liveCities = () => CITIES.filter((c) => c.live);
export const cityBySlug = (slug: string) => liveCities().find((c) => c.slug === slug);
export const areaBySlug = (city: City, slug: string) => city.areas.find((a) => a.slug === slug);
