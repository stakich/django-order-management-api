import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getOrders } from "../api/orders";
import type { Order } from "../api/orders";
import { Header } from "../components/Header";

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getOrders(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setOrders(data);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "Could not load orders");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  return (
    <>
      <Header />
      <main className="mx-auto max-w-[1000px] px-5 py-12">
        <h1 className="mb-8 text-3xl font-bold">My orders</h1>
        {loading ? (
          <p role="status">Loading orders...</p>
        ) : error ? (
          <p role="alert" className="text-red-700">{error}</p>
        ) : orders.length === 0 ? (
          <p>
            You have no orders yet.{" "}
            <Link className="text-violet-800 underline" to="/">Browse products</Link>
          </p>
        ) : (
          <div className="space-y-3">
            {orders.map((order) => (
              <Link
                key={order.id}
                to={`/orders/${order.id}`}
                className="flex flex-wrap items-center justify-between gap-4 border p-5 hover:bg-neutral-50"
              >
                <div>
                  <p className="font-semibold">Order #{order.id}</p>
                  <p className="text-sm text-neutral-600">{new Date(order.created_at).toLocaleString()}</p>
                </div>
                <div className="text-right">
                  <p className="font-medium">{order.status}</p>
                  <p className="text-xs text-neutral-600">{order.items.length} product lines</p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
