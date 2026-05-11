/**
 * GET /api/summary/:sku?shop=...
 *
 * Returns a one-sentence Groq-generated summary of all reviews for the
 * given shop+SKU plus the review count. Recomputed on every call (no
 * cache) — fine for demo volumes.
 */
import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

import { corsPreflight, withCors } from "../cors.server";
import { listReviews } from "../reviews.server";
import { summarizeReviews } from "../summary.server";

export const loader = async ({ params, request }: LoaderFunctionArgs) => {
  if (request.method === "OPTIONS") return corsPreflight();

  const sku = params.sku;
  const shop = new URL(request.url).searchParams.get("shop");
  if (!sku || !shop) {
    return json({ error: "sku (path) and shop (query) are required" }, withCors({ status: 400 }));
  }

  const reviews = await listReviews(shop, sku);
  const summary = await summarizeReviews(reviews);

  return json({ summary, review_count: reviews.length }, withCors());
};
