type HeaderProps = {
  cartCount: number;
  search: string;
  onSearchChange: (value: string) => void;
};

export function Header({ cartCount, search, onSearchChange }: HeaderProps) {
  return (
    <>
      <header className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-5 py-4">
        <a href="#home" aria-label="MayBell home">
          <img
            className="h-9 w-auto max-w-32 object-contain"
            src="/assets/images/company-logo.svg"
            alt="MayBell"
          />
        </a>

        <label className="order-3 flex w-full max-w-lg items-center border border-neutral-200 md:order-none md:flex-1">
          <span className="sr-only">Search products</span>
          <input
            className="min-w-0 flex-1 px-4 py-2.5 outline-none"
            type="search"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search products..."
          />
          <span className="bg-amber-400 px-5 py-2.5 font-medium">Search</span>
        </label>

        <div className="flex items-center gap-2 text-sm font-medium">
          <svg aria-hidden="true" className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 3h2l2.2 10.5a2 2 0 0 0 2 1.5h9.4a2 2 0 0 0 2-1.6L22 7H6" />
            <circle cx="10" cy="20" r="1" fill="currentColor" stroke="none" />
            <circle cx="19" cy="20" r="1" fill="currentColor" stroke="none" />
          </svg>
          <span>Cart ({cartCount})</span>
        </div>
      </header>

      <nav className="bg-violet-900 text-white" aria-label="Main navigation">
        <div className="mx-auto flex max-w-[1200px] items-center gap-8 px-5 py-3 text-sm">
          <a className="bg-amber-400 px-4 py-2 font-medium text-neutral-900" href="#products">All categories</a>
          <a className="hover:text-amber-300" href="#home">Home</a>
          <a className="hover:text-amber-300" href="#products">Catalog</a>
        </div>
      </nav>
    </>
  );
}
