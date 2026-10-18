import type { Metadata } from "next";
import Link from "next/link";
import { ContactBlock, LegalPage } from "@/components/Legal";

export const metadata: Metadata = { title: "Contact Us" };

export default function ContactPage() {
  return (
    <LegalPage title="Contact Us" intro={<p>We&apos;re happy to help with services, bookings, payments, your account or anything else.</p>}>
      <h2>Customer support</h2>
      <ContactBlock />
      <p>
        If you have an account, the quickest way to get help with a job is to <Link href="/login?next=/tickets">raise a ticket</Link> in the app.
      </p>

      <h2 id="grievance">Grievance Officer</h2>
      <p>
        If you are not satisfied with how a complaint was handled, or have a concern about your personal data, you can write to our Grievance Officer. We acknowledge
        every grievance within 48 hours and aim to resolve it within 30 days.
      </p>
      <ContactBlock grievance />
    </LegalPage>
  );
}
