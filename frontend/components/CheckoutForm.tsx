"use client";

import { FormEvent, useState } from "react";
import { PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";

// Shipping address is collected on the cart page (matching the backend's
// ShippingAddress model) and sent when creating the PaymentIntent, so it's
// already attached server-side — this form only needs to collect payment
// details via Stripe's PaymentElement.

export default function CheckoutForm({ onSuccess }: { onSuccess: () => void }) {
  const stripe = useStripe();
  const elements = useElements();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!stripe || !elements) return;

    setIsSubmitting(true);
    setError(null);

    const { error: submitError } = await elements.submit();
    if (submitError) {
      setError(submitError.message ?? "Please check your payment details.");
      setIsSubmitting(false);
      return;
    }

    const { error: confirmError, paymentIntent } = await stripe.confirmPayment({
      elements,
      redirect: "if_required",
    });

    if (confirmError) {
      setError(confirmError.message ?? "Payment failed. Please try again.");
      setIsSubmitting(false);
      return;
    }

    if (paymentIntent && paymentIntent.status === "succeeded") {
      onSuccess();
    } else {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <div>
        <p className="mb-2 font-mono text-[11px] uppercase tracking-wide text-text-faint">Payment</p>
        <PaymentElement />
      </div>

      {error && <p className="font-body text-sm text-danger">{error}</p>}

      <button
        type="submit"
        disabled={!stripe || isSubmitting}
        className="w-full rounded-sm bg-yellow-signal py-2.5 font-display text-sm font-semibold text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
      >
        {isSubmitting ? "Processing…" : "Place order"}
      </button>
      <p className="text-center font-mono text-[10px] text-text-faint">
        Ships blind dropship &middot; no distributor branding
      </p>
    </form>
  );
}
