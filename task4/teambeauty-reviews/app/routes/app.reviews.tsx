/**
 * Admin: list reviews submitted across this shop's products.
 *
 * Authenticated via Shopify session — we scope by session.shop so each
 * merchant only sees their own reviews.
 */
import type { LoaderFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import {
  Page,
  Layout,
  Card,
  IndexTable,
  Text,
  Badge,
  EmptyState,
  BlockStack,
} from "@shopify/polaris";
import { TitleBar } from "@shopify/app-bridge-react";

import { authenticate } from "../shopify.server";
import { listReviewsForShop } from "../reviews.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { session } = await authenticate.admin(request);
  const reviews = await listReviewsForShop(session.shop);
  return json({ reviews, shop: session.shop });
};

export default function ReviewsAdmin() {
  const { reviews, shop } = useLoaderData<typeof loader>();

  if (reviews.length === 0) {
    return (
      <Page>
        <TitleBar title="Reviews" />
        <Layout>
          <Layout.Section>
            <Card>
              <EmptyState
                heading="No reviews yet"
                action={{
                  content: "How to test",
                  url: "https://shopify.dev/docs/apps/online-store/theme-app-extensions",
                  external: true,
                }}
                image=""
              >
                <p>
                  Add the <b>Product reviews</b> app block to any product page
                  in your theme, then submit a review from the storefront.
                </p>
                <p style={{ marginTop: "1em" }}>
                  Currently scoped to: <code>{shop}</code>
                </p>
              </EmptyState>
            </Card>
          </Layout.Section>
        </Layout>
      </Page>
    );
  }

  const rowMarkup = reviews.map((r, index) => (
    <IndexTable.Row id={String(r.id)} key={r.id} position={index}>
      <IndexTable.Cell>{r.product_sku}</IndexTable.Cell>
      <IndexTable.Cell>{r.customer_name}</IndexTable.Cell>
      <IndexTable.Cell>
        <Badge tone={r.rating >= 4 ? "success" : r.rating <= 2 ? "critical" : "attention"}>
          {`${r.rating} / 5`}
        </Badge>
      </IndexTable.Cell>
      <IndexTable.Cell>
        <Text as="span" truncate>
          {r.review_text}
        </Text>
      </IndexTable.Cell>
      <IndexTable.Cell>{new Date(r.created_at).toLocaleString()}</IndexTable.Cell>
    </IndexTable.Row>
  ));

  return (
    <Page>
      <TitleBar title="Reviews" />
      <Layout>
        <Layout.Section>
          <BlockStack gap="400">
            <Card padding="400">
              <Text as="p" tone="subdued">
                Showing {reviews.length} review{reviews.length === 1 ? "" : "s"}{" "}
                for <code>{shop}</code>. AI summaries are shown on the
                storefront product page itself.
              </Text>
            </Card>
            <Card padding="0">
              <IndexTable
                resourceName={{ singular: "review", plural: "reviews" }}
                itemCount={reviews.length}
                selectable={false}
                headings={[
                  { title: "Product SKU" },
                  { title: "Customer" },
                  { title: "Rating" },
                  { title: "Review" },
                  { title: "Submitted" },
                ]}
              >
                {rowMarkup}
              </IndexTable>
            </Card>
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}
