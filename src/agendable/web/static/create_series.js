(() => {
    let attendeeSuggestionIndex = -1;

    const normalizeEmail = (value) => String(value || "").trim().toLowerCase();

    const attendeesHiddenInput = document.getElementById("attendee-emails");
    const attendeesQueryInput = document.getElementById("attendee-query");
    const attendeeChipList = document.getElementById("selected-attendees");
    const selectedAttendeeEmails = new Set(
        String(attendeesHiddenInput?.value || "")
            .split(",")
            .map((value) => normalizeEmail(value))
            .filter((value) => value.length > 0)
    );
    const selectedAttendeeLabels = new Map(
        Array.from(selectedAttendeeEmails).map((email) => [email, email])
    );

    const syncAttendeeEmailsValue = () => {
        if (!(attendeesHiddenInput instanceof HTMLInputElement)) {
            return;
        }
        attendeesHiddenInput.value = Array.from(selectedAttendeeEmails).join(", ");
    };

    const renderAttendeeChips = () => {
        if (!(attendeeChipList instanceof HTMLElement)) {
            return;
        }

        attendeeChipList.innerHTML = "";
        for (const email of selectedAttendeeEmails) {
            const chip = document.createElement("span");
            chip.className = "attendee-chip";

            const label = document.createElement("span");
            label.className = "attendee-chip-label";
            label.textContent = selectedAttendeeLabels.get(email) || email;
            chip.appendChild(label);

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "attendee-chip-remove";
            removeButton.dataset.attendeeEmail = email;
            removeButton.setAttribute("aria-label", `Remove ${email}`);
            removeButton.textContent = "Remove";
            chip.appendChild(removeButton);

            attendeeChipList.appendChild(chip);
        }
    };

    const clearAttendeeSuggestions = () => {
        const suggestions = document.getElementById("attendee-suggestions");
        if (suggestions) {
            suggestions.innerHTML = "";
        }
        attendeeSuggestionIndex = -1;
    };

    const removeAttendeeEmail = (email) => {
        const normalizedEmail = normalizeEmail(email);
        if (!normalizedEmail) {
            return;
        }
        selectedAttendeeEmails.delete(normalizedEmail);
        selectedAttendeeLabels.delete(normalizedEmail);
        syncAttendeeEmailsValue();
        renderAttendeeChips();
    };

    const getAttendeeSuggestionButtons = () => {
        const container = document.getElementById("attendee-suggestions");
        if (!container) {
            return [];
        }
        return Array.from(container.querySelectorAll("button[data-attendee-email]"));
    };

    const setAttendeeSuggestionIndex = (index) => {
        const buttons = getAttendeeSuggestionButtons();
        attendeeSuggestionIndex = index;

        buttons.forEach((button, buttonIndex) => {
            button.classList.toggle("typeahead-active", buttonIndex === attendeeSuggestionIndex);
        });

        if (attendeeSuggestionIndex >= 0 && attendeeSuggestionIndex < buttons.length) {
            buttons[attendeeSuggestionIndex].scrollIntoView({ block: "nearest" });
        }
    };

    const addAttendeeEmail = (email, label = null) => {
        const suggestions = document.getElementById("attendee-suggestions");
        const normalizedEmail = normalizeEmail(email);
        if (!normalizedEmail) {
            return;
        }

        const normalizedLabel = String(label || "").trim();
        if (!selectedAttendeeEmails.has(normalizedEmail)) {
            selectedAttendeeEmails.add(normalizedEmail);
        }
        selectedAttendeeLabels.set(normalizedEmail, normalizedLabel || normalizedEmail);
        syncAttendeeEmailsValue();
        renderAttendeeChips();

        if (attendeesQueryInput instanceof HTMLInputElement) {
            attendeesQueryInput.value = "";
            attendeesQueryInput.focus();
        }

        if (suggestions) {
            suggestions.innerHTML = "";
        }
    };

    const addTypedAttendeeQuery = () => {
        if (!(attendeesQueryInput instanceof HTMLInputElement)) {
            return false;
        }

        const candidate = normalizeEmail(attendeesQueryInput.value.replace(/,$/, ""));
        if (!candidate || !candidate.includes("@")) {
            return false;
        }

        addAttendeeEmail(candidate, candidate);
        return true;
    };

    document.addEventListener("pointerdown", (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }

        const button = target.closest("button[data-attendee-email]");
        if (!(button instanceof HTMLButtonElement)) {
            return;
        }

        event.preventDefault();
        const email = button.dataset.attendeeEmail;
        if (!email) {
            return;
        }

        const label = button.dataset.attendeeLabel || email;
        addAttendeeEmail(email, label);
    });

    if (attendeesQueryInput instanceof HTMLInputElement) {
        attendeesQueryInput.addEventListener("keydown", (event) => {
            const buttons = getAttendeeSuggestionButtons();
            if (buttons.length == 0) {
                if (event.key === "Escape") {
                    clearAttendeeSuggestions();
                }

                if (event.key === "Enter" || event.key === ",") {
                    if (addTypedAttendeeQuery()) {
                        event.preventDefault();
                    }
                }

                if (event.key === "Backspace" && !attendeesQueryInput.value && selectedAttendeeEmails.size > 0) {
                    const lastEmail = Array.from(selectedAttendeeEmails).at(-1);
                    if (lastEmail) {
                        removeAttendeeEmail(lastEmail);
                        event.preventDefault();
                    }
                }

                return;
            }

            if (event.key === "ArrowDown") {
                event.preventDefault();
                const nextIndex =
                    attendeeSuggestionIndex < 0
                        ? 0
                        : (attendeeSuggestionIndex + 1) % buttons.length;
                setAttendeeSuggestionIndex(nextIndex);
                return;
            }

            if (event.key === "ArrowUp") {
                event.preventDefault();
                const nextIndex =
                    attendeeSuggestionIndex < 0
                        ? buttons.length - 1
                        : (attendeeSuggestionIndex - 1 + buttons.length) % buttons.length;
                setAttendeeSuggestionIndex(nextIndex);
                return;
            }

            if (event.key === "Enter") {
                if (attendeeSuggestionIndex >= 0 && attendeeSuggestionIndex < buttons.length) {
                    event.preventDefault();
                    const email = buttons[attendeeSuggestionIndex].dataset.attendeeEmail;
                    if (email) {
                        const label = buttons[attendeeSuggestionIndex].dataset.attendeeLabel || email;
                        addAttendeeEmail(email, label);
                    }
                } else if (addTypedAttendeeQuery()) {
                    event.preventDefault();
                }
                return;
            }

            if (event.key === ",") {
                if (addTypedAttendeeQuery()) {
                    event.preventDefault();
                }
                return;
            }

            if (event.key === "Escape") {
                event.preventDefault();
                clearAttendeeSuggestions();
            }
        });

        attendeesQueryInput.addEventListener("blur", () => {
            window.setTimeout(clearAttendeeSuggestions, 120);
        });
    }

    document.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }

        const removeButton = target.closest(".attendee-chip-remove[data-attendee-email]");
        if (!(removeButton instanceof HTMLButtonElement)) {
            return;
        }

        event.preventDefault();
        const email = removeButton.dataset.attendeeEmail;
        if (!email) {
            return;
        }
        removeAttendeeEmail(email);
    });

    document.body.addEventListener("htmx:afterSwap", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement) || target.id !== "attendee-suggestions") {
            return;
        }
        attendeeSuggestionIndex = -1;
    });

    const tzInput = document.getElementById("recurrence-timezone");
    if (tzInput) {
        const systemTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (systemTz) {
            const hasSystemTz = Array.from(tzInput.options).some((opt) => opt.value === systemTz);
            if (hasSystemTz && (!tzInput.value || tzInput.value === "UTC")) {
                tzInput.value = systemTz;
            }
        }
    }

    syncAttendeeEmailsValue();
    renderAttendeeChips();
})();
