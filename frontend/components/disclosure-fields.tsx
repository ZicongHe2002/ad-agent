import type { DisclosureStatus } from "@/lib/types";

export type ResolvedDisclosure = Extract<DisclosureStatus, "DECLARED" | "PLATFORM_APPLIED" | "NOT_REQUIRED">;

export function DisclosureFields({ status, evidence, onStatus, onEvidence, disabled = false }: {
  status: ResolvedDisclosure | "";
  evidence: string;
  onStatus(value: ResolvedDisclosure | ""): void;
  onEvidence(value: string): void;
  disabled?: boolean;
}) {
  return <fieldset className="stack" disabled={disabled} style={{ border: "1px solid var(--line)", borderRadius: 12, padding: 16 }}>
    <legend>Disclosure decision</legend>
    <div className="field"><label htmlFor="disclosure-status">Verified disclosure outcome</label>
      <select id="disclosure-status" className="select" value={status} onChange={(event) => onStatus(event.target.value as ResolvedDisclosure | "")}>
        <option value="">Keep existing verified decision</option>
        <option value="DECLARED">Disclosure included in the final comment</option>
        <option value="PLATFORM_APPLIED">Platform disclosure applied</option>
        <option value="NOT_REQUIRED">Not required by the verified policy</option>
      </select>
    </div>
    <div className="field"><label htmlFor="disclosure-evidence">Evidence and policy reference</label>
      <textarea id="disclosure-evidence" className="textarea" value={evidence} onChange={(event) => onEvidence(event.target.value)} placeholder="Describe the actual disclosure, platform label, or applicable policy and its source." required={Boolean(status)} />
    </div>
    <small className="cell-secondary">An unresolved disclosure needs an explicit decision and evidence. Brand disclosure cannot be waived for an identity that requires it.</small>
  </fieldset>;
}

export function disclosurePayload(status: ResolvedDisclosure | "", evidence: string) {
  if (!status) return {};
  if (!evidence.trim()) throw new Error("Record disclosure evidence before confirming this decision.");
  return { disclosure_status: status, disclosure_evidence: { operator_notes: evidence.trim() } };
}
