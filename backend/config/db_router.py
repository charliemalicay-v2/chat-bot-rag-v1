"""Send the `rag` app (embeddings) to the pgvector database, everything else to MySQL."""

VECTOR_APPS = {"rag"}


class VectorRouter:
    def db_for_read(self, model, **hints):
        return "vector" if model._meta.app_label in VECTOR_APPS else "default"

    def db_for_write(self, model, **hints):
        return self.db_for_read(model)

    def allow_relation(self, obj1, obj2, **hints):
        # No cross-database relations (Django cannot enforce them).
        return obj1._state.db == obj2._state.db

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in VECTOR_APPS:
            return db == "vector"
        return db == "default"
