"use client";

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { useCart } from "@/contexts/CartContext";

type Tab = {
  label: string;
  href: string;
};

const TABS: Tab[] = [
  { label: "Fabric Builder", href: "/builder" },
  { label: "Saved Builds", href: "/saved" },
  { label: "Completed Builds", href: "/completed" },
];

export default function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isLoading } = useAuth();
  const { count } = useCart();

  function handleLogout() {
    logout();
    router.push("/builder");
  }

  return (
    <header className="sticky top-0 z-50 border-b border-blue-dim/60 bg-void/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] items-center gap-10 px-6">
        {/* Wordmark — a small node-and-trace glyph standing in for a logo,
            echoes the canvas signature element at a smaller scale. */}
        <Link href="/builder" className="flex items-center gap-2.5 py-4 font-display text-lg font-bold tracking-tight text-text-primary">
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
            <circle cx="4" cy="4" r="2.5" className="fill-yellow-signal" />
            <circle cx="18" cy="4" r="2.5" className="fill-blue-medium" />
            <circle cx="11" cy="18" r="2.5" className="fill-blue-medium" />
            <path d="M6 4H16M6 4 11 18M16 4 11 18" stroke="#3B7DFF" strokeWidth="1.4" />
          </svg>
          HardwareFabric
        </Link>

        <nav className="flex flex-1 items-stretch gap-1" aria-label="Primary">
          {TABS.map((tab) => {
            const isActive = pathname?.startsWith(tab.href);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={isActive ? "page" : undefined}
                className={[
                  "relative flex items-center gap-2 px-4 py-4 font-display text-sm font-medium tracking-wide transition-colors",
                  isActive ? "text-text-primary" : "text-text-muted hover:text-text-primary",
                ].join(" ")}
              >
                {tab.label}
                {/* Active-tab trace: a glowing underline that reads as a
                    soldered connector pad being energized. */}
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-3 -bottom-px h-[2px] bg-blue-medium shadow-[0_0_8px_2px_rgba(59,125,255,0.65)]"
                  />
                )}
              </Link>
            );
          })}

          <Link
            href="/cart"
            aria-current={pathname?.startsWith("/cart") ? "page" : undefined}
            className={[
              "relative flex items-center gap-2 px-4 py-4 font-display text-sm font-medium tracking-wide transition-colors",
              pathname?.startsWith("/cart") ? "text-text-primary" : "text-text-muted hover:text-text-primary",
            ].join(" ")}
          >
            Cart
            {count > 0 && (
              <span className="rounded-sm bg-yellow-signal px-1.5 py-0.5 font-mono text-[11px] font-medium leading-none text-void">
                {count}
              </span>
            )}
            {pathname?.startsWith("/cart") && (
              <span
                aria-hidden="true"
                className="absolute inset-x-3 -bottom-px h-[2px] bg-blue-medium shadow-[0_0_8px_2px_rgba(59,125,255,0.65)]"
              />
            )}
          </Link>
        </nav>

        <div className="flex items-center gap-3 py-4">
          {isLoading ? null : user ? (
            <>
              <span className="font-mono text-xs text-text-muted">{user.email}</span>
              <button
                type="button"
                onClick={handleLogout}
                className="rounded-sm border border-blue-dim px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide text-text-muted transition-colors hover:border-blue-medium hover:text-text-primary"
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-sm border border-blue-dim px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide text-text-muted transition-colors hover:border-blue-medium hover:text-text-primary"
              >
                Log in
              </Link>
              <Link
                href="/register"
                className="rounded-sm border border-yellow-dim px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide text-yellow-signal transition-colors hover:border-yellow-signal hover:bg-yellow-signal/10"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
