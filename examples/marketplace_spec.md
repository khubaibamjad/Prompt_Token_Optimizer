# Marketplace specification

Hello, I would like you to please read this whole specification carefully before you start.

## Authentication

I want you to make sure that the authentication module should be able to handle all of the common cases that users would expect from a modern application. It is important to note that the authentication module must not expose any internal database entities directly to the client. Users should be able to use the authentication features from both mobile devices and desktop browsers without any problems.

- Do not use any paid third-party services for authentication.
- Keep the authentication code simple, well structured and well commented.
- Write unit tests for the authentication service layer and integration tests for the authentication API.

## Products

I want you to make sure that the products module should be able to handle all of the common cases that users would expect from a modern application. It is important to note that the products module must not expose any internal database entities directly to the client. Users should be able to use the products features from both mobile devices and desktop browsers without any problems.

- Do not use any paid third-party services for products.
- Keep the products code simple, well structured and well commented.
- Write unit tests for the products service layer and integration tests for the products API.

## Orders

I want you to make sure that the orders module should be able to handle all of the common cases that users would expect from a modern application. It is important to note that the orders module must not expose any internal database entities directly to the client. Users should be able to use the orders features from both mobile devices and desktop browsers without any problems.

- Do not use any paid third-party services for orders.
- Keep the orders code simple, well structured and well commented.
- Write unit tests for the orders service layer and integration tests for the orders API.

## Payments

I want you to make sure that the payments module should be able to handle all of the common cases that users would expect from a modern application. It is important to note that the payments module must not expose any internal database entities directly to the client. Users should be able to use the payments features from both mobile devices and desktop browsers without any problems.

- Do not use any paid third-party services for payments.
- Keep the payments code simple, well structured and well commented.
- Write unit tests for the payments service layer and integration tests for the payments API.

## Admin

I want you to make sure that the admin module should be able to handle all of the common cases that users would expect from a modern application. It is important to note that the admin module must not expose any internal database entities directly to the client. Users should be able to use the admin features from both mobile devices and desktop browsers without any problems.

- Do not use any paid third-party services for admin.
- Keep the admin code simple, well structured and well commented.
- Write unit tests for the admin service layer and integration tests for the admin API.

## Notifications

I want you to make sure that the notifications module should be able to handle all of the common cases that users would expect from a modern application. It is important to note that the notifications module must not expose any internal database entities directly to the client. Users should be able to use the notifications features from both mobile devices and desktop browsers without any problems.

- Do not use any paid third-party services for notifications.
- Keep the notifications code simple, well structured and well commented.
- Write unit tests for the notifications service layer and integration tests for the notifications API.

## Search

I want you to make sure that the search module should be able to handle all of the common cases that users would expect from a modern application. It is important to note that the search module must not expose any internal database entities directly to the client. Users should be able to use the search features from both mobile devices and desktop browsers without any problems.

- Do not use any paid third-party services for search.
- Keep the search code simple, well structured and well commented.
- Write unit tests for the search service layer and integration tests for the search API.

## Reviews

I want you to make sure that the reviews module should be able to handle all of the common cases that users would expect from a modern application. It is important to note that the reviews module must not expose any internal database entities directly to the client. Users should be able to use the reviews features from both mobile devices and desktop browsers without any problems.

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

The admin pannel shuld let administrators manage evrything. Before coding, figure out the architecture and explain how everything will work. I might add more features later, so for now just build the core.

Thank you so much in advance for your help!
