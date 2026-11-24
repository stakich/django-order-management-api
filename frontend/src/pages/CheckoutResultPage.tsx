import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getOrder, parseOrderId, type Order } from "../api/orders";
import { Header } from "../components/Header";

function CheckoutStatus({ orderId }: { orderId: number }) {
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [requestNumber, setRequestNumber] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getOrder(orderId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setOrder(data);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "Could not load payment status");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [orderId, requestNumber]);

  function refresh() {
    setLoading(true);
    setError("");
    setRequestNumber((number) => number + 1);
  }

  return (
    <div className="space-y-4 border border-neutral-200 p-6">
      {loading && <p role="status">Checking payment status...</p>}
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {!loading && !error && order && (
        <>
          <p>Order #{order.id} · <strong>{order.status}</strong></p>
          {order.status === "PENDING" && (
            <p className="text-sm text-neutral-600">
              Payment has yet to be confirmed. Use Refresh status to check again.
            </p>
          )}
        </>
      )}
      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="border px-4 py-2 disabled:opacity-50"
        >
          Refresh status
        </button>
        {order && (
          <Link to={`/orders/${order.id}`} className="text-violet-800 underline">
            View order
          </Link>
        )}
      </div>
    </div>
  );
}

export default function CheckoutResultPage({ outcome }: { outcome: "success" | "cancel" }) {
  const [params] = useSearchParams();
  const orderId = parseOrderId(params.get("order_id"));

  return (
    <>
      <Header />
      <main className="mx-auto max-w-[800px] space-y-6 px-5 py-12">
        <h1 className="text-3xl font-bold">
          {outcome === "success" ? "Payment status" : "Checkout cancelled"}
        </h1>
        {orderId === null ? (
          <p>Open your order history to check the payment status.</p>
        ) : (
          <CheckoutStatus key={orderId} orderId={orderId} />
        )}
        <Link to="/orders" className="inline-block text-violet-800 underline">
          View order history
        </Link>
      </main>
    </>
  );
}
