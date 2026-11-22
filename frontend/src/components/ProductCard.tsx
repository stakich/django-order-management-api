import type { Product } from "../types/product";

type ProductCardProps = {
  product: Product;
  onAdd: () => void;
};

export function ProductCard({ product, onAdd }: ProductCardProps) {
  const hasImage = Boolean(product.image_url);

  return (
    <article className="group overflow-hidden border border-neutral-100 bg-white">
      <div className="relative flex aspect-square items-center justify-center bg-violet-50 p-5">
        <img
          className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-105"
          src={product.image_url ?? "/assets/images/product-chair.png"}
          alt={hasImage ? product.name : "Generic furniture illustration"}
          loading="lazy"
        />
        {!hasImage && (
          <span className="absolute bottom-2 left-2 bg-white/90 px-2 py-1 text-xs text-neutral-600">
            Demo image
          </span>
        )}
      </div>
      <div className="space-y-2 p-4">
        <p className="text-xs uppercase tracking-wider text-neutral-500">
          {product.category_name}
        </p>
        <h3 className="font-semibold uppercase tracking-wide">{product.name}</h3>
        <p className="text-lg font-semibold">
          {Number(product.price).toLocaleString("en-IE", {
            style: "currency",
            currency: "EUR",
          })}
        </p>
        <button
          type="button"
          onClick={onAdd}
          disabled={product.stock === 0}
          className="w-full bg-amber-400 px-4 py-3 text-sm font-semibold text-neutral-900 transition-colors hover:bg-amber-300 disabled:cursor-not-allowed disabled:bg-neutral-200 disabled:text-neutral-500"
        >
          {product.stock === 0 ? "Out of stock" : "Add to cart"}
        </button>
      </div>
    </article>
  );
}
