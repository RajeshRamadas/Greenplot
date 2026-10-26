import type { Metadata } from "next";
import Link from "next/link";
import { ContactBlock, LegalPage } from "@/components/Legal";
import { BUSINESS } from "@/lib/legal";

export const metadata: Metadata = { title: "Service Delivery Policy" };

export default function ServiceDeliveryPage() {
  return (
    <LegalPage
      title="Service Delivery Policy"
      intro={
        <p>
          {BUSINESS.brand} provides property care services (plot cleaning, gardening, inspections, fencing and gate work, repairs and maintenance) and the software to
          track them. We do not ship physical goods. This page explains how and when services are delivered.
        </p>
      }
    >
      <h2>1. Where we work</h2>
      <p>
        We deliver services at plots and properties in the layouts and areas we serve, listed when you request a service. If an address is outside our area, we tell you
        before you pay.
      </p>

      <h2>2. When the work happens</h2>
      <ul>
        <li>Each job is given a scheduled date when it is booked or approved. You can see it in the app.</li>
        <li>One-off jobs are normally scheduled within 3 to 7 working days of booking, depending on the type of work and vendor availability.</li>
        <li>Recurring services (for example monthly cleaning or inspections) are carried out in each period of your plan.</li>
        <li>Urgent tickets, such as a leak or a broken gate, are attended to as soon as a team is available.</li>
      </ul>

      <h2>3. Access to the property</h2>
      <p>
        You must give us safe access to the plot on the scheduled date, through the layout office, a key holder or an open plot. If we cannot get in, we reschedule the
        visit and the cancellation terms in our <Link href="/refund-policy">Refund &amp; Cancellation Policy</Link> apply.
      </p>

      <h2>4. Proof of delivery</h2>
      <p>
        A service counts as delivered when the assigned team marks the job complete with before and after photos, which are timestamped and may carry the location they
        were taken at. You are notified in the app and, if you opted in, by WhatsApp, SMS or email. Photos and job notes stay in your property&apos;s records.
      </p>

      <h2>5. Delays</h2>
      <p>
        If a job will miss its scheduled date, we tell you and give a new date. If the delay is not acceptable to you, you can cancel the job for a full refund of any
        amount paid for it.
      </p>

      <h2>6. Plants bought from the online store</h2>
      <p>
        Plants ordered from our <Link href="/store">plant store</Link> are delivered by our own team within Bangalore, usually in <b>2 to 4 working days</b>. We call
        the number on the order before we come. Delivery is free over the amount shown at checkout, and a delivery charge is added below it, which you see before you
        pay. Plants are delivered in their nursery pots, watered, with care notes. You can pay online or in cash on delivery, and the bill for the order is on your
        order page the moment it is placed.
      </p>

      <h2>7. Digital access</h2>
      <p>
        Access to the {BUSINESS.brand} app is given by email and text message once the layout office approves your account. There is nothing to download or ship.
      </p>

      <h2>8. Contact</h2>
      <ContactBlock />
    </LegalPage>
  );
}
