"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export type CartItem = {
  id: string;
  build_id: string | null;
  component_id: string;
  quantity: number;
  preferred_distributor: string | null;
  sku: string;
  mpn: string;
  name: string;
  category: string;
  msrp_cents: number;
};

type CartContextValue = {
  items: CartItem[];
  count: number;
  isLoading: boolean;
  refresh: () => Promise<void>;
  addComponent: (componentId: string, quantity?: number, buildId?: string) => Promise<void>;
  addBuild: (buildId: string) => Promise<void>;
  updateQuantity: (cartItemId: string, quantity: number) => Promise<void>;
  removeItem: (cartItemId: string) => Promise<void>;
};

const CartContext = createContext<CartContextValue | undefined>(undefined);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [items, setItems] = useState<CartItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!user) {
      setItems([]);
      return;
    }
    setIsLoading(true);
    try {
      const data = await api.get<CartItem[]>("/api/v1/cart");
      setItems(data);
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addComponent = useCallback(
    async (componentId: string, quantity = 1, buildId?: string) => {
      await api.post("/api/v1/cart/items", { component_id: componentId, quantity, build_id: buildId ?? null });
      await refresh();
    },
    [refresh]
  );

  const addBuild = useCallback(
    async (buildId: string) => {
      await api.post("/api/v1/cart/add-build", { build_id: buildId });
      await refresh();
    },
    [refresh]
  );

  const updateQuantity = useCallback(
    async (cartItemId: string, quantity: number) => {
      await api.patch(`/api/v1/cart/items/${cartItemId}`, { quantity });
      await refresh();
    },
    [refresh]
  );

  const removeItem = useCallback(
    async (cartItemId: string) => {
      await api.delete(`/api/v1/cart/items/${cartItemId}`);
      await refresh();
    },
    [refresh]
  );

  const count = useMemo(() => items.reduce((sum, i) => sum + i.quantity, 0), [items]);

  const value = useMemo(
    () => ({ items, count, isLoading, refresh, addComponent, addBuild, updateQuantity, removeItem }),
    [items, count, isLoading, refresh, addComponent, addBuild, updateQuantity, removeItem]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within a CartProvider");
  return ctx;
}
