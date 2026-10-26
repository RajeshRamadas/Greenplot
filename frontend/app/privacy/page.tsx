import type { Metadata } from "next";
import Link from "next/link";
import { ContactBlock, LegalPage } from "@/components/Legal";
import { BUSINESS } from "@/lib/legal";
import { pageOpenGraph } from "@/lib/site";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "How GreenPlot collects, uses, stores and protects your personal data, photos and payment details, and how to reach our Grievance Officer.",
  alternates: { canonical: "/privacy" },
  openGraph: pageOpenGraph({ title: "Privacy Policy", description: "How GreenPlot collects, uses, stores and protects your personal data, photos and payment details, and how to reach our Grievance Officer.", url: "/privacy" }),
};

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      intro={
        <p>
          This policy explains what personal data {BUSINESS.legalName} (&quot;{BUSINESS.brand}&quot;, &quot;we&quot;) collects through our website and app, why we
          collect it, who we share it with and the choices you have. It is written to meet the Digital Personal Data Protection Act, 2023 and the Information Technology
          Act, 2000.
        </p>
      }
    >
      <h2>1. Who this covers</h2>
      <p>
        Plot owners, residents and tenants, layout office staff, supervisors, security guards, field staff, vendors, and anyone who visits our website or requests a
        demo. Layout associations that use {BUSINESS.brand} decide who in their layout gets an account; for records they keep about their layout, we process the data
        on their behalf.
      </p>

      <h2>2. What we collect</h2>
      <ul>
        <li>
          <b>Account details:</b> name, email, mobile number, role, and for vendors the company name and services offered.
        </li>
        <li>
          <b>Property details:</b> plot number, layout, ownership or tenancy, household members you add, and property records and documents.
        </li>
        <li>
          <b>Photos and job records:</b> before and after photos, inspection photos and notes. Photos are timestamped and may include the location where they were
          taken.
        </li>
        <li>
          <b>Security records:</b> visitor names, phone numbers and purpose of visit, vehicle numbers, gate entries, patrol checkpoints and incident reports.
        </li>
        <li>
          <b>Staff records:</b> attendance check-ins, which may include the time and location of the check-in.
        </li>
        <li>
          <b>Payments:</b> bills, amounts, payment status and the reference numbers Razorpay gives us. Your card, UPI or bank details are entered on Razorpay and are
          never stored by us.
        </li>
        <li>
          <b>Messages:</b> tickets, complaints, comments and WhatsApp messages you send to our business number.
        </li>
        <li>
          <b>Technical data:</b> IP address, device and browser type, and sign-in records, kept for security and to prevent misuse.
        </li>
      </ul>

      <h2>3. Why we use it</h2>
      <ul>
        <li>To create and secure your account, including sign-in codes sent by SMS, WhatsApp or email.</li>
        <li>To schedule, carry out, verify and record maintenance and other services for your property.</li>
        <li>To run layout security: visitor approvals, vehicle logs, patrols and incident handling.</li>
        <li>To bill you, take payments and issue refunds.</li>
        <li>To send you updates about your jobs, tickets, bills and layout notices.</li>
        <li>To answer support requests and handle complaints.</li>
        <li>To meet legal, tax and accounting obligations, and to protect our users and the service against fraud and misuse.</li>
      </ul>
      <p>We do not sell your personal data and we do not use it for third-party advertising.</p>

      <h2>4. Your consent and choices</h2>
      <ul>
        <li>We process your data on the basis of the consent you give when you register or use the service, or where the law otherwise allows.</li>
        <li>
          WhatsApp updates are sent only if you opt in, and you can switch them off in your profile at any time. Sign-in and security codes are always sent, because
          the account cannot work without them.
        </li>
        <li>
          You can withdraw consent at any time by writing to us. Withdrawing consent does not affect processing already done, but we may no longer be able to provide
          the service.
        </li>
      </ul>

      <h2>5. Who we share it with</h2>
      <p>We share data only as needed to run the service:</p>
      <ul>
        <li>
          <b>Your layout:</b> the layout office and its staff see the records of the layout they manage, according to their role.
        </li>
        <li>
          <b>Vendors and field staff:</b> the details needed to do a job, such as the plot location and the job description.
        </li>
        <li>
          <b>Service providers:</b> Razorpay (payments), Meta (WhatsApp messages), our SMS provider, our email provider, and our cloud hosting and storage providers.
          They may only use the data to provide their service to us.
        </li>
        <li>
          <b>Authorities:</b> where the law requires it, or to protect someone&apos;s safety, for example in a security incident.
        </li>
      </ul>

      <h2>6. How long we keep it</h2>
      <p>
        We keep account and property records while your account is active, because the point of {BUSINESS.brand} is a lasting history of your property. When an
        account is closed we delete or anonymise its personal data within 90 days, except records we must keep longer by law (such as invoices and payment records,
        kept for 8 years) or that the layout needs for its own property history. Security logs such as visitor and vehicle entries are kept for up to 1 year unless an
        incident requires longer.
      </p>

      <h2>7. How we protect it</h2>
      <p>
        Data is sent over HTTPS, passwords are stored hashed, photos and documents are kept in private storage and opened only through short-lived links, access is
        limited by role and by layout, and important actions are recorded in an audit log. No system is perfectly secure; if a breach affects your data, we will tell
        you and the Data Protection Board of India as the law requires.
      </p>

      <h2>8. Your rights</h2>
      <p>You can ask us to:</p>
      <ul>
        <li>give you a summary of the personal data we hold about you and how it is used;</li>
        <li>correct, complete or update your data;</li>
        <li>erase your data when it is no longer needed for the purpose it was collected for;</li>
        <li>nominate someone to exercise these rights for you in case of death or incapacity.</li>
      </ul>
      <p>
        Write to our Grievance Officer at the address below. We respond within 30 days. If you are not satisfied with our response, you can complain to the Data
        Protection Board of India.
      </p>

      <h2>9. Cookies and local storage</h2>
      <p>
        We do not use advertising or tracking cookies. The app stores a sign-in token and a few settings in your browser so you stay signed in and can use parts of the
        app offline. Clearing your browser data removes them.
      </p>

      <h2>10. Children</h2>
      <p>Accounts are for adults. We do not knowingly collect personal data from children under 18 except as household or visitor details added by an adult.</p>

      <h2>11. Changes to this policy</h2>
      <p>
        If we change this policy in a way that affects you, we will tell you in the app or by email before the change takes effect. The date at the top shows when it
        was last updated.
      </p>

      <h2>12. Contact and grievances</h2>
      <ContactBlock grievance />
      <p className="small muted">
        See also our <Link href="/terms">Terms &amp; Conditions</Link>.
      </p>
    </LegalPage>
  );
}
