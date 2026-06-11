(function () {
    const authArea = document.querySelector('.auth-page-wrap');
    const botPanel = document.querySelector('.auth-bot-panel');
    if (!authArea || !botPanel) return;

    const orb = document.createElement('div');
    orb.className = 'cursor-orb';
    document.body.appendChild(orb);

    const halo = document.createElement('div');
    halo.className = 'cursor-halo';
    document.body.appendChild(halo);

    const updateHover = (x, y) => {
        orb.style.left = `${x}px`;
        orb.style.top = `${y}px`;
        orb.style.opacity = '1';
        halo.style.left = `${x}px`;
        halo.style.top = `${y}px`;
        halo.style.opacity = '0.65';
    };

    const fadeOut = () => {
        orb.style.opacity = '0';
        halo.style.opacity = '0';
    };

    botPanel.addEventListener('pointermove', (event) => {
        const rect = botPanel.getBoundingClientRect();
        const x = event.clientX;
        const y = event.clientY;
        updateHover(x, y);
        const cx = ((event.clientX - rect.left) / rect.width) * 100;
        const cy = ((event.clientY - rect.top) / rect.height) * 100;
        botPanel.style.setProperty('--cx', `${cx}%`);
        botPanel.style.setProperty('--cy', `${cy}%`);
    });

    botPanel.addEventListener('pointerleave', fadeOut);
    botPanel.addEventListener('pointerdown', fadeOut);

    const nodes = botPanel.querySelectorAll('.bot-node');
    nodes.forEach((node, index) => {
        const delay = 0.15 + index * 0.08;
        node.style.animation = `nodeDrift 3s ease-in-out ${delay}s infinite alternate`;
    });

    const registerForm = document.querySelector('#register-form');
    const loginForm = document.querySelector('form[action="/auth/login"]');
    const loadingOverlay = document.querySelector('#auth-loading-overlay');
    const submitButton = document.querySelector('#auth-submit-btn');
    const tierSelect = document.querySelector('select[name="tier"]');

    const attachSubmitLoader = (form, button, message, subtext) => {
        if (!form || !button || !loadingOverlay) return;
        form.addEventListener('submit', () => {
            button.disabled = true;
            button.classList.add('btn-disabled');
            const loadingText = loadingOverlay.querySelector('.loading-text');
            const loadingSubtext = loadingOverlay.querySelector('.loading-subtext');
            if (loadingText) loadingText.textContent = message;
            if (loadingSubtext) loadingSubtext.textContent = subtext;
            loadingOverlay.classList.add('active');
        });
    };

    if (registerForm && submitButton) {
        attachSubmitLoader(
            registerForm,
            submitButton,
            tierSelect && tierSelect.value === 'Premium'
                ? 'Preparing your premium account…'
                : 'Preparing your account…',
            tierSelect && tierSelect.value === 'Premium'
                ? 'Saving premium signup details and securing your access.'
                : 'Saving signup details and securing your access.'
        );
    }

    if (loginForm && submitButton) {
        attachSubmitLoader(
            loginForm,
            submitButton,
            'Verifying credentials…',
            'Building your secure session and connecting the terminal.'
        );
    }
})();
