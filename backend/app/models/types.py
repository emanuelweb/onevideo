from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# JSONB en PostgreSQL; JSON genérico en otros motores (p. ej. SQLite en tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")
