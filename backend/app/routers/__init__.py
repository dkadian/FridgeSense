"""HTTP routers. Deliberately thin: each one validates, delegates to a service
and translates domain errors into status codes. No business rules live here."""
