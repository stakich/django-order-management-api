import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CART_STORAGE_KEY,
  cartReducer,
  cartTotalCents,
  cartCount,
  priceToCents,
  readCart,
} from "../src/cart/cart.ts";

const product = {
  id: 1, name: "Chair", price: "129.95", stock: 2, image_url: null,
  is_active: true,
};

test("adds products and clamps quantity to known stock", () => {
  const one = cartReducer([], { type: "add", product });
  const two = cartReducer(one, { type: "add", product });
  const three = cartReducer(two, { type: "add", product });
  assert.equal(three.length, 1);
  assert.equal(three[0].quantity, 2);
  assert.equal(cartCount(three), 2);
});

test("rejects unavailable products", () => {
  assert.deepEqual(cartReducer([], { type: "add", product: { ...product, stock: 0 } }), []);
  assert.deepEqual(cartReducer([], { type: "add", product: { ...product, is_active: false } }), []);
});

test("removes items on zero quantity and on remove", () => {
  const items = cartReducer([], { type: "add", product });
  assert.deepEqual(cartReducer(items, { type: "setQuantity", id: 1, quantity: 0 }), []);
  assert.deepEqual(cartReducer(items, { type: "remove", id: 1 }), []);
});

test("calculates exact cents for two decimal amounts", () => {
  const items = [{ id: 1, name: "Chair", price: "12.99", quantity: 3, stock: 4, imageUrl: null }];
  assert.equal(priceToCents("12.99"), 1299);
  assert.equal(priceToCents("12.9"), 1290);
  assert.equal(cartTotalCents(items), 3897);
});

test("refreshes product snapshots when a product is added again", () => {
  const items = cartReducer([], { type: "add", product });
  const [item] = cartReducer(items, {
    type: "add",
    product: { ...product, name: "Dining chair", price: "110.00", stock: 1 },
  });
  assert.equal(item.name, "Dining chair");
  assert.equal(item.price, "110.00");
  assert.equal(item.quantity, 1);
});

test("restores valid stored items and skips corrupt or duplicate entries", (t) => {
  const originalStorage = globalThis.localStorage;
  t.after(() => { globalThis.localStorage = originalStorage; });
  const items = cartReducer([], { type: "add", product });
  globalThis.localStorage = {
    getItem(key) {
      assert.equal(key, CART_STORAGE_KEY);
      return JSON.stringify([...items, items[0], { ...items[0], id: 2, quantity: 4 }]);
    },
  };
  assert.deepEqual(readCart(), items);
  globalThis.localStorage = { getItem: () => "{" };
  assert.deepEqual(readCart(), []);
});
