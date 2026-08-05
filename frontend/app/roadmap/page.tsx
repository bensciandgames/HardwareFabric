import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Roadmap — HardwareFabric",
  description: "What's live, what's in progress, and what's next for HardwareFabric.",
};

type Status = "shipped" | "in-progress" | "planned";

type RoadmapItem = {
  title: string;
  status: Status;
  description: string;
};

type Phase = {
  label: string;
  items: RoadmapItem[];
};

const STATUS_META: Record<Status, { label: string; className: string }> = {
  shipped: {
    label: "Live",
    className: "border-blue-medium text-blue-medium",
  },
  "in-progress": {
    label: "In Progress",
    className: "border-yellow-signal text-yellow-signal",
  },
  planned: {
    label: "Planned",
    className: "border-blue-dim text-text-muted",
  },
};

const PHASES: Phase[] = [
  {
    label: "Foundation",
    items: [
      {
        title: "Fabric Builder",
        status: "shipped",
        description:
          "Configure a build across Consumer Tower, Workstation Rig, or Rackmount Server Blade in one unified canvas.",
      },
      {
        title: "Accounts & Authentication",
        status: "in-progress",
        description:
          "Sign up, log in, and keep your builds tied to your own account.",
      },
    ],
  },
  {
    label: "Pricing & Procurement",
    items: [
      {
        title: "Live Component Pricing",
        status: "in-progress",
        description:
          "Real-time pricing and availability pulled from our supplier network as you build, not static list prices.",
      },
      {
        title: "Secure Checkout",
        status: "in-progress",
        description:
          "Pay for a full build in a single checkout, with pricing locked at the moment you check out.",
      },
      {
        title: "Automatic Order Fulfillment",
        status: "in-progress",
        description:
          "Once you check out, HardwareFabric places and tracks procurement on your behalf — no manual sourcing.",
      },
    ],
  },
  {
    label: "Build Management",
    items: [
      {
        title: "Saved Builds",
        status: "planned",
        description: "Save a configuration and come back to finish it later.",
      },
      {
        title: "Completed Builds & Order History",
        status: "planned",
        description: "A running history of everything you've built and ordered, with status and tracking.",
      },
      {
        title: "In-Builder Compatibility Guardrails",
        status: "planned",
        description:
          "Surface memory, lane, and slot compatibility warnings directly in the builder before you check out — not just after.",
      },
    ],
  },
  {
    label: "Scale & Launch",
    items: [
      {
        title: "Expanded Supplier Network",
        status: "planned",
        description: "Additional supplier integrations to widen catalog coverage and improve availability.",
      },
      {
        title: "Business & Operational Readiness",
        status: "planned",
        description:
          "Finalizing the legal, financial, and operational groundwork behind the scenes to support a full public launch.",
      },
      {
        title: "Public Launch",
        status: "planned",
        description: "HardwareFabric opens for general use.",
      },
    ],
  },
];

export default function RoadmapPage() {
  return (
    <div className="mx-auto max-w-3xl py-10">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-blue-medium">Roadmap</p>
      <h1 className="mt-2 font-display text-3xl font-bold tracking-tight text-text-primary sm:text-4xl">
        Building HardwareFabric in the open
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-relaxed text-text-muted">
        HardwareFabric is under active development. This page tracks where things stand —
        what&apos;s live today, what&apos;s actively being built, and what&apos;s coming next
        on the way to a full public launch.
      </p>

      <div className="mt-10 flex flex-wrap gap-4 font-mono text-[11px] uppercase tracking-wide text-text-muted">
        {(Object.keys(STATUS_META) as Status[]).map((key) => (
          <span key={key} className="flex items-center gap-2">
            <span className={`rounded-sm border px-2 py-0.5 ${STATUS_META[key].className}`}>
              {STATUS_META[key].label}
            </span>
          </span>
        ))}
      </div>

      <div className="mt-10 space-y-12">
        {PHASES.map((phase) => (
          <section key={phase.label}>
            <h2 className="font-display text-lg font-semibold tracking-tight text-text-primary">
              {phase.label}
            </h2>
            <div className="mt-4 space-y-3">
              {phase.items.map((item) => {
                const meta = STATUS_META[item.status];
                return (
                  <div
                    key={item.title}
                    className="rounded-md border border-blue-dim/60 bg-panel/60 p-4"
                  >
                    <div className="flex flex-wrap items-center gap-3">
                      <h3 className="font-display text-sm font-medium text-text-primary">
                        {item.title}
                      </h3>
                      <span
                        className={`rounded-sm border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide ${meta.className}`}
                      >
                        {meta.label}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-relaxed text-text-muted">
                      {item.description}
                    </p>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      <p className="mt-14 border-t border-blue-dim/40 pt-6 text-xs text-text-faint">
        This roadmap is a snapshot, not a commitment — order and timing may shift as we build.
      </p>
    </div>
  );
}
