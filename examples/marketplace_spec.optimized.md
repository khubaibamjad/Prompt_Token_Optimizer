# Marketplace specification

Hello, read this whole specification carefully before you start.

## Authentication

Authentication module: handle common user cases, modern application. No direct database exposure to client. Users: mobile devices, desktop browsers, authentication features.

- Do not use any paid third-party services for authentication.
- Keep the authentication code simple, well structured and well commented.
- Write unit tests for the authentication service layer and integration tests for the authentication API.

## Products

Products module: handle common cases, modern application. No direct database exposure to client. Users: mobile, desktop features.

- Do not use any paid third-party services for products.
- Keep the products code simple, well structured and well commented.
- Write unit tests for the products service layer and integration tests for the products API.

## Orders

Orders module: handle common cases, modern application. No direct database exposure to client. Users: mobile, desktop browsers.

- Do not use any paid third-party services for orders.
- Keep the orders code simple, well structured and well commented.
- Write unit tests for the orders service layer and integration tests for the orders API.

## Payments

Payments module: handle common user cases, modern application. No direct database exposure to client. Users: mobile devices, desktop browsers, payments features.

- Do not use any paid third-party services for payments.
- Keep the payments code simple, well structured and well commented.
- Write unit tests for the payments service layer and integration tests for the payments API.

## Admin

Admin module: handle common user cases, modern application. No direct database exposure to client. Users: admin features from mobile, desktop browsers.

- Do not use any paid third-party services for admin.
- Keep the admin code simple, well structured and well commented.
- Write unit tests for the admin service layer and integration tests for the admin API.

## Notifications

Notifications module: handle common cases, no internal database exposure. Users: mobile, desktop.

- Do not use any paid third-party services for notifications.
- Keep the notifications code simple, well structured and well commented.
- Write unit tests for the notifications service layer and integration tests for the notifications API.

## Search

Search module: handle common cases, no internal database exposure. Users: mobile, desktop browsers.

- Do not use any paid third-party services for search.
- Keep the search code simple, well structured and well commented.
- Write unit tests for the search service layer and integration tests for the search API.

## Reviews

Reviews module: handle common cases, no direct database exposure. Users: mobile, desktop.

- Do not use any paid third-party services for reviews.
- Keep the reviews code simple, well structured and well commented.
- Write unit tests for the reviews service layer and integration tests for the reviews API.

## Example code style

```python
def get_order(order_id: int) -> OrderDTO:
    order = repository.find(order_id)
    return OrderDTO.from_entity(order)
```

## Notes

Admin panel: administrators manage everything. First, design architecture and explain how it works. Core build for now, more features later.
