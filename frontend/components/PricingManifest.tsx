"use client";

import type { BuildSlot } from "./BuildCanvas";

function formatUSD(cents: number) {
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export default function PricingManifest({
  slots,
  onAddToCart,
  isAddingToCart,
  disabledReason,
}: {
  slots: BuildSlot[];
  onAddToCart: () => void;
  isAddingToCart: boolean;
  disabledReason?: string | null;
}) {
  const filled = slots.filter((s) => s.part);
  const subtotalCents = filled.reduce((sum, s) => sum + (s.part?.priceCents ?? 0), 0);
  const distributors = Array.from(new Set(filled.map((s) => s.part!.distributor).filter(Boolean))) as string[];

  const isDisabled = filled.length === 0 || isAddingToCart || Boolean(disabledReason);

  return (
    <aside className="w-full shrink-0 self-start rounded-md border border-blue-dim/60 bg-panel lg:w-80">
      <div className="border-b border-blue-dim/50 px-5 py-3">
        <p className="font-mono text-[11px] uppercase tracking-wider text-text-faint">Sourcing Manifest</p>
      </div>

      <div className="flex flex-col gap-4 px-5 py-4">
        {filled.length === 0 ? (
          <p className="font-body text-sm text-text-muted">
            No components sourced yet. Populate a socket to see live pricing and distributor routing here.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {filled.map((s) => (
              <li key={s.category} className="flex items-center justify-between font-mono text-xs">
                <span className="truncate text-text-muted">{s.part!.name}</span>
                <span className="ml-3 shrink-0 text-text-primary">{formatUSD(s.part!.priceCents)}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="border-t border-blue-dim/50 pt-4">
          <div className="flex items-center justify-between">
            <span className="font-display text-sm text-text-muted">Subtotal</span>
            <span className="font-mono text-lg font-medium text-yellow-signal">{formatUSD(subtotalCents)}</span>
          </div>
        </div>

        {distributors.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {distributors.map((d) => (
              <span
                key={d}
                className="rounded-sm border border-blue-dim bg-void px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-blue-medium"
              >
                {d}
              </span>
            ))}
          </div>
        )}

        <button
          type="button"
          disabled={isDisabled}
          onClick={onAddToCart}
          className="w-full rounded-sm bg-yellow-signal py-2.5 font-display text-sm font-semibold text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-30"
        >
          {isAddingToCart ? "Adding…" : "Add build to cart"}
        </button>
        {disabledReason && <p className="text-center font-mono text-[10px] text-text-faint">{disabledReason}</p>}
        <p className="text-center font-mono text-[10px] text-text-faint">
          Ships blind dropship &middot; no distributor branding
        </p>
      </div>
    </aside>
  );
}
