import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, clearTokens, saveTokens } from "../src/api/auth.ts";
import { createOrder } from "../src/api/orders.ts";

const cartItem = { id: 2, quantity: 3, price: "99.00" };

function mockSession(t) {
  const originalStorage = globalThis.sessionStorage;
  const originalWindow = globalThis.window;
  const storage = new Map();
  globalThis.sessionStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  globalThis.window = new EventTarget();
  t.after(() => {
    globalThis.sessionStorage = originalStorage;
    globalThis.window = originalWindow;
  });
  saveTokens({ access: "example-access", refresh: "example-refresh" });
  return storage;
}

test("order creation sends only product IDs and quantities", async (t) => {
  mockSession(t);
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({ id: 7 }));

  assert.deepEqual(await createOrder([cartItem]), { id: 7 });
  const [url, options] = fetch.mock.calls[0].arguments;
  assert.equal(url, "/api/v1/orders/");
  assert.equal(options.method, "POST");
  assert.equal(options.headers.get("Authorization"), "Bearer example-access");
  assert.deepEqual(JSON.parse(options.body), {
    items: [{ product: 2, quantity: 3 }],
  });
});

test("order creation surfaces the backend rejection", async (t) => {
  mockSession(t);
  const fetch = t.mock.method(globalThis, "fetch", async () => {
    return Response.json({ detail: "Insufficient stock" }, { status: 400 });
  });
  await assert.rejects(createOrder([cartItem]), {
    name: ApiError.name,
    message: "Insufficient stock",
    status: 400,
  });
  assert.equal(fetch.mock.callCount(), 1);
});

test("a session change aborts pending authenticated order requests", async (t) => {
  const storage = mockSession(t);
  const { promise, resolve } = Promise.withResolvers();
  const fetch = t.mock.method(globalThis, "fetch", () => promise);

  const order = createOrder([cartItem]);
  clearTokens();
  saveTokens({ access: "new-access", refresh: "new-refresh" });
  resolve(new Response(null, { status: 401 }));

  await assert.rejects(order, { name: "AbortError" });
  assert.equal(fetch.mock.callCount(), 1);
  assert.equal(storage.get("access_token"), "new-access");
});

test("concurrent requests share a token refresh within the same session", async (t) => {
  mockSession(t);
  const fetch = t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url === "/api/v1/auth/token/refresh/") {
      return Response.json({ access: "refreshed-access" });
    }
    if (options.headers.get("Authorization") === "Bearer refreshed-access") {
      return Response.json({ id: 7 });
    }
    return new Response(null, { status: 401 });
  });

  await Promise.all([createOrder([cartItem]), createOrder([cartItem])]);
  assert.equal(fetch.mock.calls.filter(({ arguments: [url] }) => url.endsWith("/refresh/")).length, 1);
});

test("an invalid refresh ends the session without retrying the order", async (t) => {
  const storage = mockSession(t);
  const fetch = t.mock.method(globalThis, "fetch", async () => {
    return Response.json({ detail: "Invalid token" }, { status: 401 });
  });

  await assert.rejects(createOrder([cartItem]), { status: 401 });
  assert.equal(fetch.mock.callCount(), 2);
  assert.equal(storage.has("access_token"), false);
  assert.equal(storage.has("refresh_token"), false);
});
