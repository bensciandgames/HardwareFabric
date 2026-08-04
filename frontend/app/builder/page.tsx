"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import WorkspaceModeToggle, { WorkspaceMode } from "@/components/WorkspaceModeToggle";
import ComponentRail, { Category } from "@/components/ComponentRail";
import BuildCanvas, { BuildSlot } from "@/components/BuildCanvas";
import PricingManifest from "@/components/PricingManifest";
import ComponentPickerModal from "@/components/ComponentPickerModal";
import { useAuth } from "@/contexts/AuthContext";
import { useCart } from "@/contexts/CartContext";
import { api, ApiError } from "@/lib/api";

// Socket layout per workspace scale — which categories are relevant and
// their display label. Populated parts come from the backend build, not
// hardcoded here.
const SLOT_LAYOUT: Record<WorkspaceMode, { category: Category; label: string }[]> = {
  consumer_tower: [
    { category: "cpu", label: "Processor" },
    { category: "motherboard", label: "Motherboard (ATX / mATX)" },
    { category: "memory", label: "Memory — UDIMM" },
    { category: "gpu", label: "Graphics Card" },
    { category: "storage_nvme", label: "NVMe SSD" },
    { category: "psu", label: "Power Supply" },
    { category: "case", label: "Case" },
    { category: "cooler", label: "CPU Cooler" },
  ],
  workstation_rig: [
    { category: "cpu", label: "Processor — HEDT" },
    { category: "motherboard", label: "Motherboard (E-ATX)" },
    { category: "memory", label: "Memory — RDIMM" },
    { category: "gpu", label: "GPU / Accelerator" },
    { category: "storage_nvme", label: "NVMe SSD (PCIe 5.0)" },
    { category: "psu", label: "Power Supply" },
    { category: "case", label: "Case" },
    { category: "cooler", label: "Cooling" },
    { category: "nic", label: "Network Interface" },
  ],
  rackmount_server: [
    { category: "cpu", label: "Server Processor" },
    { category: "motherboard", label: "Server Motherboard (SSI-EEB)" },
    { category: "memory", label: "Memory — RDIMM / LRDIMM" },
    { category: "gpu", label: "GPU / Accelerator" },
    { category: "storage_nvme", label: "NVMe SSD (PCIe 5.0, U.2)" },
    { category: "raid_hba", label: "RAID / HBA Controller" },
    { category: "riser_backplane", label: "Riser / Backplane" },
    { category: "psu", label: "Redundant Power Supply" },
    { category: "cooler", label: "Cooling" },
    { category: "nic", label: "Network Interface" },
  ],
};

type BuildComponentRow = {
  id: string;
  component_id: string;
  pcie_slot_id: string | null;
  quantity: number;
  sku: string;
  mpn: string;
  name: string;
  category: Category;
  msrp_cents: number;
  slot_label: string | null;
};

type BottleneckWarning = {
  component_name: string;
  vram_gb: number | null;
  slot_label: string;
  slot_capacity: number;
  device_ideal_lanes: number;
};

