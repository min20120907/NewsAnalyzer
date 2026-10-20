/**
 * Cinematic Animation Layer for NewsAnalyzer
 * 負責渲染虛擬滑鼠、點擊漣漪、聚光燈、提示氣泡、標題橫幅、前期提要卡片、結果區塊解析器與轉場過場
 */
(function () {
  if (window.CinemaOverlay) return;

  class OverlayController {
    constructor() {
      this.speed = 1.0;
      this.paused = false;
      this.isInteractive = false;
      this.cursorX = 100;
      this.cursorY = 100;
      this.currentFocusEl = null;
      this._initDOM();
      this._bindEvents();
    }

    _initDOM() {
      if (document.getElementById('cinema-overlay')) return;

      const overlay = document.createElement('div');
      overlay.id = 'cinema-overlay';
      overlay.innerHTML = `
        <div class="cinema-transition-shutter" id="cinema-shutter"></div>
        <div class="cinema-spotlight-box" id="cinema-spotlight"></div>
        <div class="cinema-cursor" id="cinema-cursor"></div>
        <div class="cinema-tooltip" id="cinema-tooltip"></div>
        <div class="cinema-explainer" id="cinema-explainer"></div>
        <div class="cinema-banner" id="cinema-banner">
          <div class="cinema-banner-title" id="cinema-banner-title"></div>
          <div class="cinema-banner-desc" id="cinema-banner-desc"></div>
        </div>
        <div class="cinema-briefing" id="cinema-briefing">
          <div class="briefing-tag" id="briefing-tag">SCENARIO BRIEFING</div>
          <div class="briefing-title" id="briefing-title"></div>
          <div class="briefing-desc" id="briefing-desc"></div>
          <div class="briefing-points" id="briefing-points"></div>
        </div>
      `;
      document.body.appendChild(overlay);

      this.cursor = document.getElementById('cinema-cursor');
      this.tooltip = document.getElementById('cinema-tooltip');
      this.explainer = document.getElementById('cinema-explainer');
      this.banner = document.getElementById('cinema-banner');
      this.bannerTitle = document.getElementById('cinema-banner-title');
      this.bannerDesc = document.getElementById('cinema-banner-desc');
      this.spotlight = document.getElementById('cinema-spotlight');
      this.briefing = document.getElementById('cinema-briefing');
      this.briefingTag = document.getElementById('briefing-tag');
      this.briefingTitle = document.getElementById('briefing-title');
      this.briefingDesc = document.getElementById('briefing-desc');
      this.briefingPoints = document.getElementById('briefing-points');
      this.shutter = document.getElementById('cinema-shutter');

      this.cursorX = window.innerWidth / 2;
      this.cursorY = 180;
      this.updateCursorPos(this.cursorX, this.cursorY, false);
    }

    _bindEvents() {
      const sync = () => this._syncSpotlight();
      window.addEventListener('scroll', sync, { passive: true });
      window.addEventListener('resize', sync, { passive: true });

      // 持續以 requestAnimationFrame 同步聚光燈位置，徹底消除平滑捲動與排版位移造成的偏差
      const rafLoop = () => {
        if (this.currentFocusEl && this.spotlight.classList.contains('active')) {
          this._syncSpotlight();
        }
        requestAnimationFrame(rafLoop);
      };
      requestAnimationFrame(rafLoop);
    }

    _syncSpotlight() {
      if (!this.currentFocusEl || !this.spotlight.classList.contains('active')) return;
      const rect = this.currentFocusEl.getBoundingClientRect();
      const pad = 6;
      this.spotlight.style.left = `${Math.max(0, rect.left - pad)}px`;
      this.spotlight.style.top = `${Math.max(0, rect.top - pad)}px`;
      this.spotlight.style.width = `${rect.width + pad * 2}px`;
      this.spotlight.style.height = `${rect.height + pad * 2}px`;
    }

    updateCursorPos(x, y, animate = true) {
      this.cursorX = x;
      this.cursorY = y;
      if (!animate) {
        this.cursor.style.transition = 'none';
      } else {
        this.cursor.style.transition = `transform ${0.45 / this.speed}s cubic-bezier(0.22, 1, 0.36, 1)`;
      }
      this.cursor.style.transform = `translate3d(${x}px, ${y}px, 0)`;

      this.tooltip.style.left = `${x}px`;
      this.tooltip.style.top = `${y}px`;
    }

    async moveTo(targetOrX, y = null, duration = 450) {
      let destX = targetOrX;
      let destY = y;

      if (typeof targetOrX === 'string') {
        const el = document.querySelector(targetOrX);
        if (el) {
          const rect = el.getBoundingClientRect();
          destX = rect.left + rect.width / 2;
          destY = rect.top + rect.height / 2;
        } else {
          return;
        }
      }

      this.updateCursorPos(destX, destY, true);
      await this.sleep((duration / this.speed));
    }

    async click(target = null) {
      if (target) {
        await this.moveTo(target);
      }
      this.cursor.classList.add('clicking');
      this._createRipple(this.cursorX, this.cursorY);

      await this.sleep(120 / this.speed);
      this.cursor.classList.remove('clicking');
      await this.sleep(100 / this.speed);
    }

    _createRipple(x, y) {
      const ripple = document.createElement('div');
      ripple.className = 'cinema-ripple';
      ripple.style.left = `${x}px`;
      ripple.style.top = `${y}px`;
      ripple.style.width = '44px';
      ripple.style.height = '44px';
      document.getElementById('cinema-overlay').appendChild(ripple);

      setTimeout(() => ripple.remove(), 750);
    }

    showSpotlight(target) {
      const el = typeof target === 'string' ? document.querySelector(target) : target;
      if (!el) {
        this.hideSpotlight();
        return;
      }
      this.currentFocusEl = el;
      this._syncSpotlight();
      this.spotlight.classList.add('active');
    }

    hideSpotlight() {
      this.currentFocusEl = null;
      this.spotlight.classList.remove('active');
    }

    showTooltip(text) {
      if (!text) {
        this.hideTooltip();
        return;
      }
      this.tooltip.textContent = text;
      this.tooltip.classList.add('active');
    }

    hideTooltip() {
      this.tooltip.classList.remove('active');
    }

    showExplainer(html) {
      if (!html) {
        this.hideExplainer();
        return;
      }
      this.explainer.innerHTML = html;
      this.explainer.classList.add('active');
    }

    hideExplainer() {
      this.explainer.classList.remove('active');
    }

    async showBanner(title, desc = '', duration = 2500) {
      this.bannerTitle.textContent = title;
      this.bannerDesc.textContent = desc;
      this.banner.classList.add('show');

      if (duration > 0) {
        await this.sleep(duration / this.speed);
        this.banner.classList.remove('show');
      }
    }

    hideBanner() {
      this.banner.classList.remove('show');
    }

    async showBriefing(tag, title, desc, points = [], duration = 4000) {
      this.briefingTag.textContent = tag || 'SCENARIO BRIEFING';
      this.briefingTitle.textContent = title;
      this.briefingDesc.textContent = desc;
      this.briefingPoints.innerHTML = points.map(p => `<div class="briefing-point"><span>🔹</span><span>${p}</span></div>`).join('');

      this.briefing.classList.add('show');
      await this.sleep(duration / this.speed);
      this.briefing.classList.remove('show');
      await this.sleep(400 / this.speed);
    }

    async shutterTransition(duration = 600) {
      this.shutter.classList.add('active');
      await this.sleep(duration / this.speed);
      this.shutter.classList.remove('active');
      await this.sleep(200 / this.speed);
    }

    async typeText(target, text, charDelay = 25) {
      const el = typeof target === 'string' ? document.querySelector(target) : target;
      if (!el) return;

      await this.moveTo(target);
      await this.click();
      el.focus();
      el.value = '';

      for (let i = 0; i < text.length; i++) {
        while (this.paused) await this.sleep(100);
        el.value += text[i];
        el.dispatchEvent(new Event('input', { bubbles: true }));
        await this.sleep(charDelay / this.speed);
      }
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    sleep(ms) {
      return new Promise(resolve => setTimeout(resolve, Math.max(10, ms)));
    }
  }

  window.CinemaOverlay = new OverlayController();
})();