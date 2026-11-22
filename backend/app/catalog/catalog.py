"""Product Catalog module for AI Sales Associate."""
from typing import Dict, List, Optional
import re

CATALOG_ITEMS: List[Dict] = [
    # --- SHIRTS ---
    {
        "id": "shirt-01",
        "name": "The Riviera Linen Overshirt",
        "category": "shirts",
        "price": 88.0,
        "original_price": 110.0,
        "description": "Hand-spun breathable European flax linen with a camp collar and relaxed drape. Perfect for warm evening dinners or beachside layering.",
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["Earthy Olive", "Coastal Cream", "Midnight Navy"],
        "material": "100% Normandy Linen",
        "fit": "Relaxed Tailored",
        "occasion": ["vacation", "date night", "casual", "summer wedding"],
        "hero_highlight": "The airy silhouette and texture give you an instant effortless Mediterranean glow. It falls naturally across the chest without clinging.",
        "reviews_summary": "96% say true to size. Customers rave: 'Felt like a movie star on holiday', 'Stays cool even in 90-degree humidity'.",
        "rating": 4.9,
        "review_count": 214,
        "in_stock": True,
        "image_url": "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?auto=format&fit=crop&w=600&q=80",
    },
    {
        "id": "shirt-02",
        "name": "The Oxford Commuter Shirt",
        "category": "shirts",
        "price": 75.0,
        "original_price": 95.0,
        "description": "Heavyweight pinpoint organic cotton weave with 2% elastane for natural flex. Features non-crease tech and mother-of-pearl buttons.",
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "colors": ["Sky Blue", "Crisp White", "French Blue Stripe"],
        "material": "98% Organic Cotton, 2% Elastane",
        "fit": "Modern Slim-Regular",
        "occasion": ["work", "business casual", "interviews", "daily"],
        "hero_highlight": "Structured collar stays sharp with or without a tie, framing your jawline crisply from morning meetings to post-work drinks.",
        "reviews_summary": "93% say true to size. 'Zero wrinkle after 6 hours on a train. Tailoring looks twice its price.'",
        "rating": 4.8,
        "review_count": 348,
        "in_stock": True,
        "image_url": "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?auto=format&fit=crop&w=600&q=80",
    },
    {
        "id": "shirt-03",
        "name": "The Silk-Touch Cuban Collar Shirt",
        "category": "shirts",
        "price": 92.0,
        "original_price": 120.0,
        "description": "Ultra-soft lyocell twill with a retro camp collar and subtle geometric tonal sheen. Flowy drape with zero itch.",
        "sizes": ["M", "L", "XL"],
        "colors": ["Terracotta", "Onyx Black", "Sage Whisper"],
        "material": "100% Eco-Tencel Lyocell",
        "fit": "Boxy Contemporary",
        "occasion": ["date night", "cocktail", "party", "art gallery"],
        "hero_highlight": "Drapes like vintage silk, highlighting your posture while keeping things nonchalantly cool.",
        "reviews_summary": "91% true to size. 'Got three compliments within 20 minutes of walking into the lounge.'",
        "rating": 4.7,
        "review_count": 142,
        "in_stock": True,
        "image_url": "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?auto=format&fit=crop&w=600&q=80",
    },

    # --- PANTS ---
    {
        "id": "pants-01",
        "name": "The All-Day Tailored Chino",
        "category": "pants",
        "price": 98.0,
        "original_price": 125.0,
        "description": "Four-way stretch Italian twill with a hidden expandable waistband and water-repellent finish. The comfort of joggers with bespoke trouser aesthetics.",
        "sizes": ["30x30", "32x30", "32x32", "34x32", "36x32"],
        "colors": ["British Khaki", "Charcoal Gray", "Dark Olive", "Navy"],
        "material": "78% Cotton, 18% Polyamide, 4% Spandex",
        "fit": "Tapered Athletic",
        "occasion": ["work", "travel", "smart casual", "weekend"],
        "hero_highlight": "The subtle taper elongates the legs and sits perfectly atop loafers or clean sneakers without stacking awkward fabric.",
        "reviews_summary": "97% say fit is spot-on. 'I threw out my other chinos. Stretchy enough for airport sprints, sharp enough for boardrooms.'",
        "rating": 4.9,
        "review_count": 520,
        "in_stock": True,
        "image_url": "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?auto=format&fit=crop&w=600&q=80",
    },
    {
        "id": "pants-02",
        "name": "The Pleated Linen-Cotton Trouser",
        "category": "pants",
        "price": 115.0,
        "original_price": 140.0,
        "description": "Single-pleated high-rise trousers cut from a crisp blend of French linen and pima cotton. Side tabs replace belt loops for clean sartorial elegance.",
        "sizes": ["30x30", "32x32", "34x32", "36x32"],
        "colors": ["Sandstone", "Espresso", "Chalk White"],
        "material": "55% Linen, 45% Pima Cotton",
        "fit": "Straight Sartorial",
        "occasion": ["summer wedding", "date night", "fine dining", "resort"],
        "hero_highlight": "The single pleat creates deep vertical lines that give you commanding visual presence and breezy room in the thighs.",
        "reviews_summary": "95% true to size. 'Brought these to a destination wedding in Tuscany. Absolute perfection.'",
        "rating": 4.8,
        "review_count": 189,
        "in_stock": True,
        "image_url": "https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?auto=format&fit=crop&w=600&q=80",
    },
    {
        "id": "pants-03",
        "name": "The Essential Selvedge Denim",
        "category": "pants",
        "price": 128.0,
        "original_price": 155.0,
        "description": "13.5oz Kuroki Mills Japanese selvedge denim, sanforized and washed once for immediate comfort without losing rich indigo fade potential.",
        "sizes": ["30x32", "32x32", "34x32", "36x32"],
        "colors": ["Deep Indigo Wash", "Faded Vintage Stone"],
        "material": "100% Japanese Selvedge Cotton",
        "fit": "Slim Straight",
        "occasion": ["casual", "date night", "concert", "weekend"],
        "hero_highlight": "Substantial, authentic denim feel that shapes to your frame over time. Red-line selvedge cuff flash gives instant enthusiast credit.",
        "reviews_summary": "92% true to size. 'Stiff for the first 2 hours, then molds like a second skin. Incredible longevity.'",
        "rating": 4.9,
        "review_count": 412,
        "in_stock": True,
        "image_url": "https://images.unsplash.com/photo-1542272604-787c3835535d?auto=format&fit=crop&w=600&q=80",
    },

    # --- JACKETS ---
    {
        "id": "jacket-01",
        "name": "The Milan Unstructured Blazer",
        "category": "jackets",
        "price": 220.0,
        "original_price": 275.0,
        "description": "Unlined, soft-shouldered blazer made from Italian stretch wool-hopsack. Breathes effortlessly and resists wrinkling in a weekender bag.",
        "sizes": ["38R", "40R", "42R", "44R"],
        "colors": ["Midnight Navy", "Smoked Charcoal", "Tobacco Camel"],
        "material": "97% Wool Hopsack, 3% Elastane",
        "fit": "Modern Neapolitan",
        "occasion": ["wedding", "business casual", "cocktails", "travel"],
        "hero_highlight": "The soft Neapolitan shoulder curves naturally with zero padding. Makes you look athletic, confident, and dressed up without trying too hard.",
        "reviews_summary": "98% satisfied. 'Fits like a custom $800 bespoke jacket. Rolled it in my carry-on and wore it straight to a dinner.'",
        "rating": 4.95,
        "review_count": 310,
        "in_stock": True,
        "image_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?auto=format&fit=crop&w=600&q=80",
    },
    {
        "id": "jacket-02",
        "name": "The Suede Harrington Bomber",
        "category": "jackets",
        "price": 185.0,
        "original_price": 230.0,
        "description": "Supple micro-suede outer shell with ribbed merino hem and collar. Wind-resistant satin lining and antique brass dual zip.",
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["Caramel Brown", "Slate Blue", "Matte Black"],
        "material": "Vegan Micro-Suede / Merino Blend Trim",
        "fit": "Classic Bomber",
        "occasion": ["date night", "casual", "fall layering", "weekend"],
        "hero_highlight": "A timeless Steve McQueen silhouette. The rich caramel tone pairs with white tees or dark turtlenecks like butter.",
        "reviews_summary": "94% true to size. 'Texture feels luxurious. Wife said it was the best jacket I have ever bought.'",
        "rating": 4.85,
        "review_count": 178,
        "in_stock": True,
        "image_url": "https://images.unsplash.com/photo-1495105787522-5334e3ffa0ef?auto=format&fit=crop&w=600&q=80",
    },
    {
        "id": "jacket-03",
        "name": "The Chore Utility Overshirt Jacket",
        "category": "jackets",
        "price": 140.0,
        "original_price": 170.0,
        "description": "Heavyweight 12oz organic duck canvas with triple-needle stitching, deep patch pockets, and interior passport pocket.",
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "colors": ["Washed Olive", "Desert Tan", "Raw Ecru"],
        "material": "100% Organic Heavy Cotton Canvas",
        "fit": "Rugged Boxy Layer",
        "occasion": ["weekend", "creative office", "coffee runs", "outdoor dinner"],
        "hero_highlight": "Rugged yet refined. It adds masculine structure over any plain tee or hoodie instantly.",
        "reviews_summary": "96% true to size. 'Indestructible feel. Gets softer and looks better with every wear.'",
        "rating": 4.9,
        "review_count": 265,
        "in_stock": True,
        "image_url": "https://images.unsplash.com/photo-1544441893-675973e31985?auto=format&fit=crop&w=600&q=80",
    },
]


