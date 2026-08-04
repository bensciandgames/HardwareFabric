"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError } from "@/lib/api";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await register(email, password, fullName || undefined);
      router.push("/builder");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 py-16">
      <div>
        <h1 className="font-display text-2xl font-bold text-text-primary">Create an account</h1>
        <p className="mt-1 font-body text-sm text-text-muted">Save builds and check out instantly.</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[11px] uppercase tracking-wide text-text-faint">Full name (optional)</span>
          <input
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="rounded-sm border border-blue-dim bg-void px-3 py-2 font-body text-sm text-text-primary outline-none focus:border-blue-medium"
          />
        </label>
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
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-sm border border-blue-dim bg-void px-3 py-2 font-body text-sm text-text-primary outline-none focus:border-blue-medium"
          />
          <span className="font-mono text-[10px] text-text-faint">At least 8 characters.</span>
        </label>

        {error && <p className="font-body text-sm text-danger">{error}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="mt-2 rounded-sm bg-yellow-signal py-2.5 font-display text-sm font-semibold text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isSubmitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="font-body text-sm text-text-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-blue-medium hover:underline">
          Log in
        </Link>
      </p>
    </div>
  );
}
