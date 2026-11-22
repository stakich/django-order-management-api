export type Product = {
  id: number;
  name: string;
  description: string | null;
  price: string; // Django DecimalField is serialized as a string.
  stock: number;
  sku: string;
  category: number; // Category foreign key ID, not a category name.
  is_active: boolean;
  created_at: string;
  updated_at: string;
};
