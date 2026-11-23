/**
 * AI Sales Associate - Widget Component
 * Zero-CLS fixed viewport closed Shadow DOM Web Component.
 * Features:
 * - Constructable stylesheets with fallback
 * - Floating stylist pill with live status
 * - Proactive contextual speech bubble
 * - Chat drawer with SSE streaming support
 * - Quick-reply pills
 * - Product recommendation card with "Hero" validation badge
 * - 'View & Buy' button with native smooth scroll and spotlight effect
 * - Zero Core Web Vitals impact (CLS = 0.000)
 */

(function (window, document) {
  'use strict';

  if (window.__AISalesAssociateWidget) {
    return;
  }

  const shield = window.__AISalesAssociateShield || {
    executeSafe: (fn) => { try { return fn(); } catch (e) {} },
    wrap: (fn) => fn
  };

  const STYLES = `
    :host {
      --ai-primary: #522331;
      --ai-primary-hover: #302427;
      --ai-accent: #82534d;
      --ai-accent-gold: #915348;
      --ai-text-main: #302427;
      --ai-text-muted: #665c58;
      --ai-bg-card: #ffffff;
      --ai-bg-bubble-stylist: #f5f0e8;
      --ai-bg-bubble-user: #522331;
      --ai-border: #e1d8cf;
      --ai-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
      --ai-shadow-bubble: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);

      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 2147483640;
      pointer-events: none;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: var(--ai-text-main);
      box-sizing: border-box;
      -webkit-font-smoothing: antialiased;
    }

    *, *::before, *::after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    .widget-container {
      position: relative;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      pointer-events: none;
    }

    /* Floating Stylist Pill */
    .stylist-pill {
      pointer-events: auto;
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 10px 18px 10px 12px;
      background: var(--ai-primary);
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 9999px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.25);
      cursor: pointer;
      user-select: none;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .stylist-pill:hover {
      background: var(--ai-primary-hover);
      transform: translateY(-2px);
      box-shadow: 0 12px 28px rgba(15, 23, 42, 0.35);
    }

    .pill-avatar-wrap {
      position: relative;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: #764452;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.3);
    }

    .pill-avatar-svg {
      width: 18px;
      height: 18px;
      fill: none;
      stroke: #ffffff;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .status-beacon {
      position: absolute;
      bottom: -1px;
      right: -1px;
      width: 9px;
      height: 9px;
      background: var(--ai-accent);
      border: 2px solid var(--ai-primary);
      border-radius: 50%;
    }

    .status-beacon-pulse {
      position: absolute;
      bottom: -1px;
      right: -1px;
      width: 9px;
      height: 9px;
      background: var(--ai-accent);
      border-radius: 50%;
      animation: pulse-ring 2s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
    }

    @keyframes pulse-ring {
      0% { transform: scale(0.95); opacity: 0.8; }
      50% { transform: scale(2.2); opacity: 0; }
      100% { transform: scale(2.2); opacity: 0; }
    }

    .pill-text {
      display: flex;
      flex-direction: column;
    }

    .pill-title {
      font-size: 13px;
      font-weight: 600;
      letter-spacing: -0.01em;
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .sparkle-icon {
      color: #fcd34d;
    }

    .pill-subtitle {
      font-size: 11px;
      color: #94a3b8;
      font-weight: 400;
    }

    /* Proactive Speech Bubble */
    .speech-bubble {
      pointer-events: auto;
      max-width: 320px;
      margin-bottom: 12px;
      background: #ffffff;
      border: 1px solid var(--ai-border);
      border-radius: 16px;
      padding: 14px 16px;
      box-shadow: var(--ai-shadow-bubble);
      animation: slide-up 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      display: none;
      position: relative;
    }

    .speech-bubble.visible {
      display: block;
    }

    @keyframes slide-up {
      from { opacity: 0; transform: translateY(10px) scale(0.96); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    .bubble-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    }

    .bubble-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #0284c7;
      background: #e0f2fe;
      padding: 2px 8px;
      border-radius: 10px;
    }

    .bubble-close {
      background: transparent;
      border: none;
      color: #94a3b8;
      cursor: pointer;
      font-size: 16px;
      line-height: 1;
      padding: 2px;
      border-radius: 4px;
    }

    .bubble-close:hover {
      color: #475569;
    }

    .bubble-message {
      font-size: 13px;
      color: #334155;
      line-height: 1.45;
      margin-bottom: 10px;
    }

    .bubble-actions {
      display: flex;
      gap: 8px;
    }

    .bubble-btn-action {
      background: var(--ai-primary);
      color: #ffffff;
      border: none;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.15s ease;
    }

    .bubble-btn-action:hover {
      background: var(--ai-primary-hover);
    }

    /* Chat Drawer */
    .chat-drawer {
      pointer-events: auto;
      width: 380px;
      height: 580px;
      max-width: calc(100vw - 32px);
      max-height: calc(100vh - 100px);
      background: #ffffff;
      border: 1px solid var(--ai-border);
      border-radius: 20px;
      box-shadow: 0 25px 50px -12px rgba(15, 23, 42, 0.25);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      margin-bottom: 14px;
      opacity: 0;
      transform: translateY(16px) scale(0.97);
      transition: all 0.28s cubic-bezier(0.16, 1, 0.3, 1);
      display: none;
    }

    .chat-drawer.open {
      display: flex;
      opacity: 1;
      transform: translateY(0) scale(1);
    }

    .drawer-header {
      background: var(--ai-primary);
      color: #ffffff;
      padding: 14px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    .drawer-header-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .drawer-avatar {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: #764452;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }

    .drawer-avatar svg {
      width: 20px;
      height: 20px;
      fill: none;
      stroke: #ffffff;
      stroke-width: 2;
    }

    .drawer-avatar-beacon {
      position: absolute;
      bottom: 0;
      right: 0;
      width: 9px;
      height: 9px;
      background: #82534d;
      border: 2px solid var(--ai-primary);
      border-radius: 50%;
    }

    .drawer-info-title {
      font-size: 14px;
      font-weight: 600;
      letter-spacing: -0.01em;
    }

    .drawer-info-status {
      font-size: 11px;
      color: #94a3b8;
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .drawer-header-actions {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .drawer-btn-icon {
      background: transparent;
      border: none;
      color: #cbd5e1;
      width: 28px;
      height: 28px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease;
    }

    .drawer-btn-icon:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #ffffff;
    }

    /* Message Thread */
    .message-thread {
      flex: 1;
      padding: 16px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 14px;
      background: #fafaf9;
    }

    .message-thread::-webkit-scrollbar {
      width: 6px;
    }
    .message-thread::-webkit-scrollbar-thumb {
      background: #d6d3d1;
      border-radius: 3px;
    }

    .message-row {
      display: flex;
      gap: 10px;
      max-width: 88%;
    }

    .message-row.stylist {
      align-self: flex-start;
    }

    .message-row.user {
      align-self: flex-end;
      flex-direction: row-reverse;
    }

    .message-avatar {
      width: 26px;
      height: 26px;
      border-radius: 50%;
      background: #764452;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      margin-top: 4px;
    }

    .message-avatar svg {
      width: 14px;
      height: 14px;
      fill: none;
      stroke: #ffffff;
      stroke-width: 2;
    }

    .message-bubble {
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 13.5px;
      line-height: 1.45;
      word-break: break-word;
    }

    .message-row.stylist .message-bubble {
      background: #ffffff;
      color: #522331;
      border: 1px solid #e1d8cf;
      border-top-left-radius: 4px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }

    .message-row.user .message-bubble {
      background: var(--ai-primary);
      color: #ffffff;
      border-top-right-radius: 4px;
    }

    /* Product Card in Chat */
    .product-card {
      margin-top: 10px;
      background: #ffffff;
      border: 1px solid #e1d8cf;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
      transition: transform 0.2s ease;
    }

    .product-card:hover {
      transform: translateY(-2px);
    }

    .product-card-hero-badge {
      background: linear-gradient(90deg, #915348, #d97706);
      color: #ffffff;
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      display: flex;
      align-items: center;
      gap: 5px;
    }

    .product-card-body {
      padding: 12px;
      display: flex;
      gap: 12px;
    }

    .product-card-img {
      width: 64px;
      height: 64px;
      border-radius: 8px;
      object-fit: cover;
      background: #f5f0e8;
      flex-shrink: 0;
    }

    .product-card-details {
      display: flex;
      flex-direction: column;
      justify-content: center;
      flex: 1;
      min-width: 0;
    }

    .product-card-title {
      font-size: 13px;
      font-weight: 600;
      color: #302427;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 2px;
    }

    .product-card-price {
      font-size: 13px;
      font-weight: 700;
      color: #059669;
      margin-bottom: 4px;
    }

    .product-card-desc {
      font-size: 11px;
      color: #665c58;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .product-card-actions {
      padding: 8px 12px;
      background: #f8fafc;
      border-top: 1px solid #e1d8cf;
      display: flex;
      gap: 8px;
    }

    .btn-view-buy {
      flex: 1;
      background: #059669;
      color: #ffffff;
      border: none;
      padding: 7px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      transition: background 0.15s ease;
    }

    .btn-view-buy:hover {
      background: #047857;
    }

    /* Quick Reply Pills */
    .quick-replies-wrap {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 6px;
    }

    .quick-reply-pill {
      background: #ffffff;
      border: 1px solid #cbd5e1;
      color: #334155;
      font-size: 11.5px;
      font-weight: 500;
      padding: 5px 10px;
      border-radius: 9999px;
      cursor: pointer;
      transition: all 0.15s ease;
      white-space: nowrap;
    }

    .quick-reply-pill:hover {
      background: #f5f0e8;
      border-color: #94a3b8;
      color: #302427;
      transform: translateY(-1px);
    }

    /* Typing Indicator */
    .typing-indicator {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 8px 12px;
      background: #ffffff;
      border: 1px solid #e1d8cf;
      border-radius: 12px;
      border-top-left-radius: 4px;
    }

    .typing-dot {
      width: 6px;
      height: 6px;
      background: #94a3b8;
      border-radius: 50%;
      animation: typing-blink 1.4s infinite ease-in-out both;
    }

    .typing-dot:nth-child(1) { animation-delay: 0s; }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }

    @keyframes typing-blink {
      0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
      40% { transform: scale(1); opacity: 1; }
    }

    /* Input Footer */
    .drawer-footer {
      padding: 12px;
      background: #ffffff;
      border-top: 1px solid var(--ai-border);
    }

    .input-form {
      display: flex;
      align-items: center;
      gap: 8px;
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      border-radius: 12px;
      padding: 4px 6px 4px 12px;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    .input-form:focus-within {
      border-color: #3b82f6;
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12);
    }

    .chat-input {
      flex: 1;
      border: none;
      background: transparent;
      outline: none;
      font-size: 13.5px;
      color: #302427;
      padding: 6px 0;
      font-family: inherit;
    }

    .chat-input::placeholder {
      color: #94a3b8;
    }

    .btn-send {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: var(--ai-primary);
      color: #ffffff;
      border: none;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: background 0.15s ease;
      flex-shrink: 0;
    }

    .btn-send:hover {
      background: var(--ai-primary-hover);
    }

    .btn-send svg {
      width: 16px;
      height: 16px;
      fill: none;
      stroke: currentColor;
      stroke-width: 2;
    }

    .chat-drawer { width: 402px; height: 600px; border-radius: 12px; background: #fcf9f3; }
    .drawer-header { padding: 20px; }
    .drawer-info-title { font: normal 29px/1.12 Georgia, serif; letter-spacing: -.04em; }
    .drawer-info-status { color: #efdad4; }
    .message-thread { background: #fcf9f3; }
    .message-bubble { line-height: 1.55; }
    .drawer-footer { background: #fcf9f3; }
    .input-form { border-radius: 6px; }
    .stylist-pill { font: 600 14px/1.2 system-ui,sans-serif; padding: 10px 17px 10px 10px; }
    .pill-avatar-wrap, .drawer-avatar { background: #f5e2d5; color: #522331; font: italic 25px Georgia,serif; }
    .quick-reply-pill { color: #522331; background: #fffaf4; border-color: #c9aba8; }
    .product-card-hero-badge { background: #f1e6dc; color: #59303a; }
    .btn-view-buy, .btn-send { background: #522331; color: white; }
    :focus-visible { outline: 3px solid #af765c; outline-offset: 2px; }
    @media (max-width: 500px) {
      :host { bottom: max(12px,env(safe-area-inset-bottom)); right: 12px; }
      .chat-drawer { width: calc(100vw - 24px); max-width: none; max-height: calc(100dvh - 90px); }
      .message-thread { padding: 12px; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
    }
  `;

  class AISalesAssociateWidget extends HTMLElement {
    constructor() {
      super();
      this.backendUrl = 'http://localhost:8000';
      this.isOpen = false;
      this.isStreaming = false;
      this.currentProduct = null;
      this.hesitationTrigger = null;
      this.storeName = (typeof window !== 'undefined' && window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.storeName) || '';
      this.storeDomain = (typeof window !== 'undefined' && window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.storeDomain) || '';
      this.currency = (typeof window !== 'undefined' && window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.currency) || '$';
      this.brandTone = (typeof window !== 'undefined' && window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.brandTone) || '';
      this.shadow = this.attachShadow({ mode: 'closed' });
      this.initStyles();
      this.render();
      this.bindEvents();
    }

    connectedCallback() {
      shield.executeSafe(() => {
        this.restoreState();
        if (window.__AISalesAssociateShield) {
          window.__AISalesAssociateShield.registerUnmount(() => this.destroy());
        }
      });
    }

    initStyles() {
      if ('adoptedStyleSheets' in Document.prototype && 'replaceSync' in CSSStyleSheet.prototype) {
        const sheet = new CSSStyleSheet();
        sheet.replaceSync(STYLES);
        this.shadow.adoptedStyleSheets = [sheet];
      } else {
        const styleEl = document.createElement('style');
        styleEl.textContent = STYLES;
        this.shadow.appendChild(styleEl);
      }
    }

    render() {
      const container = document.createElement('div');
      container.className = 'widget-container';
      container.innerHTML = `
        <!-- Proactive Speech Bubble -->
        <div class="speech-bubble" id="speechBubble">
          <div class="bubble-header">
            <span class="bubble-badge">Styling advice</span>
            <button class="bubble-close" id="btnDismissBubble" aria-label="Dismiss">&times;</button>
          </div>
          <div class="bubble-message" id="bubbleMessage">Looking for styling advice or sizing confirmation? I'm here to help!</div>
          <div class="bubble-actions">
            <button class="bubble-btn-action" id="btnOpenFromBubble">Chat with Stylist</button>
          </div>
        </div>

        <!-- Chat Drawer -->
        <section class="chat-drawer" id="chatDrawer" aria-label="Styling assistant">
          <div class="drawer-header">
            <div class="drawer-header-left">
              <div class="drawer-avatar" aria-hidden="true">J</div>
              <div>
                <div class="drawer-info-title">Ask Julian</div>
                <div class="drawer-info-status">Personal AI stylist</div>
              </div>
            </div>
            <div class="drawer-header-actions">
              <button class="drawer-btn-icon" id="btnClose" aria-label="Close">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
          </div>

          <div class="message-thread" id="messageThread">
            <!-- Messages rendered dynamically -->
          </div>

          <div class="drawer-footer">
            <form class="input-form" id="chatForm">
              <input type="text" class="chat-input" id="chatInput" placeholder="Ask about fit, styling, or checkout..." autocomplete="off" />
              <button type="submit" class="btn-send" id="btnSend" aria-label="Send message">
                <svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
              </button>
            </form>
          </div>
        </section>

        <!-- Floating Stylist Pill -->
        <button type="button" class="stylist-pill" id="stylistPill" aria-expanded="false" aria-controls="chatDrawer">
          <span class="pill-avatar-wrap" aria-hidden="true">J</span>Ask Julian
        </button>
      `;

      this.shadow.appendChild(container);
    }

    bindEvents() {
      const pill = this.shadow.getElementById('stylistPill');
      const btnClose = this.shadow.getElementById('btnClose');
      const btnDismissBubble = this.shadow.getElementById('btnDismissBubble');
      const btnOpenFromBubble = this.shadow.getElementById('btnOpenFromBubble');
      const chatForm = this.shadow.getElementById('chatForm');
      const chatInput = this.shadow.getElementById('chatInput');

      pill.addEventListener('click', () => this.toggleDrawer());
      btnClose.addEventListener('click', () => this.closeDrawer());
      this.shadow.addEventListener('keydown', event => {
        if (event.key === 'Escape' && this.isOpen) this.closeDrawer();
      });
      btnDismissBubble.addEventListener('click', () => this.dismissBubble());
      btnOpenFromBubble.addEventListener('click', () => {
        this.dismissBubble();
        this.openDrawer();
      });

      if (chatInput) {
        chatInput.addEventListener('focus', () => this.pauseHesitation());
        chatInput.addEventListener('input', () => this.pauseHesitation());
      }

      chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const input = this.shadow.getElementById('chatInput');
        const text = input.value.trim();
        if (text && !this.isStreaming) {
          input.value = '';
          this.handleUserSend(text);
        }
      });
    }

    pauseHesitation() {
      if (this.hesitationMatrix && typeof this.hesitationMatrix.pause === 'function') {
        this.hesitationMatrix.pause();
      } else if (window.__AISalesAssociateHesitationMatrix?.instance?.pause) {
        window.__AISalesAssociateHesitationMatrix.instance.pause();
      }
    }

    resumeHesitation() {
      if (this.hesitationMatrix && typeof this.hesitationMatrix.resume === 'function') {
        this.hesitationMatrix.resume();
      } else if (window.__AISalesAssociateHesitationMatrix?.instance?.resume) {
        window.__AISalesAssociateHesitationMatrix.instance.resume();
      }
    }

    configure(options = {}) {
      if (options.backendUrl) {
        this.backendUrl = options.backendUrl.replace(/\/$/, '');
      }
      if (options.storeName) {
        this.storeName = options.storeName;
      }
      if (options.storeDomain) {
        this.storeDomain = options.storeDomain;
      }
      if (options.currency) {
        this.currency = options.currency;
      }
      if (options.brandTone) {
        this.brandTone = options.brandTone;
      }
      if (options.currentProduct) {
        this.currentProduct = options.currentProduct;
      }
      if (options.hesitationMatrix) {
        this.hesitationMatrix = options.hesitationMatrix;
      }
    }

    setProductContext(product) {
      this.currentProduct = product;
      // If thread only contains initial greeting and user has not sent any message yet, rehydrate with active product
      const history = window.__AISalesAssociateSessionMemory
        ? window.__AISalesAssociateSessionMemory.getChatHistory()
        : [];
      const hasUserMessage = history.some(m => m.sender === 'user');
      if (!hasUserMessage && product && product.isProductPage) {
        if (window.__AISalesAssociateSessionMemory?.clearChatHistory) {
          window.__AISalesAssociateSessionMemory.clearChatHistory();
        }
        const thread = this.shadow.getElementById('messageThread');
        if (thread) {
          thread.innerHTML = '';
          this.renderInitialGreeting();
        }
      }
    }

    handleHesitationTrigger(trigger) {
      this.hesitationTrigger = trigger;
      if (window.__AISalesAssociateSessionMemory) {
        window.__AISalesAssociateSessionMemory.recordHesitationSignal(trigger);
      }

      // If drawer is already open, NEVER interrupt the ongoing conversation!
      if (this.isOpen) {
        return;
      }

      // Show proactive speech bubble when drawer is closed
      const bubble = this.shadow.getElementById('speechBubble');
      const bubbleMsg = this.shadow.getElementById('bubbleMessage');
      if (bubble && bubbleMsg) {
        bubbleMsg.textContent = trigger.suggestedNudge;
        bubble.classList.add('visible');
      }
    }

    dismissBubble() {
      const bubble = this.shadow.getElementById('speechBubble');
      bubble.classList.remove('visible');
      if (window.__AISalesAssociateSessionMemory) {
        window.__AISalesAssociateSessionMemory.setDrawerState({ bubbleDismissed: true });
      }
    }

    openDrawer() {
      this.isOpen = true;
      this.pauseHesitation();
      const drawer = this.shadow.getElementById('chatDrawer');
      const bubble = this.shadow.getElementById('speechBubble');
      drawer.classList.add('open');
      this.shadow.getElementById('stylistPill').setAttribute('aria-expanded', 'true');
      bubble.classList.remove('visible');

      if (window.__AISalesAssociateSessionMemory) {
        window.__AISalesAssociateSessionMemory.setDrawerState({ isOpen: true, hasOpened: true });
      }

      // Auto-focus input
      setTimeout(() => {
        const input = this.shadow.getElementById('chatInput');
        if (input && this.isOpen) input.focus();
      }, 300);

      // If thread is empty, render initial greeting
      const thread = this.shadow.getElementById('messageThread');
      if (thread.children.length === 0) {
        this.renderInitialGreeting();
      }
    }

    closeDrawer() {
      this.isOpen = false;
      this.resumeHesitation();
      const drawer = this.shadow.getElementById('chatDrawer');
      drawer.classList.remove('open');
      const launcher = this.shadow.getElementById('stylistPill');
      launcher.setAttribute('aria-expanded', 'false');
      launcher.focus({ preventScroll: true });
      if (window.__AISalesAssociateSessionMemory) {
        window.__AISalesAssociateSessionMemory.setDrawerState({ isOpen: false });
      }
    }

    toggleDrawer() {
      if (this.isOpen) {
        this.closeDrawer();
      } else {
        this.openDrawer();
      }
    }

    restoreState() {
      if (!window.__AISalesAssociateSessionMemory) return;

      const history = window.__AISalesAssociateSessionMemory.getChatHistory();
      const thread = this.shadow.getElementById('messageThread');
      thread.innerHTML = '';

      if (history && history.length > 0) {
        for (const msg of history) {
          if (msg.sender === 'user') {
            this._appendUserBubble(msg.text);
          } else {
            this._appendStylistBubble(msg.text, msg.quickReplies, msg.productRecommendation);
          }
        }
      } else {
        this.renderInitialGreeting();
      }

      const drawerState = window.__AISalesAssociateSessionMemory.getDrawerState();
      if (drawerState.isOpen) {
        this.openDrawer();
      }
    }

    renderInitialGreeting() {
      const storeName = this.storeName || "our store";
      let welcomeText = `Welcome to ${storeName}! I'm Julian, your personal stylist. What style or piece can I help you find today?`;
      let quickReplies = ["Browse the collection", "Check sizing & fit", "Shopping for an occasion"];

      if (this.currentProduct && this.currentProduct.isProductPage) {
        const title = this.currentProduct.title || this.currentProduct.name || "this piece";
        welcomeText = `Welcome! I'm Julian, your stylist at ${storeName}. Eyeing **${title}**? Can I help you check fit or suggest a pairing?`;
        quickReplies = ["Check my size", "Will this suit an evening event?", "Are there any discounts today?"];
      }

      this.addStylistMessage(welcomeText, quickReplies, this.currentProduct && this.currentProduct.isProductPage ? this.currentProduct : null);
    }

    handleUserSend(text) {
      this._appendUserBubble(text);
      if (window.__AISalesAssociateSessionMemory) {
        window.__AISalesAssociateSessionMemory.saveChatMessage({
          sender: 'user',
          text
        });
      }

      this.fetchStylistResponse(text);
    }

    async fetchStylistResponse(userText) {
      this.isStreaming = true;
      const threadEl = this.shadow.getElementById('messageThread');

      // Append typing indicator
      const typingEl = document.createElement('div');
      typingEl.className = 'message-row stylist';
      typingEl.id = 'typingIndicator';
      typingEl.innerHTML = `
        <div class="message-avatar">
          <svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
        </div>
        <div class="typing-indicator">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      `;
      threadEl.appendChild(typingEl);
      this._scrollToBottom();

      const sessionId = window.__AISalesAssociateSessionMemory
        ? (window.__AISalesAssociateSessionMemory.getSessionId?.() || window.__AISalesAssociateSessionMemory.getThreadId?.())
        : (this.localSessionId ||= window.crypto.randomUUID());

      const viewedProducts = window.__AISalesAssociateSessionMemory
        ? window.__AISalesAssociateSessionMemory.getViewedProducts()
        : [];

      const customerIdentity = window.__AISalesAssociateDOMExtractor?.extractCustomerIdentity?.() || {};

      let dynamicCatalog = window.__AI_SALES_CONFIG?.catalog;
      if (!dynamicCatalog && window.__AISalesAssociateDOMExtractor?.searchNativeStore) {
        try {
          const nativeMatches = await window.__AISalesAssociateDOMExtractor.searchNativeStore(userText);
          if (Array.isArray(nativeMatches) && nativeMatches.length > 0) {
            dynamicCatalog = nativeMatches;
          }
        } catch (e) {}
      }

      const payload = {
        message: userText,
        session_id: sessionId,
        thread_id: sessionId,
        store_name: this.storeName || (typeof window !== 'undefined' && window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.storeName) || null,
        store_domain: this.storeDomain || (typeof window !== 'undefined' && window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.storeDomain) || (typeof window !== 'undefined' && window.location ? window.location.hostname : null),
        currency: this.currentProduct?.currency || this.currency || (typeof window !== 'undefined' && window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.currency) || '$',
        brand_tone: this.brandTone || (typeof window !== 'undefined' && window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.brandTone) || null,
        customer_id: customerIdentity.customerId || null,
        shopper_uuid: customerIdentity.shopperUuid || null,
        catalog: dynamicCatalog,
        product: this.currentProduct?.isProductPage ? this.currentProduct : null,
        viewed_products: viewedProducts,
        hesitation_trigger: this.hesitationTrigger || null
      };

      let streamRow;
      try {
        const response = await fetch(`${this.backendUrl}/api/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        // Remove typing indicator
        if (typingEl.parentNode) typingEl.parentNode.removeChild(typingEl);

        if (!response.ok || !response.body) {
          throw new Error(`Server returned ${response.status}`);
        }

        // Setup streaming message bubble
        const row = document.createElement('div');
        row.className = 'message-row stylist';
        row.innerHTML = `
          <div class="message-avatar">
            <svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
          </div>
          <div class="message-content" style="max-width: 100%;">
            <div class="message-bubble stream-target"></div>
            <div class="card-target"></div>
            <div class="quick-replies-wrap pills-target"></div>
          </div>
        `;
        streamRow = row;
        threadEl.appendChild(row);

        const bubbleEl = row.querySelector('.stream-target');
        const cardTarget = row.querySelector('.card-target');
        const pillsTarget = row.querySelector('.pills-target');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let quickReplies = [];
        let productRec = null;
        let pending = '';
        let finished = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = (pending + chunk).split('\n');
          pending = lines.pop();

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6).trim();
              if (dataStr === '[DONE]') continue;
              {
                const parsed = JSON.parse(dataStr);
                if (parsed.type === 'token' && parsed.content) {
                  fullText += parsed.content;
                  const cleanStream = this._cleanMessageText(fullText);
                  if (cleanStream) {
                    bubbleEl.innerHTML = this._formatMarkdown(cleanStream);
                  }
                  this._scrollToBottom();
                } else if (parsed.content || parsed.token || parsed.delta || parsed.text) {
                  const token = parsed.content || parsed.token || parsed.delta || parsed.text;
                  fullText += token;
                  const cleanStream = this._cleanMessageText(fullText);
                  if (cleanStream) {
                    bubbleEl.innerHTML = this._formatMarkdown(cleanStream);
                  }
                  this._scrollToBottom();
                }
                if (parsed.type === 'error') throw new Error('Stylist unavailable');
                if (parsed.type === 'done') {
                  finished = true;
                  if (parsed.session_id && window.__AISalesAssociateSessionMemory?.setSessionId) {
                    window.__AISalesAssociateSessionMemory.setSessionId(parsed.session_id);
                  }
                  if (parsed.message) {
                    fullText = parsed.message;
                  }
                  if (parsed.quick_replies && Array.isArray(parsed.quick_replies) && parsed.quick_replies.length > 0) {
                    quickReplies = parsed.quick_replies;
                  }
                  if (parsed.show_card && Array.isArray(parsed.recommended_products) && parsed.recommended_products.length > 0) {
                    productRec = parsed.recommended_products;
                  }
                  if (parsed.action_payload) {
                    this.activeActionPayload = parsed.action_payload;
                  }
                }
                if (parsed.quick_replies && Array.isArray(parsed.quick_replies) && parsed.quick_replies.length > 0) {
                  quickReplies = parsed.quick_replies;
                }
                if (parsed.product) {
                  productRec = parsed.product;
                }
              }
            }
          }
        }

        if (!finished) throw new Error('Incomplete response');
        // Clean final message and extract pills if present in fullText
        const pillsMatch = fullText.match(/<pills>\s*(\[.*?\])\s*<\/pills>/i);
        if (pillsMatch && (!quickReplies || quickReplies.length === 0)) {
          try {
            const parsedPills = JSON.parse(pillsMatch[1]);
            if (Array.isArray(parsedPills) && parsedPills.length > 0) {
              quickReplies = parsedPills;
            }
          } catch (e) {}
        }
        if (!quickReplies || quickReplies.length === 0) {
          const pillsSection = fullText.match(/<pills>[\s\S]*/i);
          if (pillsSection) {
            const matches = pillsSection[0].match(/"([^"]+)"/g);
            if (matches && matches.length > 0) {
              quickReplies = matches.map(m => m.replace(/^"|"$/g, ''));
            }
          }
        }

        const finalCleanText = this._cleanMessageText(fullText) || "I'm right here with you! Tell me about the occasion or vibe you're aiming for.";
        bubbleEl.innerHTML = this._formatMarkdown(finalCleanText);

        // Render Product Recommendation Card only when a specific item is curated/recommended
        if (productRec) {
          this._renderProductCard(cardTarget, productRec);
        }

        // Render Quick Reply Pills dynamically
        if (quickReplies && quickReplies.length > 0) {
          this._renderPills(pillsTarget, quickReplies);
        }

        // Save to Session Memory
        if (window.__AISalesAssociateSessionMemory) {
          window.__AISalesAssociateSessionMemory.saveChatMessage({
            sender: 'stylist',
            text: finalCleanText,
            quickReplies: quickReplies,
            productRecommendation: productRec
          });
        }
      } catch (err) {
        // Fallback gracefully without throwing or crashing host
        if (typingEl.parentNode) typingEl.parentNode.removeChild(typingEl);
        streamRow?.remove();
        this.handleFallbackResponse();
      } finally {
        this.isStreaming = false;
        this._scrollToBottom();
      }
    }

    handleFallbackResponse() {
      const product = this.currentProduct?.isProductPage ? this.currentProduct : null;
      this.addStylistMessage("The stylist is unavailable. You can keep shopping or send your question again.", [], product);
    }

    addStylistMessage(text, quickReplies = [], product = null) {
      this._appendStylistBubble(text, quickReplies, product);
      if (window.__AISalesAssociateSessionMemory) {
        window.__AISalesAssociateSessionMemory.saveChatMessage({
          sender: 'stylist',
          text,
          quickReplies,
          productRecommendation: product
        });
      }
    }

    _appendUserBubble(text) {
      const threadEl = this.shadow.getElementById('messageThread');
      const row = document.createElement('div');
      row.className = 'message-row user';
      row.innerHTML = `<div class="message-bubble">${this._escapeHTML(text)}</div>`;
      threadEl.appendChild(row);
      this._scrollToBottom();
    }

    _appendStylistBubble(text, quickReplies = [], product = null) {
      const threadEl = this.shadow.getElementById('messageThread');
      const row = document.createElement('div');
      row.className = 'message-row stylist';
      row.innerHTML = `
        <div class="message-avatar">
          <svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
        </div>
        <div class="message-content" style="max-width: 100%;">
          <div class="message-bubble">${this._formatMarkdown(text)}</div>
          <div class="card-target"></div>
          <div class="quick-replies-wrap pills-target"></div>
        </div>
      `;
      threadEl.appendChild(row);

      if (product) {
        const cardTarget = row.querySelector('.card-target');
        this._renderProductCard(cardTarget, product);
      }

      if (quickReplies && quickReplies.length > 0) {
        const pillsTarget = row.querySelector('.pills-target');
        this._renderPills(pillsTarget, quickReplies);
      }

      this._scrollToBottom();
    }

    _renderProductCard(container, product) {
      if (Array.isArray(product)) {
        product.forEach(item => this._renderProductCard(container, item));
        return;
      }
      const title = product?.title || product?.name;
      if (!title) return;
      const card = document.createElement('div');
      card.className = 'product-card';

      const imgUrl = product.image || product.image_url;
      const priceText = product.price != null && product.price !== '' ? `${product.currency || '$'}${product.price}` : '';

      card.innerHTML = `
        <div class="product-card-hero-badge">
          <span>Stylist pick</span>
        </div>
        <div class="product-card-body">
          ${imgUrl ? `<img src="${this._escapeHTML(imgUrl)}" alt="" class="product-card-img" />` : ''}
          <div class="product-card-details">
            <div class="product-card-title">${this._escapeHTML(title)}</div>
            <div class="product-card-price">${this._escapeHTML(priceText)}</div>
            <div class="product-card-desc">${this._escapeHTML(product.description || '')}</div>
          </div>
        </div>
        <div class="product-card-actions">
          <button class="btn-view-buy" id="btnViewBuy">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"></path><line x1="3" y1="6" x2="21" y2="6"></line><path d="M16 10a4 4 0 0 1-8 0"></path></svg>
            View product options
          </button>
        </div>
      `;

      const btn = card.querySelector('#btnViewBuy');
      btn.addEventListener('click', () => {
        this.triggerViewAndBuy(product);
      });

      container.appendChild(card);
    }

    _renderPills(container, pills) {
      container.innerHTML = '';
      for (const pillText of pills) {
        const pillBtn = document.createElement('button');
        pillBtn.className = 'quick-reply-pill';
        pillBtn.textContent = pillText;
        pillBtn.addEventListener('click', () => {
          if (!this.isStreaming) {
            this.handleUserSend(pillText);
          }
        });
        container.appendChild(pillBtn);
      }
    }

    triggerViewAndBuy(product) {
      shield.executeSafe(() => {
        if (product.url) {
          const url = new URL(product.url, location.href);
          if (url.origin !== location.origin || !['https:', 'http:'].includes(url.protocol)) {
            this.addStylistMessage("Open this item in the store to review its options.");
            return;
          }
          if (url.pathname !== location.pathname || url.search !== location.search) {
            location.assign(url.href);
            return;
          }
        } else if (!this.currentProduct?.isProductPage ||
                   (product.title || product.name) !== this.currentProduct.title) {
          this.addStylistMessage("Look for this item in the store to review its options.");
          return;
        }
        this.closeDrawer();
        const button = document.querySelector('#add-to-cart-btn, button[name="add"], .single_add_to_cart_button, .add-to-cart');
        if (button) {
          button.focus({ preventScroll: true });
          button.scrollIntoView({ block: 'center' });
        }
      });
    }

    _cleanMessageText(text) {
      if (!text) return '';
      return text.replace(/<pills>[\s\S]*?<\/pills>/gi, '').replace(/<pills>[\s\S]*/gi, '').trim();
    }

    _scrollToBottom() {
      const threadEl = this.shadow.getElementById('messageThread');
      if (threadEl) {
        threadEl.scrollTop = threadEl.scrollHeight;
      }
    }

    _escapeHTML(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    _formatMarkdown(text) {
      if (!text) return '';
      let cleaned = this._cleanMessageText(text);
      let escaped = this._escapeHTML(cleaned);
      // Bold
      escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      // Italics
      escaped = escaped.replace(/\*(.*?)\*/g, '<em>$1</em>');
      // Line breaks
      escaped = escaped.replace(/\n/g, '<br/>');
      return escaped;
    }

    destroy() {
      if (this.parentNode) {
        this.parentNode.removeChild(this);
      }
    }
  }

  // Register Web Component safely
  if (!customElements.get('ai-sales-associate')) {
    customElements.define('ai-sales-associate', AISalesAssociateWidget);
  }

  window.__AISalesAssociateWidget = {
    AISalesAssociateWidget,
    mount: (container = document.body, options = {}) => {
      let el = document.querySelector('ai-sales-associate');
      if (!el) {
        el = document.createElement('ai-sales-associate');
        container.appendChild(el);
      }
      if (typeof el.configure === 'function') {
        el.configure(options);
      }
      return el;
    }
  };
})(window, document);
