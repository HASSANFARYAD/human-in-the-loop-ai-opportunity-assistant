import type { ReactNode } from "react";

function labelize(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatDisplayValue(value: unknown): ReactNode {
  if (value == null || value === "") return <span className="text-muted-foreground">None</span>;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number" || typeof value === "string") return String(value);
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-muted-foreground">None</span>;
    const allScalar = value.every((item) => item == null || typeof item !== "object");
    if (allScalar) return value.map((item) => String(item)).join(", ");
    return (
      <ul className="grid gap-2">
        {value.map((item, index) => <li key={index}>{formatDisplayValue(item)}</li>)}
      </ul>
    );
  }
  if (typeof value === "object") return Object.entries(value as Record<string, unknown>).length ? <DataFields data={value as Record<string, unknown>} /> : <span className="text-muted-foreground">None</span>;
  return String(value);
}

export function EmptyState({ children = "No data available" }: { children?: ReactNode }) {
  return <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">{children}</div>;
}

export function DataFields({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, value]) => value !== undefined);
  if (!entries.length) return <EmptyState />;
  return (
    <dl className="grid gap-3 text-sm">
      {entries.map(([key, value]) => (
        <div key={key} className="grid gap-1 rounded-md border p-3 md:grid-cols-[180px_1fr]">
          <dt className="font-medium text-muted-foreground">{labelize(key)}</dt>
          <dd className="break-words">{formatDisplayValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function DataTable({ rows, columns }: { rows: Record<string, unknown>[]; columns: string[] }) {
  if (!rows.length) return <EmptyState />;
  return (
    <div className="overflow-hidden rounded-lg border">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-muted/60 text-left text-xs uppercase text-muted-foreground">
          <tr>{columns.map((column) => <th key={column} className="p-3">{labelize(column)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={String(row.id ?? index)} className="border-t transition-colors hover:bg-muted/30">
              {columns.map((column) => <td key={column} className="max-w-[320px] break-words p-3 align-top">{formatDisplayValue(row[column])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
