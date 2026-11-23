/**
 * AI Sales Associate - DOM Extractor
 * Platform-agnostic product parser reading schema.org application/ld+json,
 * OpenGraph tags, and page meta via requestIdleCallback.
 * Zero impact on Core Web Vitals (LCP, FID/INP, CLS).
 */

(function (window, document) {
  'use strict';

  if (window.__AISalesAssociateDOMExtractor) {
    return;
  }

  const shield = window.__AISalesAssociateShield || {
    executeSafe: (fn, fallback) => {
      try { return fn(); } catch (e) { return fallback; }
    }
  };

  class DOMExtractor {
    constructor() {
      this.cachedProduct = null;
      this.listeners = [];
      this.observer = null;
      this.setupVariantListeners();
    }

    /**
     * Platform-agnostic product extraction scheduled during browser idle periods.
     */
    extract(callback) {
      const scheduleIdle = window.requestIdleCallback || ((cb) => setTimeout(() => cb({ timeRemaining: () => 15 }), 50));

      scheduleIdle(() => {
        shield.executeSafe(() => {
          const product = this._performExtraction();
          this.cachedProduct = product;
          if (typeof callback === 'function') {
            callback(product);
          }
          this._notifyListeners(product);
        });
      }, { timeout: 2000 });
    }

    getCachedProduct() {
      if (!this.cachedProduct) {
        this.cachedProduct = this._performExtraction();
      }
      return this.cachedProduct;
    }

    onProductChange(fn) {
      if (typeof fn === 'function') {
        this.listeners.push(fn);
      }
    }

    _notifyListeners(product) {
      for (const fn of this.listeners) {
        shield.executeSafe(() => fn(product));
      }
    }

    _performExtraction() {
      const jsonLd = this._extractJsonLd();
      const meta = this._extractMetaTags();
      const dom = this._extractDOMHeuristics();

      const title = jsonLd.title || meta.title || dom.title || document.title || 'Featured Apparel';
      const price = jsonLd.price || meta.price || dom.price || '';
      const currency = jsonLd.currency || meta.currency || dom.currency || '$';
      const image = jsonLd.image || meta.image || dom.image || '';
      const description = jsonLd.description || meta.description || dom.description || '';
      const material = jsonLd.material || dom.material || '';
      const brand = jsonLd.brand || meta.brand || dom.brand || (typeof window !== 'undefined' && window.Shopify && window.Shopify.shop) || '';
      const sku = jsonLd.sku || dom.sku || '';
      const availability = jsonLd.availability || dom.availability || 'InStock';

      const loc = typeof window !== 'undefined' && window.location ? window.location : { pathname: '', href: '' };

      const isProductPage = Boolean(
        jsonLd.isProduct ||
        meta.isProduct ||
        dom.isProduct ||
        document.querySelector('[itemtype*="Product"]') ||
        loc.pathname.includes('/product') ||
        document.querySelector('#add-to-cart, .add-to-cart, button[name="add"]')
      );

      const variants = dom.variants || { sizes: [], colors: [] };
      const selectedVariant = dom.selectedVariant || { size: '', color: '' };
      const ctaButtons = dom.ctaButtons || {};
      const measurements = this._extractMeasurementTable();
      const customerIdentity = this.extractCustomerIdentity();

      return {
        isProductPage,
        id: sku || title.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 32),
        name: this._cleanText(title),
        title: this._cleanText(title),
        price: this._cleanPrice(price),
        currency: currency.replace(/USD/i, '$'),
        description: this._cleanText(description),
        material: this._cleanText(material),
        image,
        brand: this._cleanText(brand),
        sku,
        availability,
        variants,
        sizes: variants.sizes || [],
        colors: variants.colors || [],
        selectedVariant,
        ctaButtons,
        measurements,
        sizeChart: measurements,
        customerIdentity,
        url: loc.href
      };
    }

    _extractJsonLd() {
      const result = { isProduct: false };
      try {
        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
        for (const script of scripts) {
          try {
            const raw = JSON.parse(script.textContent || '{}');
            const items = Array.isArray(raw) ? raw : (raw['@graph'] ? raw['@graph'] : [raw]);

            for (const item of items) {
              if (item && (item['@type'] === 'Product' || item['@type'] === 'IndividualProduct')) {
                result.isProduct = true;
                result.title = item.name;
                result.description = item.description;
                result.sku = item.sku || item.productID;

                if (item.image) {
                  result.image = Array.isArray(item.image)
                    ? (typeof item.image[0] === 'string' ? item.image[0] : item.image[0]?.url)
                    : (typeof item.image === 'string' ? item.image : item.image?.url);
                }

                if (item.brand) {
                  result.brand = typeof item.brand === 'string' ? item.brand : item.brand.name;
                }

                if (item.offers) {
                  const offer = Array.isArray(item.offers) ? item.offers[0] : item.offers;
                  if (offer) {
                    result.price = offer.price || offer.lowPrice;
                    result.currency = offer.priceCurrency || '$';
                    result.availability = offer.availability ? offer.availability.split('/').pop() : 'InStock';
                  }
                }
                return result;
              }
            }
          } catch (e) {
            // Ignore individual invalid JSON-LD script blocks
          }
        }
      } catch (e) {
        // Ignore
      }
      return result;
    }

    _extractMetaTags() {
      const getMeta = (props) => {
        for (const prop of props) {
          const el = document.querySelector(`meta[property="${prop}"], meta[name="${prop}"]`);
          if (el && el.content) return el.content.trim();
        }
        return null;
      };

      const ogType = getMeta(['og:type']);
      const isProduct = ogType === 'product' || ogType === 'og:product';

      return {
        isProduct,
        title: getMeta(['og:title', 'twitter:title']),
        description: getMeta(['og:description', 'twitter:description', 'description']),
        image: getMeta(['og:image', 'twitter:image', 'image']),
        price: getMeta(['product:price:amount', 'og:price:amount']),
        currency: getMeta(['product:price:currency', 'og:price:currency']),
        brand: getMeta(['product:brand', 'og:site_name'])
      };
    }

    _extractDOMHeuristics() {
      const dom = {
        isProduct: false,
        variants: { sizes: [], colors: [] },
        selectedVariant: { size: '', color: '' },
        ctaButtons: {}
      };

      // Title detection
      const titleEl = document.querySelector('h1.product-title, h1[itemprop="name"], .product-single__title, .product-detail-title, h1');
      if (titleEl) {
        dom.title = titleEl.textContent;
      }

      // Price detection
      const priceEl = document.querySelector('[itemprop="price"], .product-price, .current-price, .price, .product-single__price');
      if (priceEl) {
        dom.price = priceEl.getAttribute('content') || priceEl.textContent;
      }

      // Image detection
      const imageEl = document.querySelector('img[itemprop="image"], .product-image img, .product-featured-image, .main-product-img');
      if (imageEl) {
        dom.image = imageEl.src || imageEl.getAttribute('data-src');
      }

      // Description
      const descEl = document.querySelector('[itemprop="description"], .product-description, .product-detail-description');
      if (descEl) {
        dom.description = descEl.textContent;
      }

      // Material detection
      const materialEl = document.querySelector('[itemprop="material"], .product-material, #acc-body-fabric, #pdp-bullet-points');
      if (materialEl) {
        const text = materialEl.textContent || '';
        const match = text.match(/\b(100%[^\n,.]*|merino wool|wool|linen|cotton|silk|cashmere|leather)[^,.\n]*/i);
        if (match) {
          dom.material = match[0].trim();
        }
      }

      // CTAs
      const addToCartEl = document.querySelector('#add-to-cart, #add-to-cart-btn, .add-to-cart, button[name="add"], .btn-add-to-cart, [data-action="add-to-cart"]');
      if (addToCartEl) {
        dom.isProduct = true;
        dom.ctaButtons.addToCart = addToCartEl.id ? `#${addToCartEl.id}` : '.add-to-cart';
      }

      const buyNowEl = document.querySelector('#buy-now, #buy-now-btn, .buy-now, button[data-action="buy-now"], .shopify-payment-button');
      if (buyNowEl) {
        dom.ctaButtons.buyNow = buyNowEl.id ? `#${buyNowEl.id}` : '.buy-now';
      }

      // Variant detection (Size buttons, swatches, radio inputs, and <select> dropdowns)
      const sizeElements = document.querySelectorAll('.size-option, .size-btn, [data-variant-type="size"], input[name*="size" i], button[data-size]');
      if (sizeElements.length > 0) {
        dom.isProduct = true;
        sizeElements.forEach((el) => {
          const val = el.textContent?.trim() || el.value || el.getAttribute('data-size');
          if (val && !dom.variants.sizes.includes(val)) {
            dom.variants.sizes.push(val);
          }
          if (el.classList.contains('active') || el.classList.contains('selected') || el.checked || el.getAttribute('aria-selected') === 'true') {
            dom.selectedVariant.size = val;
          }
        });
      }

      // Check for <select> size dropdowns (Shopify, WooCommerce, Magento, etc.)
      const sizeSelects = document.querySelectorAll('select[name*="size" i], select#size, select[id*="size" i], select[name="id"]');
      sizeSelects.forEach((sel) => {
        dom.isProduct = true;
        Array.from(sel.options || []).forEach((opt) => {
          const val = (opt.text || opt.value || '').trim();
          if (val && !dom.variants.sizes.includes(val) && !val.toLowerCase().includes('select size') && !val.toLowerCase().includes('choose')) {
            dom.variants.sizes.push(val);
          }
          if (opt.selected && val && !val.toLowerCase().includes('select size')) {
            dom.selectedVariant.size = val;
          }
        });
      });

      const colorElements = document.querySelectorAll('.color-swatch, .color-btn, [data-variant-type="color"], input[name*="color" i], button[data-color]');
      if (colorElements.length > 0) {
        dom.isProduct = true;
        colorElements.forEach((el) => {
          const val = el.getAttribute('title') || el.getAttribute('data-color') || el.value || el.textContent?.trim();
          if (val && !dom.variants.colors.includes(val)) {
            dom.variants.colors.push(val);
          }
          if (el.classList.contains('active') || el.classList.contains('selected') || el.checked) {
            dom.selectedVariant.color = val;
          }
        });
      }

      const colorSelects = document.querySelectorAll('select[name*="color" i], select#color, select[id*="color" i]');
      colorSelects.forEach((sel) => {
        dom.isProduct = true;
        Array.from(sel.options || []).forEach((opt) => {
          const val = (opt.text || opt.value || '').trim();
          if (val && !dom.variants.colors.includes(val) && !val.toLowerCase().includes('select color')) {
            dom.variants.colors.push(val);
          }
          if (opt.selected && val) {
            dom.selectedVariant.color = val;
          }
        });
      });

      return dom;
    }

    setupVariantListeners() {
      // Listen for click/change on variant toggles to keep cached state fresh
      document.addEventListener('click', (e) => {
        const target = e.target.closest('.size-option, .size-btn, button[data-size], .color-swatch, button[data-color]');
        if (target) {
          // Debounce re-extraction
          setTimeout(() => {
            this.extract();
          }, 100);
        }
      }, { passive: true });
    }

    /**
     * Shopper Identity Extraction (China/Korea precision tracking).
     * Extracts persistent shopper UUID from localStorage, merchant customerId from
     * Shopify/ShopifyAnalytics/dataLayers, and login state.
     */
    extractCustomerIdentity() {
      let customerId = null;
      let email = null;
      let shopperUuid = null;

      // 1. Merchant config explicit customer identity
      try {
        if (typeof window !== 'undefined' && window.__AI_SALES_CONFIG) {
          customerId = window.__AI_SALES_CONFIG.customerId || window.__AI_SALES_CONFIG.customer_id || null;
          email = window.__AI_SALES_CONFIG.customerEmail || window.__AI_SALES_CONFIG.customer_email || null;
        }
      } catch (e) {}

      // 2. Session memory cached customer identity
      try {
        if (typeof window !== 'undefined' && window.__AISalesAssociateSessionMemory?.getCustomerIdentity) {
          const cached = window.__AISalesAssociateSessionMemory.getCustomerIdentity();
          if (cached) {
            if (!customerId && cached.customerId) customerId = cached.customerId;
            if (!email && cached.email) email = cached.email;
          }
        }
      } catch (e) {}

      // 3. Cross-session persistent shopper UUID in localStorage
      try {
        const STORAGE_KEY = '__ai_sales_shopper_uuid';
        if (typeof window !== 'undefined' && window.localStorage) {
          shopperUuid = window.localStorage.getItem(STORAGE_KEY);
          if (!shopperUuid) {
            if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
              shopperUuid = crypto.randomUUID();
            } else {
              shopperUuid = 'shopper-' + Date.now() + '-' + Math.random().toString(36).substring(2, 10);
            }
            window.localStorage.setItem(STORAGE_KEY, shopperUuid);
          }
        }
      } catch (e) {
        shopperUuid = shopperUuid || 'anon-shopper-' + Math.random().toString(36).substring(2, 10);
      }

      // 4. Shopify Analytics / page metadata
      try {
        if (typeof window !== 'undefined') {
          if (window.ShopifyAnalytics?.meta?.page?.customerId) {
            customerId = String(window.ShopifyAnalytics.meta.page.customerId);
          } else if (window.__st?.cid) {
            customerId = String(window.__st.cid);
          } else if (window.meta?.page?.customerId) {
            customerId = String(window.meta.page.customerId);
          } else if (window.Shopify?.checkout?.customer_id) {
            customerId = String(window.Shopify.checkout.customer_id);
          }
        }
      } catch (e) {}

      // 5. Google Tag Manager / Segment dataLayer inspection
      try {
        if (typeof window !== 'undefined' && Array.isArray(window.dataLayer)) {
          for (const entry of window.dataLayer) {
            if (!entry || typeof entry !== 'object') continue;
            if (!customerId) {
              const id = entry.userId || entry.user_id || entry.customerId || entry.customer_id || entry.ecommerce?.customer_id;
              if (id) customerId = String(id);
            }
            if (!email) {
              const em = entry.userEmail || entry.user_email || entry.email;
              if (em) email = String(em);
            }
          }
        }
      } catch (e) {}

      const identity = {
        customerId: customerId || null,
        shopperUuid: shopperUuid,
        email: email || null,
        isLoggedIn: Boolean(customerId)
      };

      if (typeof window !== 'undefined' && window.__AISalesAssociateSessionMemory?.setCustomerIdentity) {
        try { window.__AISalesAssociateSessionMemory.setCustomerIdentity(identity); } catch (e) {}
      }

      return identity;
    }

    /**
     * Enhanced precision sizing extraction detecting measurement tables
     * (chest, waist, length in cm/inches, plus footwear sizes) from PDP tables.
     */
    _extractMeasurementTable() {
      try {
        const keywords = [
          'chest', 'bust', 'waist', 'hip', 'length', 'shoulder', 'sleeve', 'inseam',
          'cm', 'inch', 'inches', 'eu', 'uk', 'us', 'jp', 'foot', 'insole', 'size', 'height', 'weight', 'width'
        ];
        const tables = document.querySelectorAll('table, .size-guide table, .size-chart table');
        for (const table of tables) {
          const text = (table.textContent || '').toLowerCase();
          const matches = keywords.filter(k => text.includes(k));
          if (matches.length < 2) continue;

          // Select closest header row to data (last thead row if multiple thead rows exist)
          const headerRow = table.querySelector('thead tr:last-child') || table.querySelector('tr:first-child');
          const headers = [];
          if (headerRow) {
            const ths = headerRow.querySelectorAll('th, td');
            ths.forEach(h => {
              const val = (h.textContent || '').trim();
              if (val) headers.push(val);
            });
          }

          const rows = [];
          const trs = table.querySelectorAll('tbody tr, tr:not(:first-child)');
          trs.forEach(tr => {
            if (tr === headerRow) return;
            const cells = tr.querySelectorAll('td, th');
            if (cells.length > 0) {
              const rowObj = {};
              cells.forEach((c, idx) => {
                const colName = headers[idx] || `col_${idx}`;
                rowObj[colName] = (c.textContent || '').trim();
              });
              rows.push(rowObj);
            }
          });

          if (rows.length > 0) {
            const summary = rows.slice(0, 6).map(r => Object.entries(r).map(([k, v]) => `${k}: ${v}`).join(', ')).join(' | ');
            return {
              headers,
              rows: rows.slice(0, 10),
              summary
            };
          }
        }
      } catch (e) {}
      return null;
    }

    /**
     * Autonomous native store search detection:
     * - Queries Shopify /search/suggest.json?q={query}&resources[type]=product
     * - Queries WooCommerce Store API /wp-json/wc/store/v1/products or /?s={query}&post_type=product
     * - Or accepts dynamic store products via custom search provider
     */
    async searchNativeStore(query) {
      if (!query || typeof query !== 'string') return [];
      const clean = query.trim();
      if (!clean) return [];

      // Avoid unnecessary requests on pure conversational chit-chat
      const lower = clean.toLowerCase();
      const skipPhrases = ['hi', 'hello', 'hey', 'good morning', 'good evening', 'who are you', 'what is your name', 'yes', 'no', 'ok', 'okay', 'check my size'];
      if (skipPhrases.includes(lower)) return [];

      const toAbsoluteUrl = (u) => {
        if (!u) return '';
        try {
          return (typeof window !== 'undefined' && window.location) ? new URL(u, window.location.origin).href : u;
        } catch (e) {
          return u;
        }
      };

      // 1. Dynamic custom search provider hook if supplied by merchant
      if (typeof window !== 'undefined') {
        const customFn = window.__AI_SALES_SEARCH_FN || (window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.searchProducts);
        if (typeof customFn === 'function') {
          try {
            const results = await customFn(clean);
            if (Array.isArray(results) && results.length > 0) return results;
          } catch (e) {}
        }
      }

      // 2. Shopify Native Suggest API Detection
      const isShopify = typeof window !== 'undefined' && Boolean(
        window.Shopify ||
        document.querySelector('link[href*="cdn.shopify.com"]') ||
        document.querySelector('script[src*="cdn.shopify.com"]') ||
        document.querySelector('meta[name="shopify-checkout-api-token"]')
      );

      if (isShopify) {
        try {
          const url = `/search/suggest.json?q=${encodeURIComponent(clean)}&resources[type]=product&resources[limit]=5`;
          const res = await fetch(url, {
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin'
          });
          if (res.ok) {
            const data = await res.json();
            const products = data?.resources?.results?.products;
            if (Array.isArray(products) && products.length > 0) {
              return products.map(p => ({
                id: String(p.id || p.handle || p.title),
                title: p.title || p.name,
                name: p.title || p.name,
                price: p.price || (p.price_min ? (p.price_min / 100).toFixed(2) : ''),
                url: toAbsoluteUrl(p.url),
                image: p.image || p.featured_image?.url || (p.images && p.images[0]) || '',
                description: (p.body || p.description || '').replace(/<[^>]*>/g, '').slice(0, 160),
                in_stock: p.available !== false
              }));
            }
          }
        } catch (e) {}
      }

      // 3. WooCommerce Native Search Detection (Store API + Fallback)
      const isWooCommerce = typeof window !== 'undefined' && Boolean(
        window.wc_add_to_cart_params ||
        document.body?.classList?.contains('woocommerce') ||
        document.querySelector('link[href*="woocommerce"]')
      );

      if (isWooCommerce) {
        // Try modern Store API first
        try {
          const storeApiUrl = `/wp-json/wc/store/v1/products?search=${encodeURIComponent(clean)}&per_page=5`;
          const res = await fetch(storeApiUrl, {
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin'
          });
          if (res.ok) {
            const data = await res.json();
            if (Array.isArray(data) && data.length > 0) {
              return data.slice(0, 5).map(p => ({
                id: String(p.id || p.slug || p.name),
                title: p.name || p.title,
                name: p.name || p.title,
                price: p.prices?.price ? (Number(p.prices.price) / 100).toFixed(2) : (p.price || ''),
                url: toAbsoluteUrl(p.permalink || p.url),
                image: (p.images && p.images[0]?.src) || '',
                description: (p.short_description || p.description || '').replace(/<[^>]*>/g, '').slice(0, 160),
                in_stock: p.is_in_stock !== false
              }));
            }
          }
        } catch (e) {}

        // Fallback to legacy WooCommerce JSON search endpoint
        try {
          const url = `/?s=${encodeURIComponent(clean)}&post_type=product&json=1`;
          const res = await fetch(url, {
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin'
          });
          if (res.ok) {
            const data = await res.json();
            if (Array.isArray(data) && data.length > 0) {
              return data.slice(0, 5).map(p => ({
                id: String(p.id || p.slug || p.title),
                title: p.title || p.name,
                name: p.title || p.name,
                price: p.price || p.regular_price || '',
                url: toAbsoluteUrl(p.permalink || p.url),
                image: p.image_url || (p.images && p.images[0]?.src) || '',
                description: (p.short_description || p.description || '').replace(/<[^>]*>/g, '').slice(0, 160),
                in_stock: p.is_in_stock !== false
              }));
            }
          }
        } catch (e) {}
      }

      return [];
    }

    _cleanText(str) {
      if (!str) return '';
      return String(str).replace(/\s+/g, ' ').trim();
    }

    _cleanPrice(str) {
      if (!str) return '';
      const match = String(str).replace(/,/g, '').match(/\d+(\.\d{1,2})?/);
      return match ? match[0] : String(str).trim();
    }
  }

  const extractorInstance = new DOMExtractor();

  window.__AISalesAssociateDOMExtractor = {
    instance: extractorInstance,
    extract: (cb) => extractorInstance.extract(cb),
    getCachedProduct: () => extractorInstance.getCachedProduct(),
    onProductChange: (fn) => extractorInstance.onProductChange(fn),
    extractCustomerIdentity: () => extractorInstance.extractCustomerIdentity(),
    searchNativeStore: (query) => extractorInstance.searchNativeStore(query)
  };
})(window, document);
