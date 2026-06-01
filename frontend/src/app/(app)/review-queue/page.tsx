import { Suspense } from "react";
import { OpportunityListView } from "@/features/opportunities/opportunity-list-view";

export default function ReviewQueuePage() {
  return <Suspense fallback={null}><OpportunityListView reviewOnly /></Suspense>;
}
