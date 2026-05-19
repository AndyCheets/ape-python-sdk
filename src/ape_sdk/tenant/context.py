from pydantic import BaseModel, ConfigDict, Field


class TenantWorkerContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_key: str = Field(alias="tenantKey")
    display_name: str = Field(alias="displayName")
    database_name: str = Field(alias="databaseName")
    enabled_modules: list[str] = Field(default_factory=list, alias="enabledModules")
    tenant_database_connection_string: str = Field(alias="tenantDatabaseConnectionString")
