# Changelog

## 1.3.2

- Removes the redundant delivery ETA sensor; delivery date and window remain in the active online orders attributes.
- Removes the Markdown countdown example from the README.
- Cleans up the retired ETA entity from the entity registry when the sensor platform loads.


## 1.3.1

- Stops changing the ETA sensor every minute, preventing countdown updates from filling the activity history.
- Exposes stable window start/end timestamps for a native Markdown card to render the full live countdown range.


## 1.3.0

- Shows a live countdown to the delivery window, including the remaining time inside the arrival window.
- Refreshes the countdown every minute without making additional requests to AB.


## 1.2.0

- Adds account-specific order-status and delivery ETA sensors with preparing, packed, on-the-way, and delivered phases.
- Preserves AB's raw status and delivery details as attributes so unrecognized statuses can be identified without mislabeling them.

## 1.1.1

- Fixes integration manifest ordering and declares the HTTP dependency required by frontend resources.
- Declares config-entry-only YAML setup for Home Assistant validation.

## 1.1.0

- Adds account-specific online-order tracking with recent status, delivery window, item counts, and order total.
- Refreshes order history separately from the 30-second cart updates and omits delivery addresses and instructions from Home Assistant attributes.

## 1.0.0

- First public Marketplace-ready release.
- Adds account-specific AB Plus data and shopping-list entities.
- Includes the combined shopping picker, AB offers browser, and AB Plus barcode dashboard cards.
- Documents Marketplace installation, HACS fallback, account setup, and cookie handling.

