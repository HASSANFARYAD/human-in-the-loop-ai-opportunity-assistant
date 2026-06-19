import { Suspense } from "react";
import { SettingsView } from "@/features/dashboard/settings-view";

export default function SettingsPage() {
  return <Suspense fallback={null}><SettingsView /></Suspense>;
}
