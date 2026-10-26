import type { Metadata } from "next";
import Link from "next/link";
import { ContactBlock, LegalPage } from "@/components/Legal";
import { BUSINESS } from "@/lib/legal";
import { pageOpenGraph } from "@/lib/site";

export const metadata: Metadata = {
  title: "Refund & Cancellation Policy",
  description: "How to cancel or reschedule a GreenPlot visit, when you get a refund, and how long refunds take to reach your account.",
  alternates: { canonical: "/refund-policy" },
  openGraph: pageOpenGraph({ title: "Refund & Cancellation Policy", description: "How to cancel or reschedule a GreenPlot visit, when you get a refund, and how long refunds take to reach your account.", url: "/refund-policy" }),
};

export default function RefundPolicyPage() {
  return (
    <LegalPage
      title="Refund & Cancellation Policy"
      intro={
        <p>
          This policy explains when you can cancel a {BUSINESS.brand} service and how refunds work for payments made through our website or app.
          Online payments are processed by Razorpay.
        </p>
      }
    >
      <h2>1. Cancelling a scheduled job</h2>
      <ul>
        <li>
          <b>More than 24 hours before the scheduled visit:</b> you can cancel free of charge. Any amount you paid is refunded in full.
        </li>
        <li>
          <b>Within 24 hours of the visit:</b> we may keep a visit charge to cover the team or vendor already assigned. We tell you the charge before you confirm
          the cancellation, and the rest is refunded.
        </li>
        <li>
          <b>After work has started:</b> the job can be stopped, but you pay for the work done and materials already bought. Any balance is refunded.
        </li>
      </ul>
      <p>
        To cancel, raise a ticket on the job in the app, or write to <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a> with the job number.
      </p>

      <h2>2. When we cancel</h2>
      <p>
        If we cannot carry out a job (for example, the plot cannot be reached, a vendor is unavailable, or the weather makes the work unsafe), we will offer a new date. If
        you do not want to reschedule, we refund the full amount paid for that job.
      </p>

      <h2>3. Work not done or not done properly</h2>
      <p>
        Every completed job carries before and after photos. If you believe a job was not completed or not done to the agreed standard, tell us within <b>7 days</b> of
        it being marked complete, through the job&apos;s feedback or by email. We will review the photos and the job record and, at our option:
      </p>
      <ul>
        <li>send a team to redo the work at no extra cost, or</li>
        <li>refund the part of the payment that covers the work not done.</li>
      </ul>
      <p>Complaints raised after 7 days are reviewed case by case.</p>

      <h2>4. Plans and recurring services</h2>
      <p>
        If you are on a monthly or yearly plan, you can cancel at any time. The plan stays active until the end of the period you have paid for and is not renewed after
        that. We do not refund part of a period already started, except where a service in that period was not delivered, in which case section 3 applies.
      </p>

      <h2>5. Plants bought from the online store</h2>
      <p>
        Plants ordered from our <Link href="/store">plant store</Link> are living goods, so they are handled differently from service bookings:
      </p>
      <ul>
        <li>You can cancel an order free of charge any time before it is sent out for delivery; an online payment is refunded in full.</li>
        <li>
          If a plant arrives damaged, broken or not the plant you ordered, tell us within <b>48 hours</b> of delivery with photos. We replace it on the next delivery
          run, or refund that item in full, whichever you prefer.
        </li>
        <li>
          You can also refuse a plant at the door if it is clearly unhealthy, and pay nothing for it. We cannot take plants back later for change of mind, because a
          plant&apos;s condition depends on how it is kept after delivery.
        </li>
        <li>Plants that decline after 48 hours are not refunded, but send us a photo and we will advise you on how to revive them at no charge.</li>
      </ul>

      <h2>6. Duplicate or extra payments</h2>
      <p>
        If you are charged twice, or pay more than the bill, we refund the extra amount once it is identified. You do not need to ask, but you can write to us to speed
        it up.
      </p>

      <h2>7. How refunds are paid</h2>
      <ul>
        <li>Refunds go back to the payment method you used (card, UPI, net banking or wallet).</li>
        <li>
          We start an approved refund within <b>2 working days</b>. Your bank or card issuer usually credits it within <b>5 to 7 working days</b> after that.
        </li>
        <li>Payment gateway charges are not deducted from refunds for cancellations made by us.</li>
        <li>Payments made in cash or by direct bank transfer are refunded by bank transfer to an account you name.</li>
      </ul>

      <h2>8. Contact</h2>
      <p>For any cancellation or refund question, contact us:</p>
      <ContactBlock />
      <p className="small muted">
        See also our <Link href="/terms">Terms &amp; Conditions</Link> and <Link href="/service-delivery">Service Delivery Policy</Link>.
      </p>
    </LegalPage>
  );
}
