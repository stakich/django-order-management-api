export type Product = {
  id: number;
  name: string;
  description: string | null;
  price: string;
  stock: number;
  sku: string;
  category: number;
  category_name: string;
  image: string | null;
  image_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Category = {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};
