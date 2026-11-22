"""State definition for LangGraph Sales Engine."""
from typing import Annotated, Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# Customer Intent Stages
IntentStage = Literal["EXPLORER", "EVALUATOR", "READY_TO_BUY"]


class SalesState(TypedDict, total=False):
    """
    SalesState tracks conversational history, customer profile,
    browsing context, intent stage, and cart actions.
    """
    merchant_catalog: bool
    catalog_items: List[Dict[str, Any]]

    messages: Annotated[List[BaseMessage], add_messages]
    customer_profile: Dict[str, Any]
    viewed_products: List[Dict[str, Any]]
    intent_stage: IntentStage
    cart_intent: Dict[str, Any]
    recommended_products: List[Dict[str, Any]]
    current_node: str
    quick_replies: List[str]
    action_payload: Optional[Dict[str, Any]]
    metadata: Dict[str, Any]


def init_sales_state(
    viewed_products: Optional[List[Dict[str, Any]]] = None,
    customer_profile: Optional[Dict[str, Any]] = None,
    intent_stage: IntentStage = "EXPLORER",
) -> SalesState:
    """Helper to initialize a fresh SalesState."""
    return SalesState(
        messages=[],
        customer_profile=customer_profile or {
            "name": None,
            "occasion": None,
            "style_preference": None,
            "size": None,
            "budget": None,
            "hesitation_reason": None,
        },
        viewed_products=viewed_products or [],
        intent_stage=intent_stage,
        cart_intent={
            "items": [],
            "size": None,
            "color": None,
            "applied_discount": None,
            "ready_for_checkout": False,
        },
        recommended_products=[],
        current_node="greeting",
        quick_replies=[],
        action_payload=None,
        metadata={},
    )
