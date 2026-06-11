/**
 * 2025-style ambient animations — scroll reveals, parallax, floating particles, card tilt.
 * Inspired by modern web design trends (glassmorphism + motion-first UX).
 */
(function () {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    document.addEventListener("DOMContentLoaded", () => {
        initAmbientParticles();
        initHeroParallax();
        initCardTilt();
        initScrollProgress();
        initMagneticButtons();
        initTextReveal();
    });

    /* Floating ambient particles (Pinterest 2025 glass hero style) */
    function initAmbientParticles() {
        const layer = document.createElement("div");
        layer.className = "ambient-particle-layer";
        layer.setAttribute("aria-hidden", "true");
        document.body.prepend(layer);

        for (let i = 0; i < 18; i++) {
            const p = document.createElement("span");
            p.className = "ambient-particle";
            const size = 4 + Math.random() * 8;
            p.style.cssText = `
                width:${size}px; height:${size}px;
                left:${Math.random() * 100}%;
                top:${Math.random() * 100}%;
                --dur:${12 + Math.random() * 20}s;
                --delay:${Math.random() * -20}s;
                --drift:${20 + Math.random() * 40}px;
            `;
            layer.appendChild(p);
        }
    }

    /* Hero mouse parallax on neon arcs + glass orb */
    function initHeroParallax() {
        const hero = document.querySelector(".hero-atmosphere");
        if (!hero) return;

        const targets = hero.querySelectorAll(".neon-arc, .hero-glass-orb, .tech-card");
        hero.addEventListener("mousemove", (e) => {
            const rect = hero.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width - 0.5;
            const y = (e.clientY - rect.top) / rect.height - 0.5;
            targets.forEach((el, i) => {
                const depth = (i + 1) * 8;
                el.style.transform = `translate(${x * depth}px, ${y * depth}px)`;
            });
        });
        hero.addEventListener("mouseleave", () => {
            targets.forEach(el => { el.style.transform = ""; });
        });
    }

    /* 3D tilt on glass cards (2025 hover trend) */
    function initCardTilt() {
        document.querySelectorAll(".tech-card, .studio-card, .ufo-panel-card, .auth-tech-card").forEach(card => {
            card.classList.add("tilt-card");
            card.addEventListener("mousemove", (e) => {
                const rect = card.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width - 0.5;
                const y = (e.clientY - rect.top) / rect.height - 0.5;
                card.style.transform = `perspective(800px) rotateY(${x * 6}deg) rotateX(${-y * 6}deg) translateY(-4px)`;
            });
            card.addEventListener("mouseleave", () => {
                card.style.transform = "";
            });
        });
    }

    /* Top scroll progress bar */
    function initScrollProgress() {
        const bar = document.createElement("div");
        bar.className = "scroll-progress-bar";
        bar.setAttribute("aria-hidden", "true");
        document.body.prepend(bar);

        window.addEventListener("scroll", () => {
            const scrollTop = window.scrollY;
            const docHeight = document.documentElement.scrollHeight - window.innerHeight;
            const pct = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
            bar.style.width = pct + "%";
        }, { passive: true });
    }

    /* Subtle magnetic pull on pill buttons */
    function initMagneticButtons() {
        document.querySelectorAll(".btn-glass-pill, .btn-ghost-pill, .auth-btn-submit").forEach(btn => {
            btn.addEventListener("mousemove", (e) => {
                const rect = btn.getBoundingClientRect();
                const x = e.clientX - rect.left - rect.width / 2;
                const y = e.clientY - rect.top - rect.height / 2;
                btn.style.transform = `translate(${x * 0.15}px, ${y * 0.15}px)`;
            });
            btn.addEventListener("mouseleave", () => { btn.style.transform = ""; });
        });
    }

    /* Staggered word reveal on hero headline */
    function initTextReveal() {
        const headline = document.querySelector(".hero-headline");
        if (!headline || headline.dataset.revealed) return;
        headline.dataset.revealed = "true";
        const text = headline.textContent.trim();
        headline.textContent = "";
        headline.classList.add("text-reveal-wrap");
        text.split(" ").forEach((word, i) => {
            const span = document.createElement("span");
            span.className = "text-reveal-word";
            span.textContent = word + " ";
            span.style.animationDelay = (0.08 * i) + "s";
            headline.appendChild(span);
        });
    }
})();

/* Stagger chart panels when results appear */
function staggerChartPanels() {
    document.querySelectorAll("#results-stage-view .ufo-panel-card").forEach((panel, i) => {
        panel.classList.remove("chart-panel-visible");
        panel.style.animationDelay = (i * 0.1) + "s";
        requestAnimationFrame(() => panel.classList.add("chart-panel-visible"));
    });
}

/* Stagger supplier table rows */
function staggerTableRows() {
    document.querySelectorAll("#supplier-table-rows tr").forEach((row, i) => {
        row.classList.add("table-row-reveal");
        row.style.animationDelay = (i * 0.06) + "s";
    });
}
