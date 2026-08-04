"use client";

import type { WorkspaceMode } from "./WorkspaceModeToggle";

export type Category =
  | "cpu" | "motherboard" | "memory" | "gpu" | "storage_nvme" | "storage_sata"
  | "psu" | "case" | "cooler" | "nic" | "raid_hba" | "riser_backplane";

const CATEGORY_LABELS: Record<Category, string> = {
  cpu: "CPU",
  motherboard: "Motherboard",
  memory: "Memory",
  gpu: "GPU / Accelerator",
  storage_nvme: "NVMe Storage",
  storage_sata: "SATA Storage",
  psu: "Power Supply",
  case: "Case / Chassis",
  cooler: "Cooling",
  nic: "Network Interface",
  raid_hba: "RAID / HBA Controller",
  riser_backplane: "Riser / Backplane",
};

// Which categories are relevant per workspace scale — this is the frontend
// mirror of the min_workspace_scope array on the components table.
const SCOPE_CATEGORIES: Record<WorkspaceMode, Category[]> = {
  consumer_tower: ["cpu", "motherboard", "memory", "gpu", "storage_nvme", "storage_sata", "psu", "case", "cooler"],
  workstation_rig: ["cpu", "motherboard", "memory", "gpu", "storage_nvme", "storage_sata", "psu", "case", "cooler", "nic"],
  rackmount_server: ["cpu", "motherboard", "memory", "gpu", "storage_nvme", "storage_sata", "psu", "cooler", "nic", "raid_hba", "riser_backplane"],
};

export default function ComponentRail({
  workspaceMode,
  activeCategory,
  onSelectCategory,
  filledCategories,
}: {
  workspaceMode: WorkspaceMode;
  activeCategory: Category;
  onSelectCategory: (c: Category) => void;
  filledCategories: Set<Category>;
}) {
  const categories = SCOPE_CATEGORIES[workspaceMode];

  return (
    <aside className="w-full shrink-0 rounded-md border border-blue-dim/60 bg-panel sm:w-60">
      <div className="border-b border-blue-dim/50 px-4 py-3">
        <p className="font-mono text-[11px] uppercase tracking-wider text-text-faint">Component Rail</p>
      </div>
      <ul className="flex flex-col py-2">
        {categories.map((cat) => {
          const isActive = cat === activeCategory;
          const isFilled = filledCategories.has(cat);
          return (
            <li key={cat}>
              <button
                type="button"
                onClick={() => onSelectCategory(cat)}
                className={[
                  "flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors",
                  isActive ? "bg-blue-faint text-text-primary" : "text-text-muted hover:bg-panel-raised hover:text-text-primary",
                ].join(" ")}
              >
                {/* Pin header dot — solid yellow if the slot is filled,
                    hollow if still open, echoing the socket states on canvas. */}
                <span
                  aria-hidden="true"
                  className={[
                    "h-2 w-2 shrink-0 rounded-full border",
                    isFilled ? "border-yellow-signal bg-yellow-signal" : "border-text-faint bg-transparent",
                  ].join(" ")}
                />
                <span className="font-display text-sm">{CATEGORY_LABELS[cat]}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
