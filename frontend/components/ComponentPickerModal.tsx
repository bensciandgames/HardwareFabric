"use client";

import { useEffect, useMemo, useState } from "react";
import type { Category } from "./ComponentRail";
import type { WorkspaceMode } from "./WorkspaceModeToggle";
import { api, ApiError } from "@/lib/api";

// Categories whose parts occupy a physical PCIe slot on the motherboard —
// mirrors which satellite tables have a pcie_devices row in the schema.
const PCIE_CATEGORIES: Category[] = ["gpu", "storage_nvme", "nic", "raid_hba"];

type ComponentSummary = {
  id: string;
  sku: string;
  mpn: string;
  category: Category;
  name: string;
  msrp_cents: number;
  specs: Record<string, unknown>;
};

type PricedOffer = {
  mpn: string;
  sku: string;
  name: string;
  category: Category;
  distributor: string;
  retail_price_cents: number;
  quantity_available: number;
  lead_time_days: number | null;
  in_stock: boolean;
};

type PcieSlot = {
  id: string;
  slot_label: string;
  physical_form: string;
  max_electrical_lanes: number;
  pcie_version: number;
  bifurcation_capable: boolean;
};

function formatUSD(cents: number) {
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export default function ComponentPickerModal({
  category,
  categoryLabel,
  workspaceMode,
  motherboardComponentId,
  occupiedSlotIds,
  onClose,
  onSelect,
}: {
  category: Category;
  categoryLabel: string;
  workspaceMode: WorkspaceMode;
  motherboardComponentId: string | null;
  occupiedSlotIds: Set<string>;
  onClose: () => void;
  onSelect: (component: ComponentSummary, pcieSlotId: string | null, offer: PricedOffer | undefined) => Promise<void>;
}) {
  const [components, setComponents] = useState<ComponentSummary[]>([]);
  const [offersByMpn, setOffersByMpn] = useState<Record<string, PricedOffer>>({});
  const [slots, setSlots] = useState<PcieSlot[]>([]);
  const [selectedSlotId, setSelectedSlotId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submittingId, setSubmittingId] = useState<string | null>(null);

  const needsSlot = PCIE_CATEGORIES.includes(category);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const list = await api.get<ComponentSummary[]>(
          `/api/v1/components?category=${category}&workspace_mode=${workspaceMode}`
        );
        if (cancelled) return;
        setComponents(list);

        if (list.length > 0) {
          const priced = await api.post<{ best_offers: PricedOffer[] }>("/api/v1/pricing/lookup", {
            mpns: list.map((c) => c.mpn),
          });
          if (cancelled) return;
          const byMpn: Record<string, PricedOffer> = {};
          for (const o of priced.best_offers) byMpn[o.mpn] = o;
          setOffersByMpn(byMpn);
        }

        if (needsSlot && motherboardComponentId) {
          const slotList = await api.get<PcieSlot[]>(
            `/api/v1/components/${motherboardComponentId}/pcie-slots`
          );
          if (cancelled) return;
          const availableSlots = slotList.filter((s) => !occupiedSlotIds.has(s.id));
          setSlots(availableSlots);
          setSelectedSlotId(availableSlots[0]?.id ?? "");
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.detail : "Failed to load components");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, workspaceMode, motherboardComponentId]);

  const sorted = useMemo(
    () =>
      [...components].sort((a, b) => {
        const pa = offersByMpn[a.mpn]?.retail_price_cents ?? a.msrp_cents;
        const pb = offersByMpn[b.mpn]?.retail_price_cents ?? b.msrp_cents;
        return pa - pb;
      }),
    [components, offersByMpn]
  );

  async function handleSelect(component: ComponentSummary) {
    setError(null);
    setSubmittingId(component.id);
    try {
      await onSelect(component, needsSlot ? selectedSlotId || null : null, offersByMpn[component.mpn]);
      onClose();
    } catch (err) {
      // Surfaces the Postgres trigger's own rejection message (memory type
      // mismatch, PCIe lane oversubscription) verbatim — this is the
      // "compatibility surfaced in the UI" backlog item.
      setError(err instanceof ApiError ? err.detail : "Could not add this component to the build.");
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-void/80 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-md border border-blue-dim/60 bg-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-blue-dim/50 px-5 py-3">
          <p className="font-display text-sm font-medium text-text-primary">Insert &mdash; {categoryLabel}</p>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-sm px-2 py-1 font-mono text-text-muted hover:text-text-primary"
          >
            ✕
          </button>
        </div>

        {needsSlot && (
          <div className="flex items-center gap-3 border-b border-blue-dim/50 px-5 py-3">
            <label className="font-mono text-[11px] uppercase tracking-wide text-text-faint" htmlFor="slot-select">
              PCIe slot
            </label>
            {slots.length === 0 ? (
              <p className="font-mono text-[11px] text-text-faint">
                {motherboardComponentId
                  ? "No open slots detected — select a motherboard first, or this will add unassigned."
                  : "Select a motherboard first to assign a physical slot."}
              </p>
            ) : (
              <select
                id="slot-select"
                value={selectedSlotId}
                onChange={(e) => setSelectedSlotId(e.target.value)}
                className="rounded-sm border border-blue-dim bg-void px-2 py-1 font-mono text-xs text-text-primary"
              >
                {slots.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.slot_label} &middot; x{s.max_electrical_lanes} &middot; PCIe {s.pcie_version}
                    {s.bifurcation_capable ? " (bifurcation)" : ""}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading && <p className="font-body text-sm text-text-muted">Loading live pricing…</p>}
          {!isLoading && sorted.length === 0 && (
            <p className="font-body text-sm text-text-muted">No parts found for this category yet.</p>
          )}

          <ul className="flex flex-col gap-2">
            {sorted.map((c) => {
              const offer = offersByMpn[c.mpn];
              const priceCents = offer?.retail_price_cents ?? c.msrp_cents;
              const inStock = offer ? offer.in_stock : true;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    disabled={!inStock || submittingId === c.id}
                    onClick={() => handleSelect(c)}
                    className="flex w-full items-center justify-between rounded-sm border border-blue-dim/60 bg-void/40 px-4 py-3 text-left transition-colors hover:border-blue-medium disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-display text-sm text-text-primary">{c.name}</p>
                      <p className="font-mono text-[11px] text-text-muted">
                        MPN {c.mpn}
                        {offer ? ` · via ${offer.distributor}` : ""}
                        {!inStock ? " · out of stock" : ""}
                      </p>
                    </div>
                    <p className="ml-4 shrink-0 font-mono text-sm text-yellow-signal">
                      {submittingId === c.id ? "Adding…" : formatUSD(priceCents)}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        {error && (
          <div className="border-t border-danger/40 bg-danger/10 px-5 py-3">
            <p className="font-mono text-xs text-danger">{error}</p>
          </div>
        )}
      </div>
    </div>
  );
}
