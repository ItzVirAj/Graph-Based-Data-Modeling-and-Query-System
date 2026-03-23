# Example Prompts

Use these prompts in the chat panel or against `POST /api/query`.

1. Which products are associated with the highest number of billing documents?
2. Trace the full flow of billing document 90504204
3. Find sales orders with broken or incomplete flows
4. Show me all orders for customer 320000083
5. What invoices are linked to delivery 80738040?
6. Total payment amount for order 740509
7. Which products were in the most orders?
8. Show the full chain from order 740509 to payment
9. What payments are connected to invoice 90504204?
10. Show deliveries for customer 320000083
11. Which of these were delivered?
12. What about their invoices?
13. Find the plant linked to delivery 80738076
14. Show journal entries linked to invoice 90504204
15. What is an order?
16. Define delivery
17. What is the capital of France?

Expected behavior:

- The first 14 should pass and query the SAP O2C dataset.
- `What is the capital of France?` should be rejected by the guardrail.
