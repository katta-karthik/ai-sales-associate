"""State definition for LangGraph Sales Engine."""
from typing import Annotated, Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# Customer Intent Stages
IntentStage = Literal["EXPLORER", "EVALUATOR", "READY_TO_BUY"]


class StylistStructuredResponse(BaseModel):
    """Structured response schema for modern LangChain structured output."""
    message: str = Field(description="Snappy 1-2 sentence response under 25 words")
    quick_replies: List[str] = Field(default_factory=list, description="2-3 dynamic quick-reply pills")
    suggested_product_id: Optional[str] = Field(default=None, description="Recommended product SKU/ID if applicable")
    action_type: Optional[str] = Field(default=None, description="Cart or navigation action type")


class SalesState(TypedDict, total=False):
    """
    SalesState tracks conversational history, customer profile,
    browsing context, intent stage, and cart actions across multi-turn sessions.
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

    # Dynamic store identity & shopper context
    store_name: str
    store_domain: Optional[str]
    currency: str
    brand_tone: Optional[str]
    shopper_uuid: Optional[str]
    customer_id: Optional[str]
    hesitation_trigger: Optional[Dict[str, Any]]
    promo_code: Optional[str]
    allow_discounts: bool


def init_sales_state(
    viewed_products: Optional[List[Dict[str, Any]]] = None,
    customer_profile: Optional[Dict[str, Any]] = None,
    intent_stage: IntentStage = "EXPLORER",
    store_name: str = "Our Store",
    store_domain: Optional[str] = None,
    currency: str = "$",
    brand_tone: Optional[str] = None,
    shopper_uuid: Optional[str] = None,
    customer_id: Optional[str] = None,
    hesitation_trigger: Optional[Dict[str, Any]] = None,
    merchant_catalog: Optional[bool] = None,
    catalog_items: Optional[List[Dict[str, Any]]] = None,
    promo_code: Optional[str] = None,
    allow_discounts: Optional[bool] = None,
) -> SalesState:
    """Helper to initialize a fresh SalesState with default memory channels and dynamic identity."""
    profile = customer_profile or {
        "name": None,
        "occasion": None,
        "style_preference": None,
        "fit_preference": None,
        "size": None,
        "budget": None,
        "hesitation_reason": None,
        "customer_id": customer_id,
        "shopper_uuid": shopper_uuid,
        "has_converted": False,
        "conversion_count": 0,
    }
    if customer_id and "customer_id" not in profile:
        profile["customer_id"] = customer_id
    if shopper_uuid and "shopper_uuid" not in profile:
        profile["shopper_uuid"] = shopper_uuid
    if hesitation_trigger and isinstance(hesitation_trigger, dict):
        profile["hesitation_reason"] = (
            hesitation_trigger.get("type") or
            hesitation_trigger.get("reason") or
            hesitation_trigger.get("suggestedNudge")
        )

    # Determine whether running in merchant mode vs internal demo mode
    is_merchant = False
    if merchant_catalog is not None:
        is_merchant = merchant_catalog
    elif catalog_items is not None:
        is_merchant = True
    elif store_name and store_name.strip().lower() not in ("karthik & co.", "karthik & co", "karthik & co. modern apparel", "demo store", "our store"):
        is_merchant = True
    elif store_domain and "localhost" not in store_domain and "127.0.0.1" not in store_domain:
        is_merchant = True

    effective_allow_discounts = allow_discounts if allow_discounts is not None else (not is_merchant)
    effective_promo = promo_code if promo_code is not None else ("STYLIST10" if not is_merchant else None)

    state_dict = SalesState(
        messages=[],
        customer_profile=profile,
        viewed_products=viewed_products or [],
        intent_stage=intent_stage,
        cart_intent={
            "items": [],
            "size": None,
            "color": None,
            "applied_discount": effective_promo if effective_allow_discounts else None,
            "ready_for_checkout": False,
        },
        recommended_products=[],
        current_node="greeting",
        quick_replies=[],
        action_payload=None,
        metadata={},
        store_name=store_name,
        store_domain=store_domain,
        currency=currency,
        brand_tone=brand_tone,
        shopper_uuid=shopper_uuid,
        customer_id=customer_id,
        hesitation_trigger=hesitation_trigger,
        merchant_catalog=is_merchant,
        allow_discounts=effective_allow_discounts,
        promo_code=effective_promo,
    )
    if catalog_items is not None:
        state_dict["catalog_items"] = catalog_items
    elif not is_merchant:
        # demo environment seed items
        pass

    return state_dict
