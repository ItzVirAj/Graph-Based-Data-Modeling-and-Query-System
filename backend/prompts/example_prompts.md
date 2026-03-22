# Example Prompts

Use these prompts in the chat panel or against `POST /api/query`.

## Core graph exploration

1. Show me all orders for customer 320000083
2. What invoices are linked to delivery 80738040?
3. Total payment amount for order 740509
4. Which products were in the most orders?
5. Show the full chain from order 740509 to payment
6. List all overdue invoices
7. Count all deliveries connected to invoice 90504204
8. Show all products linked to order 740509
9. Which customers have the most invoices?
10. Find the address connected to customer 320000083
11. Trace invoice 90504204 flow
12. Show payments linked to invoice 90504204
13. Count all orders in the graph
14. Show deliveries for customer 320000083
15. Find node 80738040

## Guardrail rejection example

16. What is the capital of France?

Expected behavior: the system should reject this question because it is not related to the SAP O2C dataset.

## Notes

- If `GEMINI_API_KEY` is not configured, the backend will answer in mock mode.
- IDs can be asked directly when known, for example `order 740509` or `invoice 90504204`.
- Questions outside orders, deliveries, invoices, payments, customers, products, and addresses should be rejected.
