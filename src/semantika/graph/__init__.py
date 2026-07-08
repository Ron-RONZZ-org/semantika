"""Graph module — semantic triple store.

Provides NodeService, PredicateService, TripleService, ReviewService, ProofService.
Ported from A-semantika with Esperanto-to-English migration.
"""

from semantika.graph.db import get_db, get_services, init_db
from semantika.graph.node_service import NodeService
from semantika.graph.predicate_group_service import PredicateGroupService
from semantika.graph.predicate_service import PredicateService
from semantika.graph.proof_service import ProofService
from semantika.graph.review_service import ReviewService
from semantika.graph.triple_service import TripleService

__all__ = [
    "NodeService",
    "PredicateGroupService",
    "PredicateService",
    "ProofService",
    "ReviewService",
    "TripleService",
    "get_db",
    "get_services",
    "init_db",
]
