import type { Product } from "../types/product";

export type CartItem = {
  id: number;
  name: string;
  price: string;
  stock: number;
  imageUrl: string | null;
  quantity: number;
};

export type CartAction =
  | { type: "add"; product: Product }
  | { type: "setQuantity"; id: number; quantity: number }
  | { type: "remove"; id: number }
  | { type: "clear" };

export const CART_STORAGE_KEY = "maybell-cart-v1";

// Prices in the UI are decimal strings; use integer cents for arithmetic.
export function priceToCents(value: string): number {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value);
  if (!match) return 0;
  return Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
}

export function formatPrice(cents: number): string {
  return (cents / 100).toLocaleString("en-IE", {
    style: "currency",
    currency: "EUR",
  });
}

export function cartCount(items: CartItem[]): number {
  return items.reduce((sum, item) => sum + item.quantity, 0);
}

export function cartTotalCents(items: CartItem[]): number {
  return items.reduce((sum, item) => sum + priceToCents(item.price) * item.quantity, 0);
}

export function cartReducer(items: CartItem[], action: CartAction): CartItem[] {
  switch (action.type) {
    case "add": {
      const product = action.product;
      if (!product.is_active || product.stock < 1) return items;
      const existing = items.find((item) => item.id === product.id);
      const updatedItem: CartItem = {
        id: product.id,
        name: product.name,
        price: product.price,
        stock: product.stock,
        imageUrl: product.image_url,
        quantity: Math.min((existing?.quantity ?? 0) + 1, product.stock),
      };

      return existing
        ? items.map((item) => item.id === product.id ? updatedItem : item)
        : [...items, updatedItem];
    }
    case "setQuantity":
      if (!Number.isSafeInteger(action.quantity)) return items;
      if (action.quantity < 1) {
        return items.filter((item) => item.id !== action.id);
      }
      return items.map((item) =>
        item.id === action.id
          ? { ...item, quantity: Math.min(action.quantity, item.stock) }
          : item
      );
    case "remove":
      return items.filter((item) => item.id !== action.id);
    case "clear":
      return [];
  }
}

export function readCart(): CartItem[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(CART_STORAGE_KEY) ?? "[]");
    if (!Array.isArray(value)) return [];

    const seen = new Set<number>();
    return value.filter((item): item is CartItem => {
      if (!item || typeof item !== "object") return false;
      const valid =
        Number.isSafeInteger(item.id) && item.id > 0 && !seen.has(item.id) &&
        typeof item.name === "string" &&
        typeof item.price === "string" && /^\d+(\.\d{1,2})?$/.test(item.price) &&
        Number.isSafeInteger(item.stock) && item.stock > 0 &&
        Number.isSafeInteger(item.quantity) && item.quantity >= 1 && item.quantity <= item.stock &&
        (item.imageUrl === null || typeof item.imageUrl === "string");
      if (valid) seen.add(item.id);
      return valid;
    });
  } catch {
    return [];
  }
}
