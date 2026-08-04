"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useCart } from "@/contexts/CartContext";
import { api, ApiError } from "@/lib/api";

type Build = {
  id: string;
  name: string;
  workspace_mode: string;
  status: string;
  created_at: string;
  updated_at: string;
};

const WORKSPACE_LABELS: Record<string, string> = {
  consumer_tower: "Consumer Tower",
  workstation_rig: "Workstation Rig",
  rackmount_server: "Rackmount Server Blade",
};

export default function SavedBuildsPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { addBuild } = useCart();
  const [builds, setBuilds] = useState<Build[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      setIsLoading(false);
      return;
    }
    api
      .get<Build[]>("/api/v1/builds")
      .then((data) => setBuilds(data.filter((b) => b.status !== "ordered")))
      .finally(() => setIsLoading(false));
  }, [user]);

  async function handleDelete(id: string) {
    await api.delete(`/api/v1/builds/${id}`);
    setBuilds((prev) => prev.filter((b) => b.id !== id));
  }

  async function handleAddToCart(id: string) {
    setNotice(null);
    try {
      await addBuild(id);
      setNotice("Added to cart.");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.detail : "Could not add this build to your cart.");
    }
  }

  if (!authLoading && !user) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <p className="font-body text-sm text-text-muted">Log in to view your saved builds.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold text-text-primary">Saved Builds</h1>
      {notice && <p className="font-mono text-xs text-text-muted">{notice}</p>}

      {isLoading ? (
        <p className="font-body text-sm text-text-muted">Loading…</p>
      ) : builds.length === 0 ? (
        <p className="font-body text-sm text-text-muted">
          No saved builds yet. Configure something in the Fabric Builder — every build you start is saved
          automatically.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {builds.map((b) => (
            <li
              key={b.id}
              className="flex items-center justify-between rounded-md border border-blue-dim/60 bg-panel px-5 py-4"
            >
              <div>
                <p className="font-display text-sm font-medium text-text-primary">{b.name}</p>
                <p className="font-mono text-[11px] text-text-muted">
                  {WORKSPACE_LABELS[b.workspace_mode] ?? b.workspace_mode} &middot; {b.status} &middot; updated{" "}
                  {new Date(b.updated_at).toLocaleDateString()}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleAddToCart(b.id)}
                  className="rounded-sm border border-yellow-dim px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide text-yellow-signal transition-colors hover:border-yellow-signal hover:bg-yellow-signal/10"
                >
                  Add to cart
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(b.id)}
                  className="rounded-sm border border-danger/40 px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide text-danger transition-colors hover:border-danger hover:bg-danger/10"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
