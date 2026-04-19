# Roupa de Gala — Backend

Django REST API for managing formal wear rental and sale operations: clients, service orders, inventory, payments, events, and reporting.

## Stack

- **Python 3.11**
- **Django 4.2 LTS** + **Django REST Framework 3.14**
- **PostgreSQL 16**
- **SimpleJWT** for authentication
- **drf-spectacular** for OpenAPI/Swagger
- **Gunicorn** in production

## Quick start

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd roupadegala

# 2. Copy env template and fill in secrets
cp .env.example .env

# 3. Bring up postgres + app with docker-compose
docker-compose up --build

# Or, run manually:
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The API will be available at `http://localhost:8000/`.

- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- OpenAPI schema: `http://localhost:8000/api/schema/`

## Project layout

```
roupadegala/
├── accounts/              # Person, auth, clients, employees
├── products/              # Product catalog, colors, brands, fabrics
├── service_control/       # Service orders (OS), items, phases, events
├── roupadegala/           # Django project settings + root URLs
├── docs/
│   └── adr/               # Architecture Decision Records
├── tests/                 # Cross-app tests + shared fixtures
├── indexes.sql            # Production DB indexes (apply with psql)
├── docker-compose.yml     # Local dev: app + postgres
├── pytest.ini             # Test config
├── pyproject.toml         # Ruff + isort + pytest config
├── .pre-commit-config.yaml
├── .env.example
└── manage.py
```

## Architecture

See [`docs/adr/`](docs/adr/) for decision records. Start with:

1. [0001 — Record architecture decisions](docs/adr/0001-record-architecture-decisions.md)
2. [0002 — Django + DRF](docs/adr/0002-django-rest-framework.md)
3. [0003 — Service order phase state machine](docs/adr/0003-service-order-phase-state-machine.md)
4. [0004 — Payment details as JSONField](docs/adr/0004-payment-details-jsonfield.md)
5. [0005 — CPF validation and duplicates](docs/adr/0005-cpf-validation-and-duplicates.md)
6. [0006 — Planilha is payment-centric](docs/adr/0006-planilha-payment-centric.md)
7. [0007 — Draft save bypasses validation](docs/adr/0007-draft-save-bypass-validation.md)
8. [0008 — FK SET_NULL on Person delete](docs/adr/0008-fk-set-null-on-person-delete.md)
9. [0009 — Indexes via indexes.sql](docs/adr/0009-indexes-via-indexes-sql.md)

## API — key endpoints

### Auth
- `POST /api/v1/auth/login/` — login with CPF + password
- `POST /api/v1/auth/refresh/` — refresh access token
- `GET  /api/v1/auth/me/` — current user

### Service Orders
- `GET  /api/v1/service-orders/v2/phase/<phase>/` — list by phase (PENDENTE, EM_PRODUCAO, AGUARDANDO_RETIRADA, AGUARDANDO_DEVOLUCAO, FINALIZADO, RECUSADA, ATRASADO)
- `POST /api/v1/service-orders/create/` — create new OS
- `PUT  /api/v1/service-orders/<id>/update/[?draft=true]` — update OS (or save as draft)
- `POST /api/v1/service-orders/<id>/mark-ready/` — EM_PRODUCAO → AGUARDANDO_RETIRADA
- `POST /api/v1/service-orders/<id>/mark-retrieved/` — → AGUARDANDO_DEVOLUCAO (rental) or FINALIZADO (sale)
- `POST /api/v1/service-orders/<id>/mark-paid/` — AGUARDANDO_DEVOLUCAO → FINALIZADO
- `POST /api/v1/service-orders/<id>/refuse/` — → RECUSADA (requires justification)
- `POST /api/v1/service-orders/<id>/return-to-pending/` — RECUSADA → PENDENTE (resgate)
- `POST /api/v1/service-orders/<id>/refund/` — record estorno (admin)
- `POST /api/v1/service-orders/<id>/add-payment/` — add partial payment
- `POST /api/v1/service-orders/<id>/change-phase/` — admin phase override

### Reporting
- `GET  /api/v1/service-orders/dashboard/` — Looker-style analytics dashboard
- `GET  /api/v1/service-orders/finance/` — flat transaction list (Financeiro page)
- `GET  /api/v1/service-orders/planilha/` — spreadsheet view (payment-centric)

### Clients
- `POST /api/v1/clients/register/` — create/update
- `GET  /api/v1/clients/list/` — paginated list + search
- `DELETE /api/v1/clients/<id>/delete/` — admin delete
- `PUT  /api/v1/clients/<id>/update-cpf/` — admin CPF edit

## Testing

```bash
pytest                          # run everything
pytest tests/                   # only the cross-app tests
pytest tests/test_cpf_validation.py
pytest -k planilha              # keyword filter
pytest --reuse-db               # skip DB teardown (faster reruns)
```

Shared fixtures live in `tests/conftest.py`. Fixtures provided:
- `api_client` — unauthenticated DRF client
- `admin_client` — authenticated as an admin Person
- `attendant_client` — authenticated as an ATENDENTE
- `admin_user`, `attendant_user`, `client_person` — Person instances

## Database indexes

Production indexes live in [`indexes.sql`](indexes.sql). They're intentionally outside of Django migrations (see [ADR-0009](docs/adr/0009-indexes-via-indexes-sql.md)) so the DBA can run them during low-traffic windows with `CONCURRENTLY` if needed.

```bash
psql -U <user> -d <db> -f indexes.sql
```

## Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Runs: black, flake8, isort, trailing-whitespace, end-of-file-fixer.

## Deployment

Production runs on Railway:
- `backendrg-production.up.railway.app` (this repo)
- `frontendrg-production.up.railway.app` (sibling React frontend)

The `Dockerfile` at the repo root is the production build. It installs dependencies with `uv` and runs Gunicorn with 4 workers and a 120s timeout.

## License

Proprietary — Decode Dev / Roupa de Gala.
