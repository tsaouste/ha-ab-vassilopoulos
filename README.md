# AB Vassilopoulos for Home Assistant

An unofficial Home Assistant integration for the AB Vassilopoulos online store in Greece. It connects Home Assistant to your AB account and provides AB Plus loyalty data, account-specific shopping carts, product search, and an offers browser with companion dashboard cards.

This project is community-made and is not affiliated with or supported by AB Vassilopoulos. It uses AB's online services, which may change without notice.

<!-- ha-marketplace:exclude-start -->
## Install from the Home Assistant Marketplace

This repository is a custom Marketplace repository. Until it is accepted into the shared catalog, add it by link:

1. In Home Assistant, open **Settings → Marketplace**.
2. Select **Add from link**.
3. Enter `tsaouste/ha-ab-vassilopoulos` (or `https://github.com/tsaouste/ha-ab-vassilopoulos`) and select **Add**.
4. If asked for a type, choose **Integration**.
5. Open **AB Vassilopoulos**, select **Install**, and follow Home Assistant's restart prompt.
6. Add the integration from **Settings → Devices & services → Add integration → AB Vassilopoulos**.

[Open this repository in your Home Assistant Marketplace](https://my.home-assistant.io/redirect/marketplace_repository/?owner=tsaouste&repository=ha-ab-vassilopoulos&category=integration)

The Marketplace requires Home Assistant 2026.11 or newer. For earlier Home Assistant versions, install it with HACS: open **HACS → Integrations → ⋮ → Custom repositories**, add the same GitHub URL with category **Integration**, then install it, restart Home Assistant, and add the integration under **Settings → Devices & services**.
<!-- ha-marketplace:exclude-end -->

## What it provides

- AB Plus points balance, profile and loyalty information exposed as Home Assistant entities.
- A separate Home Assistant to-do shopping list for each configured AB account. Cart items and quantities synchronize with AB; checking an item removes it from the active AB cart and keeps it in completed items for quick reordering. Unchecking it adds it back to the cart.
- A combined shopping-list and product-picker dashboard card with AB product search, quantities, images, prices, availability, and cart totals.
- An AB offers dashboard card with paged product results, offer pricing, offer details, and controls to add selected products to the chosen account's cart.
- An AB Plus barcode dashboard card.
- Services for product search, cart operations, offer browsing, and loyalty-card data.

The account cookie is stored by Home Assistant for the integration. Keep it private and replace it through the integration's reauthentication flow if AB expires the session.

## Configure the AB account

During setup, the integration asks for the Cookie request header from a signed-in session on [ab.gr](https://www.ab.gr/). The integration does not ask for or store your AB password.

### Find the Cookie header in Firefox

1. Sign in to ab.gr in Firefox and keep the session active.
2. Press **F12** and open **Network**.
3. Reload the AB page. Select a request to `www.ab.gr` whose path starts with `/api/v1/`.
4. In **Headers**, find **Request Headers → Cookie** and copy its value.
5. Paste that value into the integration setup form in Home Assistant.

Do not post the cookie in an issue, screenshot, or chat. It grants access to your AB session. If the session expires, sign in to AB again, copy the new Cookie header, then use the integration's **Reconfigure** flow.

To use more than one AB account, add the integration once per account and provide that account's own cookie. Each entry creates independent account data and shopping-list entities.

## Dashboard cards

The integration registers its JavaScript resources automatically. After installing or updating the integration, restart Home Assistant when prompted and reload the browser or mobile app.

Add cards from the dashboard card picker:

- **AB Shopping** combines the account's shopping list and product picker.
- **AB Offers** browses offers for the selected account and adds products to its cart.
- **AB Plus** displays the selected account's loyalty card and barcode.

Choose the corresponding account's to-do entity in each card's visual editor. A card without a selected account remains empty.

## Notes and limitations

- The AB API is not a public integration API. AB may change or limit it, and temporary AB outages can result in delayed or unavailable data.
- Product prices, promotions, and availability are read from AB and can change before checkout.
- AB does not provide the integration with a reliable indicator that distinguishes a submitted order from other cart removals. Cart changes are synchronized with Home Assistant's completed section for reorder convenience.

## Issues

Please include the Home Assistant version, integration version, relevant entity/service, and a redacted error message. Never include account cookies, access tokens, or other authentication data.

## License

MIT
