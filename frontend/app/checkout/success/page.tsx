"use client";

import Link from "next/link";

export default function CheckoutSuccessPage() {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center gap-4 py-24 text-center">
      <div className="h-3 w-3 rounded-full bg-yellow-signal shadow-[0_0_10px_3px_rgba(255,214,10,0.55)]" />
      <h1 className="font-display text-2xl font-bold text-text-primary">Order placed</h1>
      <p className="font-body text-sm text-text-muted">
        Payment confirmed. We&apos;re routing your build to our distributor network now for blind dropship
        fulfillment — you&apos;ll see it under Completed Builds once sourcing is submitted.
      </p>
      <Link
        href="/completed"
        className="mt-2 rounded-sm bg-yellow-signal px-4 py-2.5 font-display text-sm font-semibold text-void"
      >
        View Completed Builds
      </Link>
    </div>
  );
}
