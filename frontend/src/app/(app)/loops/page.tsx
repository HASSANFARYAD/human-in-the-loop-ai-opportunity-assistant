import { Suspense } from "react";
import { LoopsView } from "@/features/loops/loops-view";

export default function LoopsPage() {
  return (
    <Suspense fallback={null}>
      <LoopsView />
    </Suspense>
  );
}
