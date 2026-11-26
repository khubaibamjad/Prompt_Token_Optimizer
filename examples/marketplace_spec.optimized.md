# Marketplace specification

Read specification carefully before starting.

## Authentication

Authentication module: handle common user cases, modern application. No direct database exposure to client. Users: mobile devices, desktop browsers, authentication features.

- Do not use paid third-party services for authentication.
- Keep the authentication code simple, well structured and well commented.
- Write unit tests: authentication service layer. Write integration tests: authentication API.

## Products

Products module: handle common cases, modern application. No direct database exposure to client. Users: mobile, desktop features.

- Do not use paid third-party services for products.
- Keep the products code simple, well structured and well commented.
- Write unit tests: products service layer. Integration tests: products API.

## Orders

Orders module: handle common cases, modern application. No direct database exposure to client. Users: mobile, desktop browsers.

- Do not use paid third-party services for orders.
- Keep the orders code simple, well structured and well commented.
- Write unit tests: orders service layer. Integration tests: orders API.

## Payments

Payments module: handle common user cases, modern application. No direct database exposure to client. Users: mobile devices, desktop browsers, payments features.

- Do not use paid third-party services for payments.
- Keep the payments code simple, well structured and well commented.
- Write unit tests: payments service layer. Integration tests: payments API.

## Admin

Admin module: handle common user cases, modern application. No direct database exposure to client. Users: admin features from mobile, desktop browsers.

- Do not use paid third-party services for admin.
- Keep the admin code simple, well structured and well commented.
- Write unit tests: admin service layer. Write integration tests: admin API.

## Notifications

Notifications module: handle common cases, no internal database exposure. Users: mobile, desktop.

- Do not use paid third-party services for notifications.
- Keep the notifications code simple, well structured and well commented.
- Write unit tests: notifications service layer. Integration tests: notifications API.

## Search

Search module: handle common cases, no internal database exposure. Users: mobile, desktop browsers.

- Do not use paid third-party services for search.
- Keep the search code simple, well structured and well commented.
- Write unit tests: search service layer. Integration tests: search API.

## Reviews

Reviews module: handle common cases, no direct database exposure. Users: mobile, desktop.

- Do not use paid third-party services for reviews.
- Keep reviews code simple, well structured, well commented.
- Write unit tests: reviews service layer. Integration tests: reviews API.

## Example code style

```python
def get_order(order_id: int) -> OrderDTO:
    order = repository.find(order_id)
    return OrderDTO.from_entity(order)
```

## Notes

Admin panel: administrators manage everything. First, design architecture and explain how it works. Core build for now, more features later.
