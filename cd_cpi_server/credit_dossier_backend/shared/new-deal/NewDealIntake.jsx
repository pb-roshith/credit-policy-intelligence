import React, { useEffect, useRef, useState } from "react";
import SearchableSelect from "./SearchableSelect";
import { CURRENCIES } from "./currencies";
import "./new-deal.css";

const defaults = {
  customer: "", customer_type: "Existing", industry: "", segment: "Mid Corporate",
  geography: "", kyc: "pending", facility: "Term Loan", currency: "INR",
  amount: "", tenure: 12, pricing: "", repayment: "Equated quarterly", collateral: true, due: "",
  rating: "BB", collateral_coverage: 100, total_required_documents: 1, uploaded_required_documents: 0,
};
const currencies = CURRENCIES.flatMap(group => group.items.map(currency => ({
  value: currency.code, label: `${currency.symbol} ${currency.code} — ${currency.name}`,
  search: `${currency.country} ${currency.keywords || ""}`, description: group.group,
})));

export default function NewDealIntake({ createDeal, onCreated, onCancel, loadCompanies, getCompanyDetails }) {
  const [form, setForm] = useState(defaults);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lookupError, setLookupError] = useState("");
  const [enriching, setEnriching] = useState(false);
  const attempt = useRef(null);
  const inFlight = useRef(false);
  const selection = useRef(0);
  const set = (key, value) => {
    if (key === "customer") { selection.current += 1; setEnriching(false); }
    setForm(current => ({ ...current, [key]: value }));
  };

  useEffect(() => {
    let active = true;
    if (!loadCompanies) return;
    setLoading(true);
    Promise.resolve().then(loadCompanies).then(rows => {
      if (active) { setCompanies(rows || []); setLookupError(""); }
    }).catch(() => { if (active) setLookupError("Company lookup is unavailable. Type the legal name in the company selector."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; selection.current += 1; };
  }, [loadCompanies]);

  async function chooseCompany(name) {
    const version = ++selection.current;
    setLookupError("");
    setForm(current => ({ ...current, customer: name }));
    if (!getCompanyDetails || !companies.some(company => company.name === name)) { setEnriching(false); return; }
    setEnriching(true);
    try {
      const details = await getCompanyDetails(name);
      if (selection.current !== version) return;
      // Match Dossier's company selection defaults for the facility.
      const due = new Date(); due.setMonth(due.getMonth() + 1);
      const localDate = `${due.getFullYear()}-${String(due.getMonth() + 1).padStart(2, "0")}-${String(due.getDate()).padStart(2, "0")}`;
      setForm(current => ({ ...current,
        industry: details?.industry || "", segment: details?.segment || "Mid Corporate",
        geography: details?.geography || "",
        kyc: details?.kyc_status?.toLowerCase() === "verified" ? "verified" : "pending",
        pricing: "Repo + 285 bps", amount: 100000000, tenure: 60, due: localDate,
      }));
    } catch {
      if (selection.current === version) setLookupError("Company details are unavailable. Complete the customer details manually.");
    } finally { if (selection.current === version) setEnriching(false); }
  }

  async function submit(event) {
    event.preventDefault();
    if (inFlight.current || enriching) return;
    if (form.uploaded_required_documents > form.total_required_documents) {
      setError("Supplied documents cannot exceed required documents."); return;
    }
    const payload = { ...form, amount: Number(form.amount), customer: form.customer.trim(), geography: form.geography.trim() };
    const signature = JSON.stringify(payload);
    if (!attempt.current || attempt.current.signature !== signature) attempt.current = { signature, id: crypto.randomUUID().replaceAll("-", "") };
    setBusy(true); inFlight.current = true; setError("");
    try { onCreated(await createDeal({ ...payload, creation_request_id: attempt.current.id })); }
    catch (failure) { setError(failure.message || "Unable to create the deal. Please retry."); }
    finally { setBusy(false); inFlight.current = false; }
  }

  const field = (key, label, control, required = false) => <div className="shared-deal-field" key={key}>
    <label htmlFor={`new-deal-${key}`}>{label}{required && <span aria-hidden="true"> *</span>}</label>{control}
  </div>;
  const input = (key, label, type = "text", attributes = {}) => field(key, label,
    <input id={`new-deal-${key}`} type={type} value={form[key]} {...attributes}
      onChange={event => set(key, type === "number" && event.target.value !== "" ? Number(event.target.value) : event.target.value)} />, attributes.required);
  const select = (key, label, options) => field(key, label,
    <select id={`new-deal-${key}`} value={String(form[key])} onChange={event => set(key, key === "collateral" ? event.target.value === "true" : event.target.value)}>
      {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
    </select>);

  return <form className="shared-new-deal" onSubmit={submit}>
    <h2>Create New Deal</h2>
    <fieldset disabled={busy}>
      <section className="shared-deal-section" aria-labelledby="deal-customer-heading">
        <div className="shared-deal-section-header" id="deal-customer-heading">Customer Details</div>
        <div className="shared-deal-grid">
          {field("customer", "Legal name", <>
            <SearchableSelect inputId="new-deal-customer" allowCustom value={form.customer} onChange={chooseCompany} loading={loading}
              placeholder="Select company…" searchPlaceholder="Search company name…"
              options={companies.map(company => ({ value: company.name, label: company.name,
                description: company.library_access_error ? "Mistral Library unavailable" : `${company.document_count || 0} docs` }))} />
          </>, true)}
          {select("customer_type", "Customer type", [["Existing", "Existing"], ["New-to-bank", "New-to-bank"]])}
          {input("industry", "Industry", "text", { maxLength: 128 })}
          {select("segment", "Segment", [["SME", "SME"], ["Mid Corporate", "Mid Corporate"], ["Large Corporate", "Large Corporate"]])}
          {input("geography", "Geography", "text", { maxLength: 128 })}
          {select("kyc", "KYC status", [["verified", "Verified"], ["pending", "Pending"]])}
          {(lookupError || enriching) && <p className="shared-lookup-note" role="status">{enriching ? "Filling customer details…" : lookupError}</p>}
        </div>
      </section>
      <section className="shared-deal-section" aria-labelledby="deal-facility-heading">
        <div className="shared-deal-section-header" id="deal-facility-heading">Facility Details</div>
        <div className="shared-deal-grid">
          {select("facility", "Product / facility type", [["Term Loan", "Term Loan"], ["Working Capital", "Working Capital"], ["Syndicated Loan", "Syndicated Loan"]])}
          {field("currency", "Currency", <SearchableSelect inputId="new-deal-currency" value={form.currency} onChange={value => set("currency", value)}
            options={currencies} placeholder="Select currency…" searchPlaceholder="Search by country, currency or symbol…" />)}
          {input("amount", "Amount (in units of currency)", "number", { required: true, min: 0.01, max: 1000000000000000, step: "0.01" })}
          {input("tenure", "Tenure (months)", "number", { required: true, min: 1, max: 1200, step: 1 })}
          {input("pricing", "Pricing", "text", { maxLength: 128 })}
          {input("repayment", "Repayment", "text", { maxLength: 128 })}
          {select("collateral", "Collateral required", [["true", "Yes"], ["false", "No (Clean)"]])}
          {input("due", "Target completion date", "date")}
        </div>
      </section>
    </fieldset>
    {error && <p className="shared-deal-error" role="alert">{error}</p>}
    <div className="shared-deal-actions"><button type="button" disabled={busy} onClick={onCancel}>Cancel</button>
      <button type="submit" disabled={busy || enriching || !form.customer.trim()}>{busy ? "Creating…" : "Create deal"}</button></div>
  </form>;
}
