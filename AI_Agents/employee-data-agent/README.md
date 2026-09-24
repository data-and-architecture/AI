# Employee Data Agent

A governed AI agent for querying employee data with natural language. The project combines YAML-based metadata, a LangGraph workflow, policy enforcement, validated SQL generation, and a FastAPI service so users can ask HR analytics questions without giving the LLM direct freedom to invent SQL or schema objects.

## What the agent does

- Resolves business vocabulary through a glossary and synonym layer.
- Uses metadata tools to discover approved datasets, metrics, dimensions, and relationships.
- Builds a structured query plan before any SQL is generated.
- Applies authentication, authorization, masking, row filters, and resource limits through a centralized policy engine.
- Compiles governed SQL for PostgreSQL or SQL Server through allowlisted connections.
- Verifies results and returns a natural-language answer.
- Exposes API, admin, session-history, cancellation, audit, and metrics endpoints.

## Architecture

The runtime graph in `agent/graph.py` follows this flow:

```text
question
-> audit_start
-> authenticate
-> metadata
-> query_plan
-> validate_plan
-> policy_gate
-> sql
-> validate_sql
-> database
-> verify_result
-> interpret
-> answer
-> audit
```

If a step fails, the `recovery` node decides whether to retry metadata lookup, retry database execution, or stop with a safe failure response.

## Project layout

```text
employee-data-agent/
├── agent/
│   ├── api.py
│   ├── authentication.py
│   ├── graph.py
│   ├── main.py
│   ├── metadata_loader.py
│   ├── policy_engine.py
│   ├── query_planner.py
│   ├── sql_generator.py
│   ├── sql_server_executor.py
│   ├── postgres_executor.py
│   ├── result_verifier.py
│   └── static/index.html
├── config/
│   ├── connections.yaml
│   ├── security.yaml
│   └── observability/
├── database/
│   ├── schema.sql
│   └── seed.sql
├── metadata/
│   ├── catalog/
│   ├── glossary/
│   └── semantic/
├── prompts/
├── tests/
└── requirements.txt
```

## Requirements

- Python 3.10+
- PostgreSQL for the seeded demo database
- An OpenAI API key for the LLM-driven graph flow
- Optional SQL Server access if you want to use the SQL Server executor

Install dependencies:

```bash
cd AI_Agents/employee-data-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set environment variables before running the full agent:

```bash
export OPENAI_API_KEY="your-openai-key"
export DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/hr_database"
```

If you want OTLP tracing export, also set:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://host:4318/v1/traces"
```

## Database setup

Create and seed the demo HR database:

```bash
createdb hr_database
psql -d hr_database -f database/schema.sql
psql -d hr_database -f database/seed.sql
```

## Metadata and policy configuration

- `metadata/catalog` defines datasets and columns.
- `metadata/glossary` defines business terms and synonyms.
- `metadata/semantic` defines metrics, dimensions, and relationships.
- `config/security.yaml` defines role-based access, masking, and limits.
- `config/connections.yaml` defines allowlisted read-only database connections.

Included prototype roles:

- `DATA_ANALYST`: governed data access, no SQL visibility
- `DATA_ENGINEER`: can view SQL when combined with a data-access role
- `DATA_ADMIN`: can view SQL and admin endpoints

Prototype bearer tokens used by the app:

- `demo-token`
- `technical-token`
- `admin-token`

## Running the project

Validate metadata loading without the LLM:

```bash
python -m agent.metadata_loader
```

Run the CLI agent:

```bash
python -m agent.main
```

Run the API and browser UI:

```bash
uvicorn agent.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for the chat UI.

## API endpoints

Main endpoints:

- `GET /health`
- `GET /metrics`
- `POST /chat`
- `POST /chat/{request_id}/cancel`
- `GET /sessions/{session_id}`
- `GET /admin/metadata`
- `GET /admin/audit`

Example chat request:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Authorization: Bearer demo-token' \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "How many employees are in each department?",
    "session_id": "demo-session",
    "request_id": "demo-request"
  }'
```

The API response includes:

- `answer`
- `result`
- `request_id`
- `correlation_id`
- `session_id`
- `explanation`
- `authorized_sql` when the caller is allowed to see SQL

## Example supported questions

- `How many employees are there?`
- `How many employees are in each department?`
- `How many staff work in each team?`
- `How many active employees are in Riyadh?`
- `Active employees in Riyadh hired after 2023`

The tests also cover safe failures for unsupported metrics, ambiguous requests, authorization denials, and SQL injection-style input.

## Testing

Run the test suite with:

```bash
python -m unittest discover -s tests
```

Notable coverage includes:

- metadata loading and synonym resolution
- governed API behavior and role-based SQL visibility
- policy enforcement and audit handling
- SQL validation and recovery behavior
- MVP evaluation cases for approved and rejected queries

## Notes

- The README previously referenced a phase-based write-up and a `.env.example` file. The current project is already the integrated implementation, and environment variables are configured manually.
- Authentication is still a prototype mapping in `agent/authentication.py`. Replace it with your real identity provider before production use.
- All database connections are expected to be read-only and explicitly registered in `config/connections.yaml`.
