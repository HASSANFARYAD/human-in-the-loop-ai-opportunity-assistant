import { Suspense } from "react";
import { AutomationView } from "@/features/automation/automation-view";

export default function AutomationPage() {
  return <Suspense fallback={null}><AutomationView /></Suspense>;
}
