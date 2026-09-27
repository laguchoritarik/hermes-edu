# LangGraph role

LangGraph owns workflow orchestration only.

Planned concepts:

- `StateGraph` with typed state;
- reducers for append/merge fields;
- conditional edges for deterministic routing;
- bounded audit/revision loops;
- persistent checkpointer and `thread_id`;
- `interrupt()` / `Command(resume=...)` for human review;
- subgraphs for document types;
- retry policies for selected I/O nodes;
- streaming/parallelism only when a demonstrated need appears.

A LangGraph node should coordinate one meaningful step and delegate provider/database/document details to application services/adapters.