def list_catalog() -> List[Dict]:
    """Return all catalog items."""
    return CATALOG_ITEMS


def get_product(product_id: str) -> Optional[Dict]:
    """Retrieve single product by id."""
    for item in CATALOG_ITEMS:
        if item["id"].lower() == product_id.lower():
            return item
    return None


def search_catalog(
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    occasion: Optional[str] = None,
    limit: int = 5,
) -> List[Dict]:
    """
    Search and filter products in the in-memory catalog.
    Matches queries against name, description, material, hero_highlight, and occasion.
    """
    results = CATALOG_ITEMS

    if category:
        cat_lower = category.lower().strip()
        results = [p for p in results if cat_lower in p["category"].lower()]

    if max_price is not None:
        results = [p for p in results if p["price"] <= max_price]

    if occasion:
        occ_lower = occasion.lower().strip()
        results = [
            p for p in results
            if any(occ_lower in o.lower() for o in p.get("occasion", []))
        ]

    if query and query.strip():
        q_tokens = [t.lower() for t in re.split(r"\s+", query.strip()) if len(t) > 2]
        scored_results = []
        for p in results:
            score = 0
            searchable_text = f"{p['name']} {p['category']} {p['description']} {p['material']} {p.get('hero_highlight', '')} {' '.join(p.get('occasion', []))}".lower()
            for token in q_tokens:
                if token in p["name"].lower():
                    score += 5
                elif token in p["category"].lower():
                    score += 4
                elif token in searchable_text:
                    score += 2
            if score > 0 or not q_tokens:
                scored_results.append((score, p))
        scored_results.sort(key=lambda x: x[0], reverse=True)
        results = [item for _, item in scored_results]

    return results[:limit]
