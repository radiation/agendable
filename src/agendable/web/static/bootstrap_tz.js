(() => {
    try {
        if (document.cookie.includes("agendable_tz=")) {
            return;
        }

        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (!tz) {
            return;
        }

        let cookie = `agendable_tz=${tz}; Path=/; Max-Age=31536000; SameSite=Lax`;
        if (location && location.protocol === "https:") {
            cookie += "; Secure";
        }

        document.cookie = cookie;
    } catch (_err) {
        // Best-effort only.
    }
})();
