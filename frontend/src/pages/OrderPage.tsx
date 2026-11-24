import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { cancelOrder, getOrder, type Order } from "../api/orders";
import { formatPrice, priceToCents } from "../cart/cart";
import { Header } from "../components/Header";

function OrderDetails({ id }: { id: number }) {
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getOrder(id, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setOrder(data);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "Could not load order");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [id]);

  async function updateOrder(action: (orderId: number) => Promise<Order>) {
    if (working) return;

    setWorking(true);
    setError("");
    try {
      setOrder(await action(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update order");
    } finally {
      setWorking(false);
    }
  }

  if (loading) return <p role="status">Loading order...</p>;
  if (!order) return <p role="alert" className="text-red-700">{error}</p>;

  const total = order.items.reduce(
    (sum, item) => sum + priceToCents(item.unit_price) * item.quantity,
    0,
  );

  return (
    <div className="space-y-6">
      <div className="border p-5">
        <div className="flex flex-wrap justify-between gap-3">
          <p>Status: <strong>{order.status}</strong></p>
          <p>Total: <strong>{formatPrice(total)}</strong></p>
        </div>
        {order.status === "PENDING" && (
          <p className="mt-3 text-sm text-neutral-600">
            Reservation expires: {new Date(order.expires_at).toLocaleString()}
          </p>
        )}
      </div>
      <section className="border p-5">
        <h2 className="mb-3 text-lg font-semibold">Items</h2>
        <ul>
          {order.items.map((item) => (
            <li key={item.id} className="flex justify-between border-b py-3 text-sm">
              <span>Product #{item.product} × {item.quantity}</span>
              <span>{formatPrice(priceToCents(item.unit_price) * item.quantity)}</span>
            </li>
          ))}
        </ul>
      </section>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={working}
          onClick={() => updateOrder(getOrder)}
          className="border px-5 py-3 disabled:opacity-50"
        >
          Refresh status
        </button>
        {order.status === "PENDING" && (
          <button
            type="button"
            disabled={working}
            onClick={() => updateOrder(cancelOrder)}
            className="border border-red-300 px-5 py-3 text-red-700 disabled:opacity-50"
          >
            Cancel order
          </button>
        )}
      </div>
    </div>
  );
}

export default function OrderPage() {
  const { orderId = "" } = useParams();
  const id = Number(orderId);
  const validId = /^[1-9]\d*$/.test(orderId) && Number.isSafeInteger(id);

  return (
    <>
      <Header />
      <main className="mx-auto max-w-[900px] px-5 py-12">
        <Link to="/orders" className="text-sm text-violet-800 underline">My orders</Link>
        {validId ? (
          <>
            <h1 className="my-6 text-3xl font-bold">Order #{id}</h1>
            <OrderDetails key={id} id={id} />
          </>
        ) : (
          <h1 className="my-6 text-3xl font-bold">Invalid order ID</h1>
        )}
      </main>
    </>
  );
}
