/**
 * Karthik & Co. Modern Apparel - Store Catalog & Client Interactions
 */

const STORE_CATALOG = {
  "sovereign-blazer": {
    id: "sovereign-blazer",
    sku: "KC-BLZ-001",
    title: "The Sovereign Merino Wool Blazer",
    category: "men",
    categoryLabel: "Men's Collection",
    price: 349.00,
    compareAtPrice: 420.00,
    rating: 4.9,
    reviewCount: 128,
    badge: "Bestseller",
    shortDescription: "Unstructured luxury tailoring crafted from superfine 120s Italian Merino wool. Drapes effortlessly from executive boardroom to evening dinner.",
    fullDescription: "Tailored in Biella, Italy from 100% superfine Merino wool, The Sovereign Blazer embodies the quiet confidence of relaxed modern elegance. Featuring a half-canvas construction, soft unpadded shoulders, hand-stitched pick lapels, and genuine horn buttons, this piece adapts to your body's silhouette with breathability and natural wrinkle resistance.",
    details: [
      "100% Superfine 120s Italian Merino Wool (Biella Mills)",
      "Unstructured soft-shoulder tailored cut",
      "Half-canvas interior for lightweight, breathable drape",
      "Dual rear side vents and functioning four-button cuffs",
      "Genuine matte horn buttons with contrast thread finish",
      "Interior jet passport pocket and pen slot",
      "Dry clean only"
    ],
    colors: [
      { name: "Midnight Navy", hex: "#1a2238", selected: true },
      { name: "Heather Charcoal", hex: "#363a45", selected: false },
      { name: "Warm Camel", hex: "#a47551", selected: false }
    ],
    sizes: ["S", "M", "L", "XL"],
    defaultSize: "M",
    inventoryRemaining: 4,
    images: [
      {
        url: "media/photo-1594938298603-c8148c4dae35.jpg",
        alt: "The Sovereign Merino Wool Blazer - Front View"
      },
      {
        url: "media/photo-1507679799987-c73779587ccf.jpg",
        alt: "The Sovereign Merino Wool Blazer - Lifestyle Detail"
      },
      {
        url: "media/photo-1617137984095-74e4e5e3613f.jpg",
        alt: "The Sovereign Merino Wool Blazer - Styling Pair"
      }
    ]
  },
  "oxford-shirt": {
    id: "oxford-shirt",
    sku: "KC-SHT-014",
    title: "The Minimalist Oxford Button-Down",
    category: "men",
    categoryLabel: "Men's Collection",
    price: 128.00,
    compareAtPrice: 150.00,
    rating: 4.8,
    reviewCount: 94,
    badge: "Essential",
    shortDescription: "Woven from 100% long-staple organic Supima cotton. Heavyweight 5.5 oz basketweave with broken-in softness from day one.",
    fullDescription: "The quintessence of refined casualwear. Our Minimalist Oxford features a relaxed 3.25-inch button-down collar with a graceful roll, genuine mother-of-pearl buttons, and a clean back pleat that permits unrestricted movement while maintaining a clean, tailored drape.",
    details: [
      "100% American-grown Supima Cotton",
      "Heavyweight 5.5 oz traditional basketweave Oxford cloth",
      "Pre-washed with organic enzymes for non-shrink durability",
      "Natural Australian mother-of-pearl buttons",
      "Single needle lockstitch construction throughout",
      "Machine wash warm, hang dry or iron damp"
    ],
    colors: [
      { name: "Crisp White", hex: "#f8f9fa", selected: true },
      { name: "Sky Blue", hex: "#90caf9", selected: false },
      { name: "Slate Grey", hex: "#78909c", selected: false }
    ],
    sizes: ["S", "M", "L", "XL"],
    defaultSize: "M",
    inventoryRemaining: 7,
    images: [
      {
        url: "media/photo-1602810318383-e386cc2a3ccf.jpg",
        alt: "The Minimalist Oxford Button-Down - Front View"
      },
      {
        url: "media/photo-1596755094514-f87e34085b2c.jpg",
        alt: "The Minimalist Oxford Button-Down - Fabric Close Up"
      }
    ]
  },
  "tailored-trousers": {
    id: "tailored-trousers",
    sku: "KC-TRS-022",
    title: "Pleated Tailored Wool Trousers",
    category: "men",
    categoryLabel: "Men's Collection",
    price: 148.00,
    compareAtPrice: 185.00,
    rating: 4.85,
    reviewCount: 82,
    badge: "Trending",
    shortDescription: "High-rise relaxed fit with single reverse pleats and gentle ankle taper. Hidden side elastic comfort insert.",
    fullDescription: "A modern homage to classic Savile Row tailoring. Cut from breathable four-season tropical wool with a touch of stretch for daylong comfort. Features dual forward pleats, blind hem construction, and internal curtain waistband.",
    details: [
      "98% Virgin Wool, 2% Elastane for natural movement",
      "Single reverse forward pleats for leg elongation",
      "Concealed side-tab waistband adjusters",
      "Slanted side pockets and double welt back pockets",
      "Dry clean recommended"
    ],
    colors: [
      { name: "Slate Charcoal", hex: "#37474f", selected: true },
      { name: "Olive Green", hex: "#4b5320", selected: false },
      { name: "Espresso", hex: "#3e2723", selected: false }
    ],
    sizes: ["S", "M", "L", "XL"],
    defaultSize: "M",
    inventoryRemaining: 5,
    images: [
      {
        url: "media/photo-1624378439575-d8705ad7ae80.jpg",
        alt: "Pleated Tailored Wool Trousers - Standing Fit"
      },
      {
        url: "media/photo-1548883354-7622d03aca27.jpg",
        alt: "Pleated Tailored Wool Trousers - Detail View"
      }
    ]
  },
  "cashmere-crewneck": {
    id: "cashmere-crewneck",
    sku: "KC-KNIT-008",
    title: "Pure Mongolian Cashmere Crewneck",
    category: "women",
    categoryLabel: "Women's Collection",
    price: 195.00,
    compareAtPrice: 240.00,
    rating: 4.95,
    reviewCount: 164,
    badge: "Customer Favorite",
    shortDescription: "Ultra-plush Grade-A Mongolian cashmere fiber. 2-ply 12-gauge knit that maintains lofty softness without pilling.",
    fullDescription: "Crafted exclusively from ethically sourced raw fibers from the inner Mongolian steppe. The fibers are hand-selected for extraordinary length and micron fineness (15.5 microns), delivering cloud-like warmth without heaviness.",
    details: [
      "100% Grade-A Mongolian Cashmere",
      "2-ply 12-gauge knit construction",
      "Tubular ribbed neck, cuffs, and hem",
      "Reinforced shoulder seams to prevent stretching",
      "Hand wash cold with wool detergent, dry flat"
    ],
    colors: [
      { name: "Heather Grey", hex: "#b0bec5", selected: true },
      { name: "Oatmeal Cream", hex: "#e0d7c6", selected: false },
      { name: "Midnight Black", hex: "#1c1c1e", selected: false }
    ],
    sizes: ["S", "M", "L", "XL"],
    defaultSize: "S",
    inventoryRemaining: 3,
    images: [
      {
        url: "media/photo-1576566588028-4147f3842f27.jpg",
        alt: "Pure Mongolian Cashmere Crewneck - Main Shot"
      },
      {
        url: "media/photo-1434389677669-e08b4cac3105.jpg",
        alt: "Pure Mongolian Cashmere Crewneck - Soft Texture"
      }
    ]
  },
  "silk-slip-dress": {
    id: "silk-slip-dress",
    sku: "KC-DRS-005",
    title: "The Bias-Cut Mulberry Silk Slip Dress",
    category: "women",
    categoryLabel: "Women's Collection",
    price: 210.00,
    compareAtPrice: 260.00,
    rating: 4.92,
    reviewCount: 77,
    badge: "Iconic",
    shortDescription: "Heavyweight 22-momme pure mulberry silk cut on the bias to cascade with effortless fluidity. Delicate adjustable straps.",
    fullDescription: "Designed for day-to-night versatility. Cut on the bias to gracefully follow the body's natural contours. Layer under a tailored merino blazer for structured poise, or wear solo with heels for an ethereal evening presence.",
    details: [
      "100% 22-Momme Pure Mulberry Silk",
      "Precision bias cut for liquid drape",
      "French seams and delicate adjustable straps",
      "Midi length with subtle side slit",
      "Dry clean or cold hand wash with silk wash"
    ],
    colors: [
      { name: "Champagne Pearl", hex: "#f4ede4", selected: true },
      { name: "Emerald Green", hex: "#0f5257", selected: false },
      { name: "Onyx Black", hex: "#111111", selected: false }
    ],
    sizes: ["S", "M", "L", "XL"],
    defaultSize: "M",
    inventoryRemaining: 6,
    images: [
      {
        url: "media/photo-1595777457583-95e059d581b8.jpg",
        alt: "The Bias-Cut Mulberry Silk Slip Dress - Elegance"
      },
      {
        url: "media/photo-1539109136881-3be0616acf4b.jpg",
        alt: "The Bias-Cut Mulberry Silk Slip Dress - Movement"
      }
    ]
  },
  "leather-duffle": {
    id: "leather-duffle",
    sku: "KC-ACC-033",
    title: "The Heritage Full-Grain Leather Duffle",
    category: "accessories",
    categoryLabel: "Accessories & Leather",
    price: 320.00,
    compareAtPrice: 380.00,
    rating: 4.98,
    reviewCount: 110,
    badge: "Heritage",
    shortDescription: "Handcrafted from vegetable-tanned Italian leather with antiqued solid brass hardware. Meets international airline carry-on specs.",
    fullDescription: "An heirloom travel companion engineered for the discerning voyager. The Tuscan vegetable-tanned full-grain leather will develop a rich, luminous patina unique to your journeys. Includes a water-resistant canvas lining and padded laptop sleeve.",
    details: [
      "Tuscan Full-Grain Vegetable Tanned Cowhide",
      "Solid cast antiqued brass hardware and YKK Excella zippers",
      "Water-repellent 12oz waxed cotton canvas interior lining",
      "Detachable ergonomic leather shoulder strap with shoulder pad",
      "Dimensions: 21\" L x 11\" W x 12\" H (Airline carry-on approved)"
    ],
    colors: [
      { name: "Cognac Tan", hex: "#8d4925", selected: true },
      { name: "Dark Walnut", hex: "#4a2c11", selected: false },
      { name: "Matte Black", hex: "#1a1a1a", selected: false }
    ],
    sizes: ["One Size"],
    defaultSize: "One Size",
    inventoryRemaining: 2,
    images: [
      {
        url: "media/photo-1553062407-98eeb64c6a62.jpg",
        alt: "The Heritage Full-Grain Leather Duffle - Profile"
      },
      {
        url: "media/photo-1548036328-c9fa89d128fa.jpg",
        alt: "The Heritage Full-Grain Leather Duffle - Travel Ready"
      }
    ]
  }
};

