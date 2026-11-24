
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { useCart } from "../cart/useCart";

type HeaderProps =
  | { search: string; onSearchChange: (value: string) => void }
  | { search?: never; onSearchChange?: never };

export function Header({ search, onSearchChange }: HeaderProps) {
  const { user, isInitializing, signOut } = useAuth();
  const { count } = useCart();

  return (
    <>
      <header className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-5 py-4">
        <Link to="/" aria-label="MayBell home">
          <img
            className="h-9 w-auto max-w-32 object-contain"
            src="/assets/images/company-logo.svg"
            alt="MayBell"
          />
        </Link>

        {onSearchChange && (
          <label className="order-3 flex w-full items-center border border-neutral-200 md:order-none md:max-w-lg md:flex-1">
            <span className="sr-only">Search products</span>
            <input
              className="min-w-0 flex-1 px-4 py-2.5 outline-none"
              type="search"
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Search products..."
            />
            <span className="bg-amber-400 px-5 py-2.5 font-medium">
              Search
            </span>
          </label>
        )}

        <Link to="/cart" className="flex items-center gap-2 text-sm font-medium hover:text-violet-800">
          <svg
            aria-hidden="true"
            className="h-6 w-6"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 3h2l2.2 10.5a2 2 0 0 0 2 1.5h9.4a2 2 0 0 0 2-1.6L22 7H6"
            />
            <circle cx="10" cy="20" r="1" fill="currentColor" stroke="none" />
            <circle cx="19" cy="20" r="1" fill="currentColor" stroke="none" />
          </svg>
          <span>Cart ({count})</span>
        </Link>
      </header>

      <nav className="bg-violet-900 text-white" aria-label="Main navigation">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-7 gap-y-3 px-5 py-3 text-sm">
          <a
            href="/#products"
            className="bg-amber-400 px-4 py-2 font-medium text-neutral-900"
          >
            All categories
          </a>

          <Link to="/" className="hover:text-amber-300">
            Home
          </Link>

          <a href="/#products" className="hover:text-amber-300">
            Catalog
          </a>

          <div className="ml-auto flex items-center gap-5">
            {!isInitializing &&
              (user ? (
                <>
                  <Link to="/orders" className="hover:text-amber-300">
                    My orders
                  </Link>
                  <Link
                    to="/account"
                    className="hover:text-amber-300"
                  >
                    {user.username}
                  </Link>

                  <button
                    type="button"
                    onClick={signOut}
                    className="hover:text-amber-300"
                  >
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="hover:text-amber-300"
                  >
                    Login
                  </Link>

                  <Link
                    to="/register"
                    className="hover:text-amber-300"
                  >
                    Register
                  </Link>
                </>
              ))}
          </div>
        </div>
      </nav>
    </>
  );
}
