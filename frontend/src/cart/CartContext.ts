import { createContext } from "react";
import type { Order } from "../api/orders";
import type { Product } from "../types/product";
import type { CartItem } from "./cart";

export type CartContextValue = {
  items: CartItem[];
  count: number;
  totalCents: number;
  isPlacingOrder: boolean;
  add: (product: Product) => void;
  setQuantity: (id: number, quantity: number) => void;
  remove: (id: number) => void;
  placeOrder: () => Promise<Order | null>;
};

export const CartContext = createContext<CartContextValue | null>(null);
