"""Tags for grouping API endpoints."""
from flask_openapi3 import Tag

domain_tag = Tag(name="domain", description="GenRA science domain endpoints.")
uiv3_tag = Tag(name="UI_support_v3", description="UI support functions version 3.")
uiv4_tag = Tag(name="UI_support_v4", description="UI support functions version 4.")
data_admin_tag = Tag(name="Container_Data_Admin", description="Data / admin. endpoints.")
