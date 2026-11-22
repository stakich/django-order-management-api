# MayBell React starter patch

An incremental React + TypeScript implementation inspired by the MIT-licensed
[MayBell Tailwind E-commerce template](https://github.com/bbulakh/tailwind-ecommerce).

This ZIP is a **patch** for an existing Vite `react-ts` project, not a full replacement project.
It overwrites `src/App.tsx` and `src/index.css` when extracted.

1. From the Django project root: `unzip -o ~/Downloads/maybell-react-starter.zip -d frontend`
2. `cd frontend`
3. `npm install`
4. `npm install -D tailwindcss@3 postcss autoprefixer`
5. `bash scripts/setup-template-assets.sh`
6. `npm run dev`
7. `npm run build`

If prior `tailwind.config.js` or `postcss.config.js` exist alongside the new `.cjs`
versions, remove **only the redundant generated .js configs**, after reviewing their
contents, so Vite uses one unambiguous configuration.

What's implemented:
- Header + responsive navigation with MayBell branding and working local search
- Hero and 4 product cards using original MayBell artwork
- Cart counter in React state; out-of-stock button disabled
- Product data typed with TypeScript, currently local temporary data

Not yet implemented:
- Django API calls, router, account pages, persistent cart, Stripe checkout

The original template's MIT license is copied to TEMPLATE_LICENSE by the asset script.
