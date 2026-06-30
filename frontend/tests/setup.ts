import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

if (typeof Element.prototype.scrollTo !== "function") {
  Element.prototype.scrollTo = vi.fn() as unknown as typeof Element.prototype.scrollTo;
}

if (typeof window !== "undefined" && typeof window.localStorage === "undefined") {
  const store: Record<string, string> = {};
  Object.defineProperty(window, "localStorage", {
    value: {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => { store[key] = value; },
      removeItem: (key: string) => { delete store[key]; },
      clear: () => { Object.keys(store).forEach((k) => delete store[k]); },
      key: (index: number) => Object.keys(store)[index] ?? null,
      get length() { return Object.keys(store).length; },
    },
    writable: true,
    configurable: true,
  });
}

vi.mock("@radix-ui/react-slot", () => {
  const Slot = ({ children }: any) => children ?? null;
  Slot.displayName = "Slot";
  return { Slot };
});
