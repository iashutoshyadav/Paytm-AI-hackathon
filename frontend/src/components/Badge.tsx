import type { Badge as BadgeKind } from "@/lib/api";

const STYLE: Record<BadgeKind, { text: string; cls: string }> = {
  approve: { text: "Approve", cls: "bg-orange text-white" },
  urgent: { text: "Urgent", cls: "bg-red text-white" },
  human_only: { text: "Human only", cls: "bg-red text-white" },
  done: { text: "✓ Done", cls: "bg-green text-white" },
  silent: { text: "Stayed silent", cls: "bg-muted/15 text-muted" },
  waiting: { text: "Waiting", cls: "bg-cyan-soft text-navy" },
  dismissed: { text: "Dismissed", cls: "bg-muted/15 text-muted" },
};

export default function Badge({ kind }: { kind: BadgeKind }) {
  const s = STYLE[kind];
  return (
    <span className={`inline-block shrink-0 rounded-full px-3 py-1 text-xs font-bold whitespace-nowrap ${s.cls}`}>
      {s.text}
    </span>
  );
}
