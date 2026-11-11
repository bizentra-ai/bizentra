# BusinessOS integration status

## Shopify

Status: implemented and ready for credentials; not live-account verified.

BusinessOS uses Shopify's standalone authorization-code flow and the versioned GraphQL Admin API `2026-10`. It requests read-only `read_customers`, `read_products`, `read_inventory`, and `read_orders` scopes. The connector imports customers into CRM and products, current variant inventory totals, and orders into Operations. It records provider IDs and checksums so repeat syncs update only records created by the same Shopify connection. Orders retain their source total in provenance notes but are not counted as Finance revenue; payment or accounting reconciliation is required before financial reporting can safely count them.

Setup:

1. Create a Shopify app for a standalone service in the Shopify Dev Dashboard.
2. Configure the application URL to the public BusinessOS URL.
3. Register `https://YOUR_PUBLIC_API/api/integrations/shopify/callback` as an allowed redirect URL.
4. Configure HTTPS webhooks to `https://YOUR_PUBLIC_API/api/integrations/shopify/webhook` if using product/order webhook delivery.
5. Set `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `INTEGRATION_ENCRYPTION_KEY`, and `PUBLIC_API_URL` in the backend process.
6. On the Integrations page enter the permanent `your-store.myshopify.com` domain, connect, approve the displayed scopes, and run the initial sync.

Limitations: the connector is read-only; protected customer data and older-order access can require Shopify review or additional approval. A normal `read_orders` grant can be limited by Shopify's order-access rules. Bulk GraphQL operations are not yet used, so a single object type is capped at 10,000 records per run. Webhooks are signature-checked, deduplicated, and durably queued; scheduled synchronization remains the authoritative importer.

Official references:

- https://shopify.dev/docs/apps/build/authentication-authorization/authenticate-standalone-apps
- https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens
- https://shopify.dev/docs/api/usage/pagination-graphql
- https://shopify.dev/docs/apps/build/webhooks/delivery-structure

## Google Workspace and Microsoft 365

Status: implemented and ready for credentials; not live-account verified in this environment.

These connectors use OAuth with state validation and PKCE, refresh stored encrypted tokens, page through contacts, and import contacts into CRM. They are read-only and do not access email or calendars. Required variables are `{PROVIDER}_CLIENT_ID`, `{PROVIDER}_CLIENT_SECRET`, `INTEGRATION_ENCRYPTION_KEY`, and `PUBLIC_API_URL`.

## Planned connectors

WooCommerce, Etsy, Stripe, PayPal, QuickBooks Online, and Xero have not yet been implemented. They are intentionally absent from the working-provider list until their authentication and synchronization paths are complete and tested.