export default function FabricBuilderPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { addBuild } = useCart();

  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("consumer_tower");
  const [activeCategory, setActiveCategory] = useState<Category>("cpu");
  const [buildId, setBuildId] = useState<string | null>(null);
  const [buildComponents, setBuildComponents] = useState<BuildComponentRow[]>([]);
  const [pricedByCategory, setPricedByCategory] = useState<Record<string, { priceCents: number; distributor: string }>>({});
  const [warnings, setWarnings] = useState<BottleneckWarning[]>([]);
  const [pickerCategory, setPickerCategory] = useState<Category | null>(null);
  const [removingCategory, setRemovingCategory] = useState<Category | null>(null);
  const [isAddingToCart, setIsAddingToCart] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const slotLayout = SLOT_LAYOUT[workspaceMode];

  const refreshBuildComponents = useCallback(async (id: string) => {
    const [components, compat] = await Promise.all([
      api.get<BuildComponentRow[]>(`/api/v1/builds/${id}/components`),
      api.get<BottleneckWarning[]>(`/api/v1/builds/${id}/compatibility`),
    ]);
    setBuildComponents(components);
    setWarnings(compat);
  }, []);

  const startNewBuild = useCallback(
    async (mode: WorkspaceMode) => {
      if (!user) return;
      const build = await api.post<{ id: string }>("/api/v1/builds", { workspace_mode: mode, name: "Untitled Build" });
      setBuildId(build.id);
      setBuildComponents([]);
      setPricedByCategory({});
      setWarnings([]);
    },
    [user]
  );

  useEffect(() => {
    if (!authLoading && user && !buildId) {
      startNewBuild(workspaceMode);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user]);

  useEffect(() => {
    if (buildId) refreshBuildComponents(buildId);
  }, [buildId, refreshBuildComponents]);

  function handleWorkspaceChange(mode: WorkspaceMode) {
    setWorkspaceMode(mode);
    setActiveCategory(SLOT_LAYOUT[mode][0].category);
    if (user) startNewBuild(mode);
  }

  const motherboardComponentId = useMemo(
    () => buildComponents.find((c) => c.category === "motherboard")?.component_id ?? null,
    [buildComponents]
  );

  const occupiedSlotIds = useMemo(
    () => new Set(buildComponents.filter((c) => c.pcie_slot_id).map((c) => c.pcie_slot_id as string)),
    [buildComponents]
  );

  const slots: BuildSlot[] = useMemo(
    () =>
      slotLayout.map(({ category, label }) => {
        const match = buildComponents.find((c) => c.category === category);
        if (!match) return { category, label };
        const priced = pricedByCategory[match.id];
        return {
          category,
          label,
          part: {
            buildComponentId: match.id,
            name: match.name,
            mpn: match.mpn,
            priceCents: priced?.priceCents ?? match.msrp_cents,
            distributor: priced?.distributor,
          },
        };
      }),
    [slotLayout, buildComponents, pricedByCategory]
  );

  const filledCategories = useMemo(() => new Set(buildComponents.map((c) => c.category)), [buildComponents]);

  async function handleInsert(category: Category) {
    if (!buildId) {
      setNotice("Log in to start configuring a build.");
      return;
    }
    setPickerCategory(category);
  }

  async function handlePickerSelect(
    component: { id: string; sku: string; mpn: string; name: string; category: Category; msrp_cents: number },
    pcieSlotId: string | null,
    offer: { retail_price_cents: number; distributor: string } | undefined
  ) {
    if (!buildId) return;
    const added = await api.post<BuildComponentRow>(`/api/v1/builds/${buildId}/components`, {
      component_id: component.id,
      pcie_slot_id: pcieSlotId,
      quantity: 1,
    });
    if (offer) {
      setPricedByCategory((prev) => ({
        ...prev,
        [added.id]: { priceCents: offer.retail_price_cents, distributor: offer.distributor },
      }));
    }
    await refreshBuildComponents(buildId);
  }

  async function handleRemove(category: Category, buildComponentId: string) {
    if (!buildId) return;
    setRemovingCategory(category);
    try {
      await api.delete(`/api/v1/builds/${buildId}/components/${buildComponentId}`);
      await refreshBuildComponents(buildId);
    } finally {
      setRemovingCategory(null);
    }
  }

  async function handleAddToCart() {
    if (!buildId) return;
    setIsAddingToCart(true);
    setNotice(null);
    try {
      await addBuild(buildId);
      setNotice("Build added to cart.");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.detail : "Could not add this build to your cart.");
    } finally {
      setIsAddingToCart(false);
    }
  }

  const pickerCategoryLabel = pickerCategory ? slotLayout.find((s) => s.category === pickerCategory)?.label ?? pickerCategory : "";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="font-display text-2xl font-bold text-text-primary">Fabric Builder</h1>
        <p className="max-w-2xl font-body text-sm text-text-muted">
          Select a workspace scale to filter available components, then populate each socket. Every part is priced
          and sourced live from our distributor network the moment you add it.
        </p>
        <WorkspaceModeToggle value={workspaceMode} onChange={handleWorkspaceChange} />

        {!authLoading && !user && (
          <p className="rounded-sm border border-yellow-dim/60 bg-yellow-signal/5 px-4 py-3 font-body text-sm text-text-muted">
            <Link href="/login" className="text-yellow-signal hover:underline">
              Log in
            </Link>{" "}
            or{" "}
            <Link href="/register" className="text-yellow-signal hover:underline">
              create an account
            </Link>{" "}
            to start configuring and saving a build.
          </p>
        )}

        {notice && <p className="font-mono text-xs text-text-muted">{notice}</p>}

        {warnings.length > 0 && (
          <div className="flex flex-col gap-1 rounded-sm border border-yellow-dim/60 bg-yellow-signal/5 px-4 py-3">
            <p className="font-mono text-[11px] uppercase tracking-wide text-yellow-signal">Bottleneck warning</p>
            {warnings.map((w, i) => (
              <p key={i} className="font-body text-xs text-text-muted">
                {w.component_name} wants x{w.device_ideal_lanes} but slot {w.slot_label} only provides x
                {w.slot_capacity} — this may bottleneck a {w.vram_gb ?? "high-VRAM"}GB accelerator.
              </p>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4 lg:flex-row">
        <ComponentRail
          workspaceMode={workspaceMode}
          activeCategory={activeCategory}
          onSelectCategory={setActiveCategory}
          filledCategories={filledCategories}
        />
        <BuildCanvas
          slots={slots}
          onInsert={handleInsert}
          onRemove={handleRemove}
          removingCategory={removingCategory}
        />
        <PricingManifest
          slots={slots}
          onAddToCart={handleAddToCart}
          isAddingToCart={isAddingToCart}
          disabledReason={!user ? "Log in to add this build to your cart." : null}
        />
      </div>

      {pickerCategory && buildId && (
        <ComponentPickerModal
          category={pickerCategory}
          categoryLabel={pickerCategoryLabel}
          workspaceMode={workspaceMode}
          motherboardComponentId={motherboardComponentId}
          occupiedSlotIds={occupiedSlotIds}
          onClose={() => setPickerCategory(null)}
          onSelect={handlePickerSelect}
        />
      )}
    </div>
  );
}
