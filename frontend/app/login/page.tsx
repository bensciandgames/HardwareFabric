"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login, resendVerification } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resendStatus, setResendStatus] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNeedsVerification(false);
    setResendStatus(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      router.push("/builder");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setNeedsVerification(true);
      }
      setError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleResend() {
    setResendStatus(null);
    try {
      const res = await resendVerification(email);
      setResendStatus(res.message);
    } catch (err) {
      setResendStatus(err instanceof ApiError ? err.detail : "Couldn't resend right now — try again shortly.");
    }
  }

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 py-16">
      <div>
        <h1 className="font-display text-2xl font-bold text-text-primary">Log in</h1>
        <p className="mt-1 font-body text-sm text-text-muted">Access your saved builds and cart.</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[11px] uppercase tracking-wide text-text-faint">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-sm border border-blue-dim bg-void px-3 py-2 font-body text-sm text-text-primary outline-none focus:border-blue-medium"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[11px] uppercase tracking-wide text-text-faint">Password</span>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-sm border border-blue-dim bg-void px-3 py-2 font-body text-sm text-text-primary outline-none focus:border-blue-medium"
          />
        </label>

        {error && <p className="font-body text-sm text-danger">{error}</p>}
        {needsVerification && (
          <button
            type="button"
            onClick={handleResend}
            className="self-start text-sm text-blue-medium hover:underline"
          >
            Resend verification email
          </button>
        )}
        {resendStatus && <p className="font-body text-sm text-text-muted">{resendStatus}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="mt-2 rounded-sm bg-yellow-signal py-2.5 font-display text-sm font-semibold text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isSubmitting ? "Logging in…" : "Log in"}
        </button>
      </form>

      <p className="font-body text-sm text-text-muted">
        Don&apos;t have an account?{" "}
        <Link href="/register" className="text-blue-medium hover:underline">
          Sign up
        </Link>
      </p>
    </div>
  );
}
