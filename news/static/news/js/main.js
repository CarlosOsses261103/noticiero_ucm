(() => {
    const playlist = readJsonScript("broadcast-data", []);
    const query = new URLSearchParams(window.location.search);
    const shouldAutoplay = query.get("autoplay") === "1";

    const titleEl = document.querySelector("[data-news-title]");
    const headingEl = document.querySelector("[data-news-heading]");
    const bodyEl = document.querySelector("[data-news-body]");
    const currentLabelEl = document.querySelector("[data-current-label]");
    const playlistPositionEl = document.querySelector("[data-playlist-position]");
    const imageEl = document.querySelector("[data-carousel-image]");
    const emptyCarouselEl = document.querySelector("[data-empty-carousel]");
    const countEl = document.querySelector("[data-carousel-count]");
    const startButton = document.getElementById("startButton");
    const nextButton = document.getElementById("nextButton");
    const audioState = document.getElementById("audioState");
    const audio = document.getElementById("newsAudio");
    const video = document.getElementById("presenterVideo");

    let activeArticleIndex = 0;
    let activeImageIndex = 0;
    let activeImages = [];
    let carouselTimer = null;
    let isBroadcastRunning = false;
    let playbackToken = 0;

    async function enterFullscreen() {
        if (document.fullscreenElement || !document.documentElement.requestFullscreen) {
            return;
        }

        try {
            await document.documentElement.requestFullscreen({ navigationUI: "hide" });
        } catch {
            audioState.textContent = "Modo navegador";
        }
    }

    function syncFullscreenClass() {
        document.body.classList.toggle("is-fullscreen", Boolean(document.fullscreenElement));
    }

    function readJsonScript(id, fallback) {
        const script = document.getElementById(id);
        if (!script) {
            return fallback;
        }

        try {
            return JSON.parse(script.textContent);
        } catch {
            return fallback;
        }
    }

    function loadArticle(index) {
        const article = playlist[index];
        if (!article) {
            return null;
        }

        activeArticleIndex = index;
        activeImageIndex = 0;
        activeImages = article.image_urls || [];

        document.title = `${article.title} | Noticiero con IA`;
        titleEl.textContent = article.title;
        headingEl.textContent = article.title;
        bodyEl.textContent = article.body;
        currentLabelEl.textContent = `Noticiero con IA · Noticia ${index + 1} / ${playlist.length}`;
        playlistPositionEl.textContent = `Noticia ${index + 1} de ${playlist.length}`;

        updateCarousel(0, true);
        updateNextButton();
        return article;
    }

    function updateCarousel(index, immediate = false) {
        if (!imageEl || !emptyCarouselEl || !countEl) {
            return;
        }

        if (activeImages.length === 0) {
            imageEl.classList.add("is-hidden");
            emptyCarouselEl.classList.remove("is-hidden");
            countEl.textContent = "0 / 0";
            return;
        }

        activeImageIndex = index % activeImages.length;
        imageEl.classList.remove("is-hidden");
        emptyCarouselEl.classList.add("is-hidden");
        countEl.textContent = `${activeImageIndex + 1} / ${activeImages.length}`;

        if (immediate) {
            imageEl.src = activeImages[activeImageIndex];
            return;
        }

        imageEl.classList.add("is-changing");
        window.setTimeout(() => {
            imageEl.src = activeImages[activeImageIndex];
            imageEl.classList.remove("is-changing");
        }, 180);
    }

    function startCarousel() {
        stopCarousel();

        if (activeImages.length <= 1) {
            return;
        }

        carouselTimer = window.setInterval(() => {
            updateCarousel(activeImageIndex + 1);
        }, 5000);
    }

    function stopCarousel() {
        window.clearInterval(carouselTimer);
        carouselTimer = null;
    }

    function stopCurrentAudio() {
        if (audio) {
            audio.onended = null;
            audio.onerror = null;
            audio.pause();
        }

        if ("speechSynthesis" in window) {
            window.speechSynthesis.cancel();
        }
    }

    function updateNextButton() {
        if (!nextButton) {
            return;
        }

        nextButton.disabled = playlist.length <= 1;
        nextButton.textContent = activeArticleIndex >= playlist.length - 1
            ? "Volver al inicio"
            : "Siguiente noticia";
    }

    async function startBroadcast() {
        if (playlist.length === 0) {
            audioState.textContent = "Sin noticias";
            return;
        }

        enterFullscreen();
        isBroadcastRunning = true;
        startButton.disabled = true;
        startButton.textContent = "Noticiero en curso";

        if (video) {
            video.muted = true;
            video.currentTime = 0;
            video.play().catch(() => {});
        }

        await playArticle(activeArticleIndex);
    }

    async function playArticle(index) {
        if (!isBroadcastRunning) {
            return;
        }

        if (index >= playlist.length) {
            finishBroadcast();
            return;
        }

        const token = ++playbackToken;
        const article = loadArticle(index);
        startCarousel();
        audioState.textContent = "Preparando audio";

        const audioUrl = await resolveAudioUrl(article);

        if (!isBroadcastRunning || token !== playbackToken) {
            return;
        }

        if (audioUrl && audio) {
            await playAudioFile(audioUrl, token, () => playArticle(index + 1));
            return;
        }

        playWithBrowserVoice(article, token, () => playArticle(index + 1));
    }

    async function resolveAudioUrl(article) {
        if (article.audio_url) {
            return article.audio_url;
        }

        if (!article.audio_api_url) {
            return "";
        }

        try {
            const response = await fetch(article.audio_api_url);
            if (!response.ok) {
                return "";
            }

            const data = await response.json();
            article.audio_url = data.audio_url || "";
            return article.audio_url;
        } catch {
            return "";
        }
    }

    async function playAudioFile(audioUrl, token, onEnded) {
        audio.pause();
        audio.src = audioUrl;
        audio.currentTime = 0;
        audio.onended = () => {
            if (token === playbackToken && isBroadcastRunning) {
                onEnded();
            }
        };
        audio.onerror = () => {
            if (token === playbackToken && isBroadcastRunning) {
                audioState.textContent = "Error de audio";
                onEnded();
            }
        };

        try {
            audioState.textContent = "Reproduciendo";
            await audio.play();
        } catch {
            if (token === playbackToken) {
                audioState.textContent = "Presiona iniciar";
                startButton.disabled = false;
                startButton.textContent = "Continuar noticiero";
                isBroadcastRunning = false;
            }
        }
    }

    function playWithBrowserVoice(article, token, onEnded) {
        if (!("speechSynthesis" in window)) {
            onEnded();
            return;
        }

        const text = `${article.title}. ${article.body}`.trim();
        if (!text) {
            onEnded();
            return;
        }

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "es-CL";
        utterance.rate = 0.95;
        utterance.pitch = 1;
        utterance.onend = () => {
            if (token === playbackToken && isBroadcastRunning) {
                onEnded();
            }
        };
        utterance.onerror = () => {
            if (token === playbackToken && isBroadcastRunning) {
                onEnded();
            }
        };

        audioState.textContent = "Voz del navegador";
        window.speechSynthesis.speak(utterance);
    }

    function goToNextArticle() {
        if (playlist.length === 0) {
            audioState.textContent = "Sin noticias";
            return;
        }

        const nextIndex = (activeArticleIndex + 1) % playlist.length;
        playbackToken += 1;
        stopCurrentAudio();

        if (isBroadcastRunning) {
            playArticle(nextIndex);
            return;
        }

        loadArticle(nextIndex);
        audioState.textContent = "Noticia lista";
    }

    function finishBroadcast() {
        isBroadcastRunning = false;
        playbackToken += 1;
        stopCarousel();
        audioState.textContent = "Noticiero finalizado";
        startButton.textContent = "Repetir noticiero";
        startButton.disabled = false;
        loadArticle(0);
    }

    function preparePage() {
        if (playlist.length === 0) {
            audioState.textContent = "Sin noticias";
            return;
        }

        loadArticle(0);
        updateNextButton();

        if (video) {
            video.play().catch(() => {});
        }

        if (shouldAutoplay) {
            window.setTimeout(() => {
                startBroadcast();
            }, 600);
        }
    }

    startButton.addEventListener("click", startBroadcast);
    nextButton.addEventListener("click", goToNextArticle);
    document.addEventListener("fullscreenchange", syncFullscreenClass);
    window.addEventListener("load", preparePage);
})();
