import React from "react";
import "./new-deal.css";
export { default } from "./NewDealIntake";

export function SharedDealCard({ deal }) {
  const intake = deal.intake;
  return <article className="shared-deal-card">
    <div className="shared-deal-heading"><h3>{deal.customer}</h3><span>{deal.status}</span></div>
    <p><strong>{deal.id}</strong> · {deal.facility} · {deal.currency} {Number(deal.amount).toLocaleString()} · {deal.tenure} months</p>
    <p>{deal.industry} · {deal.geography} · KYC {deal.kyc}</p>
    {intake?.summary && <><h4>New Deal agent summary</h4><p>{intake.summary}</p>
      <ul>{(intake.next_steps || []).map((step, index) => <li key={index}>{step}</li>)}</ul></>}
    {intake && <small>Rating {intake.rating} · Collateral coverage {intake.collateral_coverage}% · Documents {intake.uploaded_required_documents}/{intake.total_required_documents}</small>}
  </article>;
}
