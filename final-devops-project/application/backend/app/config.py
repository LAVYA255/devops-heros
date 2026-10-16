"""Runtime configuration, read from environment variables.

Everything here is non-secret and comes from a ConfigMap in Kubernetes. The one
secret value, the database password, only ever arrives inside DATABASE_URL, which
is assembled from a Secret at deploy time and never written to a file.
"""
import os


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://kharcha:kharcha@localhost:5432/kharcha",
        )
        self.app_version = os.getenv("APP_VERSION", "dev")
        self.currency = os.getenv("CURRENCY", "INR")
        # Monthly spending budget, used by the summary endpoint to report how much
        # of the month's budget is gone. Lives in the ConfigMap so changing it is a
        # config change, not a code change.
        self.monthly_budget = float(os.getenv("MONTHLY_BUDGET", "20000"))


settings = Settings()
