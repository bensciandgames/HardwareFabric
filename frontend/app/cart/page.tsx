"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { loadStripe } from "@stripe/stripe-js";
import { Elements } from "@stripe/react-stripe-js";
import { useAuth } from "@/contexts/AuthContext";
import { useCart } from "@/contexts/CartContext";
import { api, ApiError } from "@/lib/api";
import CheckoutForm from "@/components/CheckoutForm";

const stripePromise = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
  ? loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY)
  : null;

function formatUSD(cents: number) {
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

type ShippingForm = {
  name: string;
  line1: string;
  line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  phone: string;
};

const EMPTY_SHIPPING: ShippingForm = {
  name: "",
  line1: "",
  line2: "",
  city: "",
  state: "",
  postal_code: "",
  country: "US",
  phone: "",
};

export default function CartPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { items, updateQuantity, removeItem, refresh } = useCart();
  const router = useRouter();

  const [shipping, setShipping] = useState<ShippingForm>(EMPTY_SHIPPING);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [isCreatingIntent, setIsCreatingIntent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const subtotalCents = useMemo(
    () => items.reduce((sum, i) => sum + i.msrp_cents * i.quantity, 0),
    [items]
  );

  async function handleProceedToPayment(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsCreatingIntent(true);
    try {
      const res = await api.post<{ client_secret: string }>("/api/v1/checkout/create-payment-intent", {
        shipping_address: {
          name: shipping.name,
          line1: shipping.line1,
          line2: shipping.line2 || null,
          city: shipping.city,
          state: shipping.state,
          postal_code: shipping.postal_code,
          country: shipping.country,
          phone: shipping.phone || null,
        },
      });
      setClientSecret(res.client_secret);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not start checkout. Please try again.");
    } finally {
      setIsCreatingIntent(false);
    }
  }

  async function handlePaymentSuccess() {
    await refresh();
    router.push("/checkout/success");
  }

  if (!authLoading && !user) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <p className="font-body text-sm text-text-muted">Log in to view your cart.</p>
      </div>
    );
  }

  if (items.length === 0 && !clientSecret) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <p className="font-body text-sm text-text-muted">
          Your cart is empty. Head to the Fabric Builder to configure a build.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      <div className="flex-1 rounded-md border border-blue-dim/60 bg-panel">
        <div className="border-b border-blue-dim/50 px-5 py-3">
          <p className="font-mono text-[11px] uppercase tracking-wider text-text-faint">Cart</p>
        </div>
        <ul className="flex flex-col divide-y divide-blue-dim/30">
          {items.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-4 px-5 py-4">
              <div className="min-w-0">
                <p className="truncate font-display text-sm text-text-primary">{item.name}</p>
                <p className="font-mono text-[11px] text-text-muted">MPN {item.mpn}</p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <input
                  type="number"
                  min={1}
                  value={item.quantity}
                  onChange={(e) => updateQuantity(item.id, Math.max(1, Number(e.target.value)))}
                  className="w-14 rounded-sm border border-blue-dim bg-void px-2 py-1 text-center font-mono text-xs text-text-primary"
                />
                <p className="w-20 text-right font-mono text-sm text-yellow-signal">
                  {formatUSD(item.msrp_cents * item.quantity)}
                </p>
                <button
                  type="button"
                  onClick={() => removeItem(item.id)}
                  className="rounded-sm border border-danger/40 px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-danger transition-colors hover:border-danger hover:bg-danger/10"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
        <div className="flex items-center justify-between border-t border-blue-dim/50 px-5 py-4">
          <span className="font-display text-sm text-text-muted">Subtotal (est.)</span>
          <span className="font-mono text-lg font-medium text-yellow-signal">{formatUSD(subtotalCents)}</span>
        </div>
        <p className="px-5 pb-4 font-mono text-[10px] text-text-faint">
          Final pricing is locked at checkout via live distributor lookup.
        </p>
      </div>

      <div className="w-full shrink-0 rounded-md border border-blue-dim/60 bg-panel lg:w-96">
        <div className="border-b border-blue-dim/50 px-5 py-3">
          <p className="font-mono text-[11px] uppercase tracking-wider text-text-faint">Checkout</p>
        </div>

        <div className="px-5 py-4">
          {!clientSecret ? (
            <form onSubmit={handleProceedToPayment} className="flex flex-col gap-3">
              <ShippingField label="Full name" value={shipping.name} onChange={(v) => setShipping({ ...shipping, name: v })} required />
              <ShippingField label="Address line 1" value={shipping.line1} onChange={(v) => setShipping({ ...shipping, line1: v })} required />
              <ShippingField label="Address line 2" value={shipping.line2} onChange={(v) => setShipping({ ...shipping, line2: v })} />
              <div className="grid grid-cols-2 gap-3">
                <ShippingField label="City" value={shipping.city} onChange={(v) => setShipping({ ...shipping, city: v })} required />
                <ShippingField label="State" value={shipping.state} onChange={(v) => setShipping({ ...shipping, state: v })} required />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <ShippingField label="ZIP" value={shipping.postal_code} onChange={(v) => setShipping({ ...shipping, postal_code: v })} required />
                <ShippingField label="Phone" value={shipping.phone} onChange={(v) => setShipping({ ...shipping, phone: v })} />
              </div>

              {error && <p className="font-body text-sm text-danger">{error}</p>}

              <button
                type="submit"
                disabled={isCreatingIntent || items.length === 0}
                className="mt-2 w-full rounded-sm bg-yellow-signal py-2.5 font-display text-sm font-semibold text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isCreatingIntent ? "Preparing…" : "Continue to payment"}
              </button>
            </form>
          ) : stripePromise ? (
            <Elements stripe={stripePromise} options={{ clientSecret }}>
              <CheckoutForm onSuccess={handlePaymentSuccess} />
            </Elements>
          ) : (
            <p className="font-body text-sm text-danger">
              Stripe publishable key is not configured (NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY).
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ShippingField({
  label,
  value,
  onChange,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-wide text-text-faint">{label}</span>
      <input
        type="text"
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-sm border border-blue-dim bg-void px-2 py-1.5 font-body text-sm text-text-primary outline-none focus:border-blue-medium"
      />
    </label>
  );
}
