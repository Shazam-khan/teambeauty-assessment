/**
 * Storefront-facing reviews API.
 *
 * GET  /api/reviews/:sku?shop=...     → list reviews for this shop+SKU
 * POST /api/reviews/:sku              → create one review
 *      body: { shop_domain, customer_name, rating, review_text }
 *
 * CORS-permissive, no auth. In production these would either move
 * behind Shopify App Proxy (HMAC-signed) or restrict Allow-Origin to
 * known shop domains. Documented in the README.
 */
import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { corsPreflight, withCors } from "../cors.server";
import { insertReview, listReviews } from "../reviews.server";

export const loader = async ({ params, request }: LoaderFunctionArgs) => {
  if (request.method === "OPTIONS") return corsPreflight();

  const sku = params.sku;
  const shop = new URL(request.url).searchParams.get("shop");
  if (!sku || !shop) {
    return json({ error: "sku (path) and shop (query) are required" }, withCors({ status: 400 }));
  }

  const reviews = await listReviews(shop, sku);
  return json({ reviews }, withCors());
};

export const action = async ({ params, request }: ActionFunctionArgs) => {
  if (request.method === "OPTIONS") return corsPreflight();
  if (request.method !== "POST") {
    return json({ error: "Method not allowed" }, withCors({ status: 405 }));
  }

  const sku = params.sku;
  if (!sku) {
    return json({ error: "sku is required" }, withCors({ status: 400 }));
  }

  let body: any;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON body" }, withCors({ status: 400 }));
  }

  const shop_domain = String(body?.shop_domain || "").trim();
  const customer_name = String(body?.customer_name || "").trim();
  const review_text = String(body?.review_text || "").trim();
  const rating = Number(body?.rating);

  if (!shop_domain || !customer_name || !review_text) {
    return json(
      { error: "shop_domain, customer_name, and review_text are required" },
      withCors({ status: 400 }),
    );
  }
  if (!Number.isInteger(rating) || rating < 1 || rating > 5) {
    return json({ error: "rating must be an integer 1..5" }, withCors({ status: 400 }));
  }
  if (customer_name.length > 100 || review_text.length > 2000) {
    return json({ error: "customer_name or review_text too long" }, withCors({ status: 400 }));
  }

  const review = await insertReview({
    shop_domain,
    product_sku: sku,
    customer_name,
    rating,
    review_text,
  });

  return json({ review }, withCors({ status: 201 }));
};
