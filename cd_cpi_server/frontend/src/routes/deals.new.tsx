import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { api } from "@/lib/deals";
import { useAuth } from "@/lib/auth";
import NewDealForm from "../../../backend/shared/new-deal/NewDealForm";

export const Route = createFileRoute("/deals/new")({
  head: () => ({ meta: [{ title: "New Deal - Credit Dossier" }] }),
  component: NewDeal,
});

function NewDeal() {
  const { user } = useAuth();
  const router = useRouter();
  if (user?.role !== "relationship_manager") {
    return <main className="mx-auto max-w-2xl px-4 py-12 text-center">
      <h1>Only Relationship Managers can create a new deal.</h1><Link to="/">Return to Dashboard</Link>
    </main>;
  }
  return <main className="mx-auto max-w-3xl px-4 py-8">
    <NewDealForm createDeal={api.deals.create}
      onCreated={deal => router.navigate({ to: "/deals/$dealId", params: { dealId: deal.id } })}
      onCancel={() => router.navigate({ to: "/" })}
      loadCompanies={api.companies.list}
      getCompanyDetails={api.companies.details}
    />
  </main>;
}
