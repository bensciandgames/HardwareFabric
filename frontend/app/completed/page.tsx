"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";

type OrderSummary = {
  id: string;
  build_id: string | null;
  status: string;
  subtotal_cents: number;
  total_cents: number;
  created_at: string;
};

type OrderItem = {
  id: string;
  mpn: string;
  name: string;
  distributor_code: string;
  quantity: number;
  unit_price_cents: number;
};

type DistributorOrder = {
  id: string;
  distributor_code: string;
  distributor_order_number: string | null;
  status: string;
  tracking_number: string | null;
};

type OrderDetail = OrderSummary & { items: OrderItem[]; distributor_orders: DistributorOrder[] };

const STATUS_LABELS: Record<string, string> = {
  pending_payment: "Pending payment",
  paid: "Paid",
  sourcing: "Sourcing",
  dropship_submitted: "Submitted to distributors",
  partially_shipped: "Partially shipped",
  shipped: "Shipped",
  cancelled: "Cancelled",
  failed: "Failed",
};

function formatUSD(cents: number) {
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export default function CompletedBuildsPage() {
  const { user, isLoading: authLoading } = useAuth();
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [expanded, setExpanded] = useState<Record<string, OrderDetail>>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user) {
      setIsLoading(false);
      return;
    }
    api
      .get<OrderSummary[]>("/api/v1/orders")
      .then(setOrders)
      .finally(() => setIsLoading(false));
  }, [user]);

  async function toggleExpand(id: string) {
    if (expanded[id]) {
      setExpanded((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      return;
    }
    const detail = await api.get<OrderDetail>(`/api/v1/orders/${id}`);
    setExpanded((prev) => ({ ...prev, [id]: detail }));
  }

  if (!authLoading && !user) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <p className="font-body text-sm text-text-muted">Log in to view your completed builds.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold text-text-primary">Completed Builds</h1>

      {isLoading ? (
        <p className="font-body text-sm text-text-muted">Loading…</p>
      ) : orders.length === 0 ? (
        <p className="font-body text-sm text-text-muted">
          No orders yet. Once you check out, your order and its dropship status will show up here.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {orders.map((o) => {
            const detail = expanded[o.id];
            return (
              <li key={o.id} className="rounded-md border border-blue-dim/60 bg-panel">
                <button
                  type="button"
                  onClick={() => toggleExpand(o.id)}
                  className="flex w-full items-center justify-between px-5 py-4 text-left"
                >
                  <div>
                    <p className="font-display text-sm font-medium text-text-primary">
                      Order {o.id.slice(0, 8)}
                    </p>
                    <p className="font-mono text-[11px] text-text-muted">
                      {STATUS_LABELS[o.status] ?? o.status} &middot; {new Date(o.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <p className="font-mono text-sm text-yellow-signal">{formatUSD(o.total_cents)}</p>
                </button>

                {detail && (
                  <div className="border-t border-blue-dim/50 px-5 py-4">
                    <ul className="flex flex-col gap-2">
                      {detail.items.map((item) => (
                        <li key={item.id} className="flex items-center justify-between font-mono text-xs">
                          <span className="text-text-muted">
                            {item.name} &times;{item.quantity} ({item.distributor_code})
                          </span>
                          <span className="text-text-primary">{formatUSD(item.unit_price_cents * item.quantity)}</span>
                        </li>
                      ))}
                    </ul>
                    {detail.distributor_orders.length > 0 && (
                      <div className="mt-3 flex flex-col gap-1 border-t border-blue-dim/30 pt-3">
                        <p className="font-mono text-[11px] uppercase tracking-wide text-text-faint">
                          Distributor sourcing
                        </p>
                        {detail.distributor_orders.map((d) => (
                          <p key={d.id} className="font-mono text-[11px] text-text-muted">
                            {d.distributor_code}: {d.status}
                            {d.distributor_order_number ? ` (PO ${d.distributor_order_number})` : ""}
                            {d.tracking_number ? ` — tracking ${d.tracking_number}` : ""}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
