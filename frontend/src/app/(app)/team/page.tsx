import { Suspense } from "react";
import { TeamView } from "@/features/team/team-view";

export default function TeamPage() {
  return <Suspense fallback={null}><TeamView /></Suspense>;
}
