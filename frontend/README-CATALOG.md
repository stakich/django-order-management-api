# MayBell — Django Catalog API patch

This patch targets the prior MayBell React starter. Apply it from the Django project root.
It replaces `frontend/src/App.tsx`, `frontend/src/components/ProductCard.tsx`,
`frontend/src/types/product.ts`, and `frontend/vite.config.ts` and adds
`frontend/src/api/products.ts`.

## Apply

```bash
unzip -o ~/Downloads/maybell-catalog-api-patch.zip -d frontend
cd frontend
npm run build
npm run dev
```

Run Django separately on http://127.0.0.1:8000, e.g. `python manage.py runserver`
from the Django project root and your Python venv.

Test the endpoint directly: http://127.0.0.1:8000/api/v1/products/

## What changed

- `vite.config.ts` proxies `/api/...` to Django in development.
- `src/api/products.ts` fetches DRF's paginated JSON (`results`, `count`, `next`).
- `src/types/product.ts` matches the Django ProductSerializer: `price` is a decimal string, `category` is the category ID, and no image field exists yet.
- `src/App.tsx` handles loading, error, server-side search (350ms debounce), and pagination.
- `src/components/ProductCard.tsx` uses a clearly marked demo image pending support for real product images. The cart is still a counter, not a fully implemented cart.

If Django has no products, the page correctly displays `No products found.`
For production hosting, the Vite development proxy must be replaced by an appropriate reverse proxy or CORS configuration.
