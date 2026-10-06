/** After creating or re-inviting a user: say where the invite went, and copy the link as a fallback. */
export async function announceInvite(r: { invite_url?: string | null; sent_via?: string[] } | undefined, toast: (t: string, k?: "ok" | "error") => void, what = "Invite") {
  if (!r?.invite_url) return;
  await navigator.clipboard?.writeText(r.invite_url).catch(() => {});
  const via = (r.sent_via ?? []).map((c) => ({ email: "email", whatsapp: "WhatsApp", sms: "SMS" })[c] ?? c);
  toast(via.length ? `${what} sent by ${via.join(" & ")}. Link also copied.` : `${what} link copied — share it with them.`);
}
