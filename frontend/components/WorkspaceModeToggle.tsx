"use client";

export type WorkspaceMode = "consumer_tower" | "workstation_rig" | "rackmount_server";

const MODES: { id: WorkspaceMode; label: string; caption: string }[] = [
  { id: "consumer_tower", label: "Consumer Tower", caption: "ATX / mATX · UDIMM" },
  { id: "workstation_rig", label: "Workstation Rig", caption: "HEDT / E-ATX · RDIMM" },
  { id: "rackmount_server", label: "Rackmount Server Blade", caption: "SSI-EEB / 1U–4U · RDIMM · LRDIMM" },
];

export default function WorkspaceModeToggle({
  value,
  onChange,
}: {
  value: WorkspaceMode;
  onChange: (mode: WorkspaceMode) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Workspace scale"
      className="flex flex-col gap-2 rounded-md border border-blue-dim/60 bg-panel p-2 sm:flex-row"
    >
      {MODES.map((mode) => {
        const isActive = value === mode.id;
        return (
          <button
            key={mode.id}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => onChange(mode.id)}
            className={[
              "group relative flex flex-1 items-center gap-3 rounded-sm px-4 py-3 text-left transition-colors",
              isActive ? "bg-blue-faint" : "hover:bg-panel-raised",
            ].join(" ")}
          >
            {/* LED indicator */}
            <span
              aria-hidden="true"
              className={[
                "h-2.5 w-2.5 shrink-0 rounded-full transition-all",
                isActive
                  ? "bg-yellow-signal shadow-[0_0_10px_3px_rgba(255,214,10,0.55)] animate-glow-breathe"
                  : "bg-text-faint",
              ].join(" ")}
            />
            <span className="flex flex-col">
              <span
                className={[
                  "font-display text-sm font-medium",
                  isActive ? "text-text-primary" : "text-text-muted group-hover:text-text-primary",
                ].join(" ")}
              >
                {mode.label}
              </span>
              <span className="font-mono text-[11px] text-text-faint">{mode.caption}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
