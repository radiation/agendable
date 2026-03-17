(() => {
    const tzInput = document.getElementById("signup-timezone");
    if (!tzInput) {
        return;
    }

    const systemTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!systemTz) {
        return;
    }

    const hasSystemTz = Array.from(tzInput.options).some((opt) => opt.value === systemTz);
    if (hasSystemTz && (!tzInput.value || tzInput.value === "UTC")) {
        tzInput.value = systemTz;
    }
})();
