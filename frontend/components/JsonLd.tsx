/** schema.org structured data for search engines, as one @graph. */
export function JsonLd({ items }: { items: object[] }) {
  const data = { "@context": "https://schema.org", "@graph": items };
  // "<" is escaped so text in the data can never close the script tag.
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }} />;
}
