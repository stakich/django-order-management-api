import { useEffect, useState } from "react";
import { getCategories, getProducts } from "./api/products";
import { Header } from "./components/Header";
import { ProductCard } from "./components/ProductCard";
import type { Category, Product } from "./types/product";

export default function App() {
  const [products, setProducts] = useState<Product[]>([]);
  const [cartCount, setCartCount] = useState(0);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [categoriesError, setCategoriesError] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    getCategories(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setCategories(data.filter((category) => category.is_active));
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setCategoriesError(true);
      });

    return () => controller.abort();
  }, []);


useEffect(() => {
  const controller = new AbortController();

  const timeout = window.setTimeout(async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await getProducts(
        search,
        page,
        categoryId,
        controller.signal
      );

      if (controller.signal.aborted) return;

      setProducts(data.results);
      setTotal(data.count);
      setHasNextPage(data.next !== null);
    } catch (err) {
      if (controller.signal.aborted) return;

      setError(
        err instanceof Error ? err.message : "Could not load products"
      );
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, search ? 350 : 0);

  return () => {
    window.clearTimeout(timeout);
    controller.abort();
  };
}, [search, page, categoryId]);


  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(1);
  }

  return (
    <div id="home" className="min-h-screen bg-white text-neutral-900">
      <Header
        cartCount={cartCount}
        search={search}
        onSearchChange={handleSearchChange}
      />

      <main>
        <section className="relative isolate flex min-h-[380px] items-center overflow-hidden bg-violet-100">
          <img
            className="absolute inset-0 -z-20 h-full w-full object-cover"
            src="/assets/images/header-bg.jpeg"
            alt="Cozy living room"
          />
          <div className="absolute inset-0 -z-10 bg-neutral-950/45" />
          <div className="mx-auto w-full max-w-[1200px] px-5 py-16 text-white">
            <p className="mb-4 text-sm font-semibold uppercase tracking-[0.2em]">
              MayBell Furniture
            </p>
            <h1 className="max-w-xl text-4xl font-bold leading-tight sm:text-5xl">
              Best collection for home decoration
            </h1>
            <p className="mt-5 max-w-lg text-sm text-neutral-100 sm:text-base">
              Find furniture that makes every room feel like home.
            </p>
            <a
              href="#products"
              className="mt-7 inline-block bg-amber-400 px-7 py-3 font-semibold text-neutral-950 hover:bg-amber-300"
            >
              Shop now
            </a>
          </div>
        </section>

        <section id="products" className="mx-auto max-w-[1200px] px-5 py-14">
          <div className="mb-7 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-sm font-semibold uppercase tracking-widest text-violet-800">
                MayBell collection
              </p>
              <h2 className="mt-2 text-2xl font-bold uppercase sm:text-3xl">
                Top new arrivals
              </h2>
            </div>
            {!loading && !error && (
              <span className="text-sm text-neutral-500">{total} products</span>
            )}
          </div>

          <div className="mb-6 flex flex-wrap items-center gap-3">
            <label htmlFor="category-filter" className="text-sm font-medium">
              Category
            </label>
            <select
              id="category-filter"
              value={categoryId ?? ""}
              onChange={(event) => {
                setCategoryId(event.target.value ? Number(event.target.value) : null);
                setPage(1);
              }}
              className="min-w-52 border border-neutral-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">All categories</option>
              {categories.map((category) => (
                <option value={category.id} key={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
            {categoriesError && (
              <p role="alert" className="text-sm text-red-700">
                Could not load categories.
              </p>
            )}
          </div>

          {loading ? (
            <p role="status" className="p-8 text-neutral-500">Loading products...</p>
          ) : error ? (
            <p role="alert" className="rounded border border-red-200 p-8 text-red-700">
              {error}. Make sure Django is running at http://127.0.0.1:8000.
            </p>
          ) : products.length === 0 ? (
            <p className="rounded border border-neutral-200 p-8 text-neutral-500">
              No products found.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
                {products.map((product) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    onAdd={() => setCartCount((prev) => prev + 1)}
                  />
                ))}
              </div>
              <div className="mt-8 flex items-center justify-between">
                <button
                  type="button"
                  disabled={page === 1}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                  className="border border-neutral-200 px-5 py-2 disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="text-sm text-neutral-500">Page {page}</span>
                <button
                  type="button"
                  disabled={!hasNextPage}
                  onClick={() => setPage((value) => value + 1)}
                  className="border border-neutral-200 px-5 py-2 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </>
          )}
        </section>
      </main>

      <footer className="border-t border-neutral-200 px-5 py-7 text-center text-sm text-neutral-500">
        MayBell storefront demo · Tailwind E-commerce design by Bogdan Bulakh
      </footer>
    </div>
  );
}
