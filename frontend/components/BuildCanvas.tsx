"use client";

import type { Category } from "./ComponentRail";

export type BuildSlot = {
  category: Category;
  label: string;
  part?: {
    buildComponentId: string;
    name: string;
    mpn: string;
    priceCents: number;
    distributor?: string;
  };
};

function formatUSD(cents: number) {
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export default function BuildCanvas({
  slots,
  onInsert,
  onRemove,
  removingCategory,
}: {
  slots: BuildSlot[];
  onInsert: (category: Category) => void;
  onRemove: (category: Category, buildComponentId: string) => void;
  removingCategory: Category | null;
}) {
  const anyPopulated = slots.some((s) => s.part);

  return (
    <div className="flex-1 rounded-md border border-blue-dim/60 bg-panel">
      <div className="flex items-center justify-between border-b border-blue-dim/50 px-5 py-3">
        <p className="font-mono text-[11px] uppercase tracking-wider text-text-faint">Build Canvas</p>
        <p className="font-mono text-[11px] text-text-faint">
          {slots.filter((s) => s.part).length}/{slots.length} sockets populated
        </p>
      </div>

      <div className="flex px-2 py-4 sm:px-4">
        {/* Bus column: one continuous vertical trace every row connects to. */}
        <div className="relative w-10 shrink-0 sm:w-14">
          <div
            aria-hidden="true"
            className={[
              "absolute left-1/2 top-0 h-full w-[2px] -translate-x-1/2",
              anyPopulated ? "bg-blue-medium shadow-[0_0_10px_1px_rgba(59,125,255,0.5)]" : "bg-blue-dim",
            ].join(" ")}
          />
        </div>

        {/* Slot list */}
        <div className="flex flex-1 flex-col gap-3">
          {slots.map((slot) => (
            <SlotRow
              key={slot.category}
              slot={slot}
              onInsert={() => onInsert(slot.category)}
              onRemove={slot.part ? () => onRemove(slot.category, slot.part!.buildComponentId) : undefined}
              isRemoving={removingCategory === slot.category}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function SlotRow({
  slot,
  onInsert,
  onRemove,
  isRemoving,
}: {
  slot: BuildSlot;
  onInsert: () => void;
  onRemove?: () => void;
  isRemoving: boolean;
}) {
  const isFilled = Boolean(slot.part);

  return (
    <div className="relative flex items-center">
      {/* Horizontal connector reaching back into the bus column. Rendered
          as an SVG line so it can reuse the .trace-line dash animation
          defined globally, rather than approximating dashes with borders. */}
      <svg
        aria-hidden="true"
        width="56"
        height="2"
        viewBox="0 0 56 2"
        className="absolute -left-14 top-1/2 hidden -translate-y-1/2 sm:block"
      >
        <line x1="0" y1="1" x2="56" y2="1" className={isFilled ? "trace-line" : "trace-line-idle"} />
      </svg>

      <div
        className={[
          "flex w-full items-center justify-between rounded-sm border px-4 py-3 transition-colors",
          isFilled
            ? "border-blue-medium/60 bg-blue-faint"
            : "border-dashed border-yellow-dim/70 bg-void/40 animate-dash-pulse",
        ].join(" ")}
      >
        {isFilled ? (
          <>
            <div className="min-w-0">
              <p className="truncate font-display text-sm font-medium text-text-primary">{slot.part!.name}</p>
              <p className="font-mono text-[11px] text-text-muted">
                MPN {slot.part!.mpn}
                {slot.part!.distributor ? ` · sourced via ${slot.part!.distributor}` : ""}
              </p>
            </div>
            <div className="ml-4 flex shrink-0 items-center gap-3">
              <p className="font-mono text-sm text-yellow-signal">{formatUSD(slot.part!.priceCents)}</p>
              <button
                type="button"
                onClick={onRemove}
                disabled={isRemoving}
                aria-label={`Remove ${slot.part!.name}`}
                className="rounded-sm border border-danger/40 px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-danger transition-colors hover:border-danger hover:bg-danger/10 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isRemoving ? "…" : "Remove"}
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="font-display text-sm text-text-muted">{slot.label} &mdash; empty socket</p>
            <button
              type="button"
              onClick={onInsert}
              className="shrink-0 rounded-sm border border-yellow-dim px-3 py-1 font-mono text-[11px] uppercase tracking-wide text-yellow-signal transition-colors hover:border-yellow-signal hover:bg-yellow-signal/10"
            >
              Insert component
            </button>
          </>
        )}
      </div>
    </div>
  );
}
