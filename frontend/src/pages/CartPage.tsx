import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { formatPrice, priceToCents } from "../cart/cart";
import { useCart } from "../cart/useCart";
import { Header } from "../components/Header";

export default function CartPage() {
  const { user, isInitializing } = useAuth();
  const { items, totalCents, setQuantity, remove, placeOrder, isPlacingOrder } = useCart();
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function handleCreateOrder() {
    if (!user) {
      navigate("/login", { state: { from: "/cart" } });
      return;
    }

    setError("");
    try {
      const order = await placeOrder();
      if (order && /^\/cart\/?$/i.test(window.location.pathname)) {
        navigate(`/orders/${order.id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create order");
    }
  }

  return (
    <>
      <Header />
      <main className="mx-auto max-w-[1200px] px-5 py-12">
        <h1 className="mb-8 text-3xl font-bold">Shopping Cart</h1>
        {items.length === 0 ? (
          <div className="rounded border border-neutral-200 p-8">
            <p className="mb-5 text-neutral-600">Your cart is empty.</p>
            <Link className="text-violet-800 underline" to="/">Browse products</Link>
          </div>
        ) : (
          <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
            <div className="space-y-4">
              {items.map((item) => (
                <article
                  key={item.id}
                  className="flex flex-wrap items-center gap-4 border border-neutral-200 p-4"
                >
                  <img
                    src={item.imageUrl ?? "/assets/images/product-chair.png"}
                    alt=""
                    className="h-24 w-24 bg-violet-50 object-contain"
                  />
                  <div className="min-w-32 flex-1">
                    <h2 className="font-semibold">{item.name}</h2>
                    <p className="text-sm text-neutral-600">
                      {formatPrice(priceToCents(item.price))} each
                    </p>
                    <button
                      type="button"
                      className="mt-2 text-sm text-red-700 underline disabled:opacity-50"
                      disabled={isPlacingOrder}
                      onClick={() => remove(item.id)}
                    >
                      Remove
                    </button>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <button
                      type="button"
                      aria-label={`Decrease quantity of ${item.name}`}
                      disabled={isPlacingOrder || item.quantity <= 1}
                      onClick={() => setQuantity(item.id, item.quantity - 1)}
                      className="h-9 w-9 border border-neutral-300 disabled:opacity-50"
                    >
                      −
                    </button>
                    <output aria-label={`Quantity of ${item.name}`}>{item.quantity}</output>
                    <button
                      type="button"
                      aria-label={`Increase quantity of ${item.name}`}
                      disabled={isPlacingOrder || item.quantity >= item.stock}
                      onClick={() => setQuantity(item.id, item.quantity + 1)}
                      className="h-9 w-9 border border-neutral-300 disabled:opacity-50"
                    >
                      +
                    </button>
                  </div>
                  <strong className="min-w-24 text-right">
                    {formatPrice(priceToCents(item.price) * item.quantity)}
                  </strong>
                </article>
              ))}
            </div>
            <aside className="h-fit border border-neutral-200 p-6">
              <h2 className="mb-4 text-xl font-semibold">Order summary</h2>
              <div className="mb-5 flex justify-between">
                <span>Estimated total</span>
                <strong>{formatPrice(totalCents)}</strong>
              </div>
              {error && <p role="alert" className="mb-4 text-sm text-red-700">{error}</p>}
              <button
                type="button"
                disabled={isPlacingOrder || isInitializing}
                onClick={handleCreateOrder}
                className="w-full bg-violet-900 px-5 py-3 font-semibold text-white disabled:opacity-50"
              >
                {isPlacingOrder ? "Creating order..." : user ? "Place order" : "Sign in to order"}
              </button>
            </aside>
          </div>
        )}
      </main>
    </>
  );
}
