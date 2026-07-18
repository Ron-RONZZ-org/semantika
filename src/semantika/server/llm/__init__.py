"""LLM integration — provider abstraction, system prompt, tool registry.

Sub-modules:

* :mod:`~semantika.server.llm.provider` — Provider singleton
* :mod:`~semantika.server.llm.tool_loop` — Re-exports from lightercore
* :mod:`~semantika.server.llm.system_prompt` — Two-file system prompt
* :mod:`~semantika.server.llm.prompt_defaults` — Shipped prompt defaults
* :mod:`~semantika.server.llm.tools` — Dedicated LLM tool registry
  (AI-optimised tools, independent from CLI command registry)
"""
