import { Suspense } from "react";
import { OpportunityListView } from "@/features/opportunities/opportunity-list-view";

export default function OpportunitiesPage() {
  return <Suspense fallback={null}><OpportunityListView /></Suspense>;
}