window.__AI_SALES_CONFIG = {
  ...window.__AI_SALES_CONFIG,
  catalog: Object.values(STORE_CATALOG).map(p => ({
    id: p.id, title: p.title, description: p.shortDescription, price: p.price,
    image: new URL(p.images[0].url, location.href).href, sizes: p.sizes,
    url: new URL('product.html?id=' + encodeURIComponent(p.id), location.href).href
  }))
};

// Global Store State & Cart helpers
function readBag() {
  try {
    const items = JSON.parse(localStorage.getItem('karthik_co_cart') || '[]');
    return Array.isArray(items) ? items.filter(i => i && typeof i.title === 'string' &&
      Number.isFinite(i.price) && Number.isInteger(i.quantity) && i.quantity > 0) : [];
  } catch {
    return [];
  }
}

window.StoreApp = {
  cart: readBag(),

  openBag() {
    const dialog = document.createElement('dialog');
    dialog.className = 'bag-panel';
    dialog.setAttribute('aria-label', 'Shopping bag');
    const title = document.createElement('h2');
    title.textContent = 'Your bag';
    dialog.append(title);
    for (const item of this.cart) {
      const line = document.createElement('p');
      const name = document.createElement('strong');
      name.textContent = item.title;
      line.append(name, document.createElement('br'), `${item.color} · ${item.size} · Qty ${item.quantity} · $${(item.price * item.quantity).toFixed(2)}`);
      const remove = document.createElement('button');
      remove.className = 'bag-remove';
      remove.textContent = 'Remove';
      remove.setAttribute('aria-label', `Remove ${item.title}, ${item.size}, ${item.color}`);
      remove.onclick = () => {
        this.cart = this.cart.filter(entry => entry !== item);
        this.saveBag();
        dialog.close();
        this.openBag();
      };
      line.append(document.createElement('br'), remove);
      dialog.append(line);
    }
    const summary = document.createElement('p');
    const total = this.cart.reduce((sum, item) => sum + item.quantity * item.price, 0);
    summary.textContent = this.cart.length ? `Subtotal  $${total.toFixed(2)}` : 'Your shopping bag is empty.';
    const close = document.createElement('button');
    close.textContent = 'Continue shopping';
    close.onclick = () => dialog.close();
    dialog.append(summary, close);
    dialog.addEventListener('close', () => dialog.remove(), { once: true });
    document.body.append(dialog);
    dialog.showModal();
  },

  getCartCount() {
    return this.cart.reduce((sum, item) => sum + (item.quantity || 1), 0);
  },

  updateCartBadges() {
    const count = this.getCartCount();
    document.querySelectorAll('.cart-count-badge').forEach(badge => {
      badge.textContent = count;
      badge.style.display = count > 0 ? 'inline-flex' : 'none';
    });
  },

  addToCart(product, selectedColor, selectedSize) {
    const existingIndex = this.cart.findIndex(
      item => item.id === product.id && item.color === selectedColor && item.size === selectedSize
    );
    if (existingIndex > -1) {
      this.cart[existingIndex].quantity = (this.cart[existingIndex].quantity || 1) + 1;
    } else {
      this.cart.push({
        id: product.id,
        title: product.title,
        price: product.price,
        color: selectedColor,
        size: selectedSize,
        image: product.images[0].url,
        quantity: 1
      });
    }
    this.saveBag();
    this.showToast(`Added to Bag: ${product.title} (${selectedSize} / ${selectedColor})`);
  },

  saveBag() {
    try { localStorage.setItem('karthik_co_cart', JSON.stringify(this.cart)); } catch { /* Keep the bag available for this visit. */ }
    this.updateCartBadges();
  },

  showToast(message, type = 'success') {
    let container = document.getElementById('store-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'store-toast-container';
      container.style.cssText = `
        position: fixed;
        bottom: 28px;
        left: 28px;
        z-index: 99999;
        display: flex;
        flex-direction: column;
        gap: 10px;
        pointer-events: none;
      `;
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'store-toast';
    toast.style.cssText = `
      background: #111827;
      color: #ffffff;
      padding: 14px 20px;
      border-radius: 8px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 14px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.25);
      border-left: 4px solid #d4af37;
      display: flex;
      align-items: center;
      gap: 12px;
      animation: toastSlideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      pointer-events: auto;
      max-width: 360px;
    `;
    toast.innerHTML = `
      <span style="font-size: 18px;">🛍️</span>
      <div style="flex: 1;">
        <div style="font-weight: 600; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; color: #d4af37; margin-bottom: 2px;">Karthik & Co. Cart</div>
        <div style="color: #e5e7eb; font-size: 13px; line-height: 1.4;" class="toast-message"></div>
      </div>
    `;

    toast.querySelector('.toast-message').textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 350);
    }, 3200);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  window.StoreApp.updateCartBadges();
  document.getElementById('header-cart-btn')?.addEventListener('click', () => window.StoreApp.openBag());
});
