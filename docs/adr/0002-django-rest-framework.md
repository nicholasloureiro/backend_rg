# 2. Use Django + Django REST Framework for backend

Date: 2026-04-19

## Status

Accepted

## Context

The business needs a backend to manage formal wear rental/sale orders, clients, products, payments, and reporting. Requirements:

- Strong data modelling with foreign keys, migrations, and a mature ORM
- Authentication and role-based permissions out of the box
- Admin interface for operational staff
- PostgreSQL as the primary datastore
- OpenAPI/Swagger for API documentation consumed by a React frontend
- Pragmatic Python ecosystem familiar to the team

## Decision

Use **Django 4.2 LTS** with **Django REST Framework 3.14** as the HTTP layer.

- **`djangorestframework-simplejwt`** for JWT auth (7-day access token, 30-day refresh token, token blacklisting)
- **`drf-spectacular`** for OpenAPI schema + Swagger UI at `/api/docs/`
- **`django-cors-headers`** for CORS (React frontend on a different origin)
- **PostgreSQL** via `psycopg2-binary`
- **Gunicorn** as the production WSGI server

Three Django apps:
- `accounts` — users, persons (clients + employees), contacts, addresses, cities
- `products` — product catalog, temporary products, colors, brands, fabrics
- `service_control` — service orders (OS), items, phases, events, refusals

## Consequences

- **Pros:** Mature ORM handles complex relational schema (ServiceOrder ↔ Person ↔ PersonsContacts/Adresses); automatic migrations; Django admin available for ops; rich ecosystem.
- **Cons:** Django is synchronous; high-concurrency request patterns would need special handling (not needed today).
- We accept the verbosity of Django over FastAPI because the team is more familiar with Django and the business is CRUD-heavy, not real-time.
- `select_related` / `prefetch_related` must be used deliberately — naive views cause N+1 queries on nested client/payment data.
