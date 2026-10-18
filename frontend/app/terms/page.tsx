import type { Metadata } from "next";
import Link from "next/link";
import { ContactBlock, LegalPage } from "@/components/Legal";
import { BUSINESS } from "@/lib/legal";

export const metadata: Metadata = { title: "Terms & Conditions" };

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms & Conditions"
      intro={
        <p>
          These terms govern your use of the {BUSINESS.brand} website, app and services, provided by {BUSINESS.legalName} (&quot;{BUSINESS.brand}&quot;,
          &quot;we&quot;, &quot;us&quot;). By creating an account, booking a service or making a payment, you agree to them. Please also read our{" "}
          <Link href="/privacy">Privacy Policy</Link> and <Link href="/refund-policy">Refund &amp; Cancellation Policy</Link>, which form part of these terms.
        </p>
      }
    >
      <h2>1. What we provide</h2>
      <p>
        {BUSINESS.brand} provides property care services for plots and homes in residential layouts, such as plot cleaning, gardening, inspections, fencing and gate
        work, repairs and maintenance, and an app for layouts to manage maintenance, security, billing and records. Some services are carried out by independent vendors
        we assign.
      </p>

      <h2>2. Accounts</h2>
      <ul>
        <li>You must be at least 18 and give accurate details. Accounts are approved by your layout office.</li>
        <li>Keep your password and sign-in codes private. You are responsible for what happens under your account.</li>
        <li>Tell us straight away if you think someone else has used your account.</li>
        <li>We or your layout office may suspend an account that is misused or breaks these terms.</li>
      </ul>

      <h2>3. Bookings and the work</h2>
      <ul>
        <li>A job is confirmed when it is approved and given a scheduled date. Its scope and price are shown on the job.</li>
        <li>Work outside the agreed scope needs your approval and may cost extra. We will not add work without telling you.</li>
        <li>You must make sure we can safely reach the plot, and tell us about any hazards or disputes affecting it.</li>
        <li>
          Before and after photos and the job record are the agreed evidence that the work was done. Raise any concern within 7 days of completion, as set out in the{" "}
          <Link href="/refund-policy">Refund &amp; Cancellation Policy</Link>.
        </li>
      </ul>

      <h2>4. Prices and payment</h2>
      <ul>
        <li>Prices are in Indian Rupees and include GST where it applies. Your bill shows the breakdown.</li>
        <li>Online payments are processed by Razorpay. By paying online you also accept Razorpay&apos;s terms.</li>
        <li>Bills are due by the date shown. We may pause new jobs on an account with overdue bills.</li>
        <li>Plans renew for the period shown until you cancel them.</li>
      </ul>

      <h2>5. Your responsibilities</h2>
      <p>You agree not to:</p>
      <ul>
        <li>upload content that is unlawful, offensive, or that you have no right to share, including photos of people without a good reason;</li>
        <li>use another person&apos;s details or account, or try to access data you are not allowed to see;</li>
        <li>disrupt the service, upload harmful files, or try to bypass its security;</li>
        <li>use visitor, vehicle or resident information for anything other than running the layout.</li>
      </ul>

      <h2>6. Vendors</h2>
      <p>
        Vendors who join {BUSINESS.brand} must hold any licences their work needs, follow safety rules at the site, upload honest photos and records of the work, and
        keep resident and property details confidential. Payment terms for vendors are agreed separately.
      </p>

      <h2>7. Your content</h2>
      <p>
        You keep ownership of the photos, documents and messages you upload. You allow us and your layout office to store, display and use them to provide the service
        and keep your property&apos;s records.
      </p>

      <h2>8. Our liability</h2>
      <ul>
        <li>We carry out services with reasonable care and skill.</li>
        <li>
          We are not responsible for damage or loss caused by things outside our control, such as weather, natural events, theft, acts of other people, or problems with
          the property that existed before our work.
        </li>
        <li>
          Security features in the app support your layout&apos;s own security arrangements. They are not a guarantee that a property will be safe from intrusion or
          damage.
        </li>
        <li>
          Except where the law does not allow it, our total liability for any claim about a job is limited to the amount you paid for that job, and we are not liable
          for indirect or consequential loss.
        </li>
      </ul>

      <h2>9. Ending your account</h2>
      <p>
        You can ask to close your account at any time. Bills for work already done stay payable. How we handle your data after closure is explained in the{" "}
        <Link href="/privacy">Privacy Policy</Link>.
      </p>

      <h2>10. Changes</h2>
      <p>
        We may update these terms. If a change affects you, we will tell you in the app or by email before it takes effect. Using the service after that means you
        accept the new terms.
      </p>

      <h2>11. Law and disputes</h2>
      <p>
        These terms are governed by the laws of India. We will first try to resolve any dispute with you directly through our Grievance Officer. Otherwise, the courts
        at {BUSINESS.city}, {BUSINESS.state} have exclusive jurisdiction, without affecting your rights under the Consumer Protection Act, 2019.
      </p>

      <h2>12. Contact</h2>
      <ContactBlock />
      <p>
        Grievances can be sent to our <Link href="/contact#grievance">Grievance Officer</Link>.
      </p>
    </LegalPage>
  );
}
