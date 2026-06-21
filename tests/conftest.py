import os

# Tests must be hermetic: never connect to a live Neo4j or load heavy embedding
# models, regardless of a developer's local .env (the demo .env may set
# VSENTINEL_RETRIEVER=neo4j). Setting it here, before any app module imports,
# wins because the demo's load_dotenv() uses override=False.
os.environ["VSENTINEL_RETRIEVER"] = "bm25"
