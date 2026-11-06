import { VoltageType } from "./chat";

export interface Product {
  sku: string;
  name: string;
  brand: string;
  category: string;
  subcategory: string;
  price: number;
  stock_quantity: number;
  voltage: VoltageType;
  capacity_liters?: number | null;
  power_watts?: number | null;
  image_url: string;
  description: string;
  features?: string[];
  rating?: number;
  reviews_count?: number;
}
