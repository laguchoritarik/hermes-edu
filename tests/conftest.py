"""Keep checkpoint deserialization strict before LangGraph test imports."""

import os

os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
