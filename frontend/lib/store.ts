/**
 * The online plant store (/store). The catalogue, prices and stock live in the API
 * (app.services.store) and are edited from the office's Store products page; the cart lives
 * in the visitor's browser until they place the order.
 */

export interface Plant {
  id: string;
  slug: string;
  name: string;
  botanical_name: string | null;
  category: string;
  summary: string;
  description: string;
  care: { light?: string; water?: string; size?: string; pot?: string; care_level?: string; pet_safe?: boolean };
  price: number;
  mrp: number | null;
  /** null: stock is not tracked. */
  stock: number | null;
  image: string;
  active: boolean;
  sort_order: number;
}

export interface StoreConfig {
  delivery_fee: number;
  free_delivery_over: number;
  cod: boolean;
  cod_limit: number;
  /** "live" with Razorpay keys, "demo" for a test payment, null when online payment is off. */
  online: "live" | "demo" | null;
  pincode_prefixes: string[];
  max_quantity: number;
  categories: Record<string, string>;
}

export interface OrderItem {
  slug: string;
  name: string;
  unit_price: number;
  quantity: number;
  line_total: number;
}

export interface StoreOrder {
  id: string;
  created_at: string;
  number: string;
  bill_number: string;
  status: "pending_payment" | "placed" | "confirmed" | "out_for_delivery" | "delivered" | "cancelled";
  payment_method: "cod" | "online";
  payment_status: "unpaid" | "paid" | "refunded";
  customer_name: string;
  phone: string;
  email: string | null;
  address: string;
  area: string;
  pincode: string;
  landmark: string | null;
  notes: string | null;
  subtotal: number;
  delivery_fee: number;
  total: number;
  provider_payment_id: string | null;
  paid_at: string | null;
  delivered_at: string | null;
  cancelled_reason: string | null;
  admin_note?: string | null;
  items: OrderItem[];
}

export const CATEGORIES: Record<string, string> = {
  indoor: "Indoor plants",
  outdoor: "Outdoor plants",
  flowering: "Flowering plants",
  herbs: "Herbs & kitchen garden",
  succulents: "Succulents & cacti",
};

export const ORDER_STATUS: Record<StoreOrder["status"], string> = {
  pending_payment: "Waiting for payment",
  placed: "Order placed",
  confirmed: "Confirmed",
  out_for_delivery: "Out for delivery",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

export const rupees = (n: number) => `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

// ------------------------------------------------------------------ catalogue (server side)

const API = (process.env.GREENPLOT_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** Read the public catalogue from the API on the server. Returns null when the API cannot be reached. */
async function storeGet<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${API}/api/v1/public/store${path}`, { next: { revalidate: 60 } });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export const getPlants = () => storeGet<Plant[]>("/products");
export const getPlant = (slug: string) => storeGet<Plant>(`/products/${encodeURIComponent(slug)}`);
export const getStoreConfig = () => storeGet<StoreConfig>("/config");

// ------------------------------------------------------------------ cart (browser)

export interface CartLine {
  slug: string;
  name: string;
  price: number;
  image: string;
  quantity: number;
}

const CART_KEY = "gp.cart";
const ORDERS_KEY = "gp.orders";
const CART_EVENT = "gp-cart";

function store(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readCart(): CartLine[] {
  try {
    const v = JSON.parse(store()?.getItem(CART_KEY) || "[]");
    return Array.isArray(v) ? v.filter((l) => l && typeof l.slug === "string" && l.quantity > 0) : [];
  } catch {
    return [];
  }
}

export function writeCart(lines: CartLine[]) {
  try {
    store()?.setItem(CART_KEY, JSON.stringify(lines.filter((l) => l.quantity > 0)));
  } catch {
    // private mode: the cart lasts only for this page view
  }
  window.dispatchEvent(new Event(CART_EVENT));
}

export function onCartChange(fn: () => void) {
  const storage = (e: StorageEvent) => e.key === CART_KEY && fn();
  window.addEventListener(CART_EVENT, fn);
  window.addEventListener("storage", storage);
  return () => {
    window.removeEventListener(CART_EVENT, fn);
    window.removeEventListener("storage", storage);
  };
}

export function addToCart(p: Pick<Plant, "slug" | "name" | "price" | "image">, quantity: number, max = 20) {
  const lines = readCart();
  const line = lines.find((l) => l.slug === p.slug);
  if (line) {
    line.quantity = Math.min(max, line.quantity + quantity);
    Object.assign(line, { name: p.name, price: p.price, image: p.image });
  } else lines.push({ slug: p.slug, name: p.name, price: p.price, image: p.image, quantity: Math.min(max, quantity) });
  writeCart(lines);
}

/** Orders placed from this browser, so the customer can find their order links again. */
export interface SavedOrder {
  number: string;
  token: string;
  total: number;
  at: string;
}

export function savedOrders(): SavedOrder[] {
  try {
    const v = JSON.parse(store()?.getItem(ORDERS_KEY) || "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

export function saveOrder(o: SavedOrder) {
  try {
    store()?.setItem(ORDERS_KEY, JSON.stringify([o, ...savedOrders().filter((x) => x.number !== o.number)].slice(0, 20)));
  } catch {
    // nothing to do: the order link is also sent by SMS/WhatsApp/email
  }
}

export const orderPath = (number: string, token: string) => `/store/order/${number}?t=${encodeURIComponent(token)}`;
