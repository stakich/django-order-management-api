import type { Product } from "../types/product";

type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export async function getProducts(
  search: string,
  page: number,
  signal: AbortSignal,
): Promise<PaginatedResponse<Product>> {
  const params = new URLSearchParams({ page: String(page) });
  if (search.trim()) params.set("search", search.trim());

  const response = await fetch(`/api/v1/products/?${params}`, { signal });

  if (!response.ok) {
    throw new Error(`Failed to fetch products (HTTP ${response.status})`);
  }

  return (await response.json()) as PaginatedResponse<Product>;
}
