import { useEffect, useReducer, useRef, useState, type ReactNode } from "react";
import { createOrder } from "../api/orders";
import type { Product } from "../types/product";
import {
  type CartAction,
  CART_STORAGE_KEY,
  cartCount,
  cartReducer,
  cartTotalCents,
  readCart,
} from "./cart";
import { CartContext } from "./CartContext";

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, dispatch] = useReducer(cartReducer, undefined, readCart);
  const [isPlacingOrder, setIsPlacingOrder] = useState(false);
  const placingOrder = useRef(false);

  useEffect(() => {
    try {
      localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(items));
    } catch {
      // Keep the cart usable when browser storage is unavailable.
    }
  }, [items]);

  function update(action: CartAction) {
    if (!placingOrder.current) dispatch(action);
  }

  function add(product: Product) {
    update({ type: "add", product });
  }

  function setQuantity(id: number, quantity: number) {
    update({ type: "setQuantity", id, quantity });
  }

  function remove(id: number) {
    update({ type: "remove", id });
  }

  async function placeOrder() {
    if (placingOrder.current || items.length === 0) return null;

    placingOrder.current = true;
    setIsPlacingOrder(true);
    try {
      const order = await createOrder(items);
      dispatch({ type: "clear" });
      return order;
    } finally {
      placingOrder.current = false;
      setIsPlacingOrder(false);
    }
  }

  return (
    <CartContext.Provider
      value={{
        items,
        count: cartCount(items),
        totalCents: cartTotalCents(items),
        isPlacingOrder,
        add,
        setQuantity,
        remove,
        placeOrder,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}
