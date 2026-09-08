# FridgeSense — API Reference

## Authentication (`/api/auth`)
- `POST /api/auth/register` — Register a new household.
- `POST /api/auth/login` — Obtain JWT access token.
- `GET /api/auth/me` — Return current authenticated user profile.

## Risk & Pantry (`/api/risk`, `/api/pantry`)
- `GET /api/risk/eat-first` — Ranked list of urgent at-risk items.
- `GET /api/pantry` — Active pantry items and summary metrics.
- `POST /api/pantry` — Add a new pantry item.
- `POST /api/pantry/{id}/resolve` — Log outcome (`consumed`, `wasted`, `donated`).

## Recipes & Receipts (`/api/recipes`, `/api/receipt`)
- `GET /api/recipes/suggest` — Suggest recipes prioritizing at-risk ingredient rescue.
- `POST /api/recipes/{id}/cook` — Deduct ingredients from pantry.
- `POST /api/receipt/parse` — Parse pasted receipt text.
- `POST /api/receipt/confirm` — Bulk import parsed receipt lines.

## Impact & Model (`/api/impact`, `/api/meta`, `/api/risk/model`)
- `GET /api/impact/summary` — Avoided ₹, CO₂e, water vs baseline.
- `GET /api/impact/timeseries` — 7-day rolling waste rate and zero-waste streaks.
- `GET /api/risk/model` — Comprehensive model card.
