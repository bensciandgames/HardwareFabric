"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";

type Status = "verifying" | "success" | "error";

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<Status>("verifying");
  const [message, setMessage] = useState<string>("Verifying your email…");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("This verification link is missing its token. Check the link in your email and try again.");
      return;
    }
    api
      .post<{ message: string }>("/api/v1/auth/verify-email", { token })
      .then((res) => {
        setStatus("success");
        setMessage(res.message);
      })
      .catch((err) => {
        setStatus("error");
        setMessage(
          err instanceof ApiError ? err.detail : "Something went wrong verifying your email. Try again shortly."
        );
      });
  }, [token]);

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-4 py-16 text-center">
      <h1 className="font-display text-2xl font-bold text-text-primary">
        {status === "verifying" && "Verifying…"}
        {status === "success" && "Email verified"}
        {status === "error" && "Verification failed"}
      </h1>
      <p className="font-body text-sm text-text-muted">{message}</p>
      {status === "success" && (
        <Link href="/login" className="mt-2 text-sm text-blue-medium hover:underline">
          Go to login
        </Link>
      )}
      {status === "error" && (
        <Link href="/login" className="mt-2 text-sm text-blue-medium hover:underline">
          Back to login — you can request a new link there
        </Link>
      )}
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="py-16 text-center font-body text-sm text-text-muted">Loading…</div>}>
      <VerifyEmailInner />
    </Suspense>
  );
}
