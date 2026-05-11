/**
 * Reviews data layer — talks to the same Supabase Postgres that backs Tasks 1–3.
 *
 * Note on architecture:
 *   The Shopify session storage in this app still uses Prisma+SQLite
 *   (see `db.server.ts` + `shopify.server.ts`). That's deliberate:
 *   PrismaSessionStorage is the well-tested default and is isolated
 *   from our business data. Reviews — which belong in the shared
 *   schema with brands/products/formulations/etc — go through `pg`.
 */
import pg from "pg";

declare global {
  // Hot reload in dev would otherwise create a new pool on every change.
  // eslint-disable-next-line no-var
  var __reviewsPool: pg.Pool | undefined;
}

function getPool(): pg.Pool {
  if (!global.__reviewsPool) {
    const url = process.env.DATABASE_URL;
    if (!url) {
      throw new Error(
        "DATABASE_URL is not set. Copy values from the repo-root .env into task4/teambeauty-reviews/.env."
      );
    }
    global.__reviewsPool = new pg.Pool({
      connectionString: url,
      // Supabase requires TLS; the pooler cert chain is fine for dev.
      ssl: { rejectUnauthorized: false },
      max: 5,
    });
  }
  return global.__reviewsPool;
}

export type Review = {
  id: number;
  shop_domain: string;
  product_sku: string;
  customer_name: string;
  rating: number;
  review_text: string;
  created_at: string;
};

export async function listReviews(
  shopDomain: string,
  productSku: string,
): Promise<Review[]> {
  const { rows } = await getPool().query<Review>(
    `SELECT id, shop_domain, product_sku, customer_name, rating, review_text, created_at
     FROM reviews
     WHERE shop_domain = $1 AND product_sku = $2
     ORDER BY created_at DESC, id DESC`,
    [shopDomain, productSku],
  );
  return rows;
}

export async function listReviewsForShop(shopDomain: string): Promise<Review[]> {
  const { rows } = await getPool().query<Review>(
    `SELECT id, shop_domain, product_sku, customer_name, rating, review_text, created_at
     FROM reviews
     WHERE shop_domain = $1
     ORDER BY created_at DESC, id DESC
     LIMIT 200`,
    [shopDomain],
  );
  return rows;
}

export async function insertReview(input: {
  shop_domain: string;
  product_sku: string;
  customer_name: string;
  rating: number;
  review_text: string;
}): Promise<Review> {
  const { rows } = await getPool().query<Review>(
    `INSERT INTO reviews (shop_domain, product_sku, customer_name, rating, review_text)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id, shop_domain, product_sku, customer_name, rating, review_text, created_at`,
    [
      input.shop_domain,
      input.product_sku,
      input.customer_name,
      input.rating,
      input.review_text,
    ],
  );
  return rows[0];
}
