"""Graph module — semantic triple store.

Provides NodeService, PredicateService, TripleService, ReviewService, ProofService.
Ported from A-semantika with Esperanto-to-English migration.
"""

from semantika.graph.db import get_db, init_db, get_services
from semantika.graph.node_service import NodeService
from semantika.graph.predicate_service import PredicateService
from semantika.graph.predicate_group_service import PredicateGroupService
from semantika.graph.triple_service import TripleService
from semantika.graph.review_service import ReviewService
from semantika.graph.proof_service import ProofService

__all__ = [
    "get_db",
    "init_db",
    "get_services",
    "NodeService",
    "PredicateService",
    "PredicateGroupService",
    "TripleService",
    "ReviewService",
    "ProofService",
]
