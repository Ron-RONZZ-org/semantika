"""Command engine — parses !commands, dispatches to handlers.

Handlers are registered via @command decorators in the handlers/ package.
The side-effect import that triggers registration lives in routes/command.py
to avoid circular imports with graph service dependencies.
"""
