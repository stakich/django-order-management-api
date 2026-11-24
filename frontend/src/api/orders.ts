import { request } from "./auth.ts";
import type { CartItem } from "../cart/cart";

export type OrderItem = {
  id: number;
  product: number;
  quantity: number;
  unit_price: string;
};

export type Order = {
  id: number;
  user: number;
  status: "PENDING" | "PAID" | "CANCELLED";
  created_at: string;
  updated_at: string;
  expires_at: string;
  items: OrderItem[];
};

const ORDERS_URL = "/api/v1/orders/";

export function parseOrderId(value: string | null): number | null {
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 && String(id) === value ? id : null;
}

export function createOrder(
  items: ReadonlyArray<Pick<CartItem, "id" | "quantity">>,
): Promise<Order> {
  return request<Order>(ORDERS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      items: items.map(({ id, quantity }) => ({ product: id, quantity })),
    }),
  }, true);
}

export function getOrders(signal?: AbortSignal): Promise<Order[]> {
  return request<Order[]>(ORDERS_URL, { signal }, true);
}

export function getOrder(id: number, signal?: AbortSignal): Promise<Order> {
  return request<Order>(`${ORDERS_URL}${id}/`, { signal }, true);
}

export function cancelOrder(id: number): Promise<Order> {
  return request<Order>(`${ORDERS_URL}${id}/cancel/`, { method: "POST" }, true);
}

export async function startCheckout(id: number, signal?: AbortSignal): Promise<string> {
  const data = await request<{ checkout_url: string }>(
    `${ORDERS_URL}${id}/checkout/`,
    { method: "POST", signal },
    true,
  );
  const value = data?.checkout_url;
  let url: URL | null;
  try {
    url = typeof value === "string" ? new URL(value) : null;
  } catch {
    throw new Error("Invalid Stripe Checkout URL");
  }
  if (url?.origin !== "https://checkout.stripe.com" || url.username || url.password) {
    throw new Error("Invalid Stripe Checkout URL");
  }
  return url.href;
}
