"use client";

import Link from "next/link";
import { ReportProblemForm, WhatsAppLink } from "@/components/Support";
import { PageHead } from "@/components/ui";

export default function ReportProblemPage() {
  return (
    <>
      <PageHead title="Report a problem" sub="Tell us what's wrong and we'll send someone to fix it." />
      <div className="grid two" style={{ alignItems: "start" }}>
        <div className="card">
          <ReportProblemForm />
        </div>
        <div className="card" style={{ marginTop: 0 }}>
          <h2>What happens next</h2>
          <ol className="small" style={{ paddingLeft: 18, lineHeight: 1.7 }}>
            <li>Your report becomes a service ticket with a number you can track.</li>
            <li>The office reviews it and assigns staff or a vendor to do the job.</li>
            <li>You get updates when work starts and finishes, with photos.</li>
            <li>When it&apos;s done, you rate the job so we know how we did.</li>
          </ol>
          <p className="small muted" style={{ marginTop: 10 }}>
            Need more detail, a preferred visit time or a priority? Use the full <Link href="/tickets">service ticket form</Link>. Urgent? <WhatsAppLink>Message us on WhatsApp</WhatsAppLink>.
          </p>
        </div>
      </div>
    </>
  );
}
