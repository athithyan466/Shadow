
(() => {
    "use strict";

    const config = document.getElementById("shadow-exam-config");
    if (!config) return;

    const attemptId = config.dataset.attemptId;
    const token = config.dataset.token;
    const terminateOnViolation = config.dataset.terminateOnViolation === "true";
    const timer = document.getElementById("timer");
    const saveStatus = document.getElementById("save-status");
    const submitButton = document.getElementById("submit-exam");
    const questions = [...document.querySelectorAll(".exam-question[data-qid]")];
    const navItems = [...document.querySelectorAll(".nav-item[data-target]")];

    let remaining = Math.max(0, Number(config.dataset.remainingSeconds || 0));
    let finished = false;
    let submitting = false;
    let violationStartedAt = 0;
    let violationTimer = 0;
    let fullscreenWasUsed = false;
    let saveQueue = Promise.resolve();

    const tabId = window.crypto?.randomUUID
        ? window.crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;

    const channel = "BroadcastChannel" in window
        ? new BroadcastChannel(`shadow-exam-${attemptId}`)
        : null;

    const setStatus = (text, bad = false) => {
        if (!saveStatus) return;
        saveStatus.textContent = text;
        saveStatus.classList.toggle("error-text", bad);
    };

    const request = async (path, payload = {}, keepalive = false) => {
        const response = await fetch(`/exam/${attemptId}/${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            keepalive,
            body: JSON.stringify({ token, ...payload })
        });

        let data = {};
        try {
            data = await response.json();
        } catch (_) {}

        if (!response.ok && response.status !== 409) {
            throw new Error(data.error || `Request failed (${response.status})`);
        }

        return { response, data };
    };

    const finishPage = (message) => {
        if (finished) return;

        finished = true;
        document.body.classList.add("exam-finished");

        if (submitButton) submitButton.disabled = true;

        document.querySelectorAll(".exam-question input").forEach(input => {
            input.disabled = true;
        });

        setStatus(message, true);

        window.setTimeout(() => {
            window.location.replace(
                `/result/${attemptId}?token=${encodeURIComponent(token)}`
            );
        }, 1200);
    };

    const reportEvent = async (event, detail = "") => {
        try {
            const result = await request("event", {
                event,
                visibility: document.visibilityState,
                detail
            });

            if (result.data.terminated) {
                finishPage("This assessment has ended because a security rule was triggered.");
            }

            return result.data;
        } catch (error) {
            console.error("Could not report exam event:", error);
            return null;
        }
    };

    const selectedOptions = question => [
        ...question.querySelectorAll(
            "input[type=radio]:checked, input[type=checkbox]:checked"
        )
    ].map(input => Number(input.value));

    const saveQuestion = question => {
        if (finished) return Promise.resolve();

        const qid = Number(question.dataset.qid);
        const optionIds = selectedOptions(question);

        setStatus("Saving answer…");

        saveQueue = saveQueue.catch(() => {}).then(async () => {
            if (finished) return;

            const result = await request("save", {
                question_id: qid,
                option_ids: optionIds
            });

            if (result.response.status === 409 || result.data.error) {
                finishPage(result.data.error || "This attempt is no longer active.");
                return;
            }

            const nav = navItems.find(item => item.dataset.target === question.id);

            if (nav) {
                nav.classList.toggle("answered", optionIds.length > 0);
            }

            setStatus("All changes saved");
        }).catch(error => {
            console.error(error);
            setStatus("Could not save your answer. Check your connection and try again.", true);
            throw error;
        });

        return saveQueue;
    };

    questions.forEach(question => {
        question.querySelectorAll("input[type=radio], input[type=checkbox]").forEach(input => {
            input.addEventListener("change", () => {
                if (finished || submitting) return;

                if (input.type === "radio") {
                    question.querySelectorAll("input[type=radio]").forEach(other => {
                        other.closest(".exam-option")?.classList.toggle("selected", other.checked);
                    });
                } else {
                    input.closest(".exam-option")?.classList.toggle("selected", input.checked);
                }

                saveQuestion(question).catch(() => {});
            });
        });

        question.querySelectorAll("input").forEach(input => {
            input.closest(".exam-option")?.classList.toggle("selected", input.checked);
        });
    });

    navItems.forEach(item => {
        item.addEventListener("click", () => {
            document.getElementById(item.dataset.target)?.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        });
    });

    const formatTime = seconds => {
        const mins = Math.floor(seconds / 60).toString().padStart(2, "0");
        const secs = (seconds % 60).toString().padStart(2, "0");
        return `${mins}:${secs}`;
    };

    const submitExam = async (automatic = false) => {
        if (finished || submitting) return;

        submitting = true;

        if (submitButton) submitButton.disabled = true;

        setStatus(automatic ? "Time is up. Submitting your answers…" : "Saving and submitting…");

        try {
            await saveQueue;

            for (const question of questions) {
                if (finished) return;
                await saveQuestion(question);
            }

            await saveQueue;

            if (finished) return;

            const result = await request("submit", {});

            if (result.data.redirect) {
                finished = true;
                document.body.classList.add("exam-finished");
                window.location.replace(result.data.redirect);
                return;
            }

            if (result.response.status === 409 || result.data.error) {
                finishPage(result.data.error || "This attempt is no longer active.");
                return;
            }

            throw new Error("Submission failed: no result redirect was returned.");
        } catch (error) {
            console.error(error);
            setStatus(`Submission failed: ${error.message}`, true);

            if (submitButton && !finished) submitButton.disabled = false;

            submitting = false;
        }
    };

    if (submitButton) {
        submitButton.addEventListener("click", () => {
            if (window.confirm("Submit your assessment now? You cannot change answers afterward.")) {
                submitExam(false);
            }
        });
    }

    if (timer) {
        const tick = () => {
            timer.textContent = formatTime(remaining);

            timer.setAttribute(
                "aria-label",
                `${Math.floor(remaining / 60)} minutes ${remaining % 60} seconds remaining`
            );

            timer.classList.toggle("timer-warning", remaining <= 60);

            if (remaining <= 0) {
                window.clearInterval(timerInterval);
                submitExam(true);
                return;
            }

            remaining -= 1;
        };

        tick();
        const timerInterval = window.setInterval(tick, 1000);
    }

    const showViolationWarning = () => {
        let overlay = document.getElementById("shadow-violation-warning");

        if (!overlay) {
            overlay = document.createElement("div");
            overlay.id = "shadow-violation-warning";
            overlay.setAttribute("role", "alertdialog");
            overlay.setAttribute("aria-live", "assertive");

            overlay.innerHTML =
                '<div class="security-warning-card"><h2>Security warning</h2><p>Leaving the exam page has been detected. Return to the assessment now. The attempt will end in <strong id="shadow-warning-count">5</strong> seconds.</p></div>';

            document.body.appendChild(overlay);
        }

        return overlay;
    };

    const startViolationGrace = eventName => {
        if (finished || violationStartedAt) return;

        violationStartedAt = Date.now();
        reportEvent(`${eventName}_warning`, "5-second grace period started");

        const overlay = showViolationWarning();
        let seconds = 5;
        const count = overlay.querySelector("#shadow-warning-count");

        if (count) count.textContent = String(seconds);

        violationTimer = window.setInterval(async () => {
            seconds -= 1;

            if (count) count.textContent = String(Math.max(0, seconds));

            if (seconds <= 0) {
                window.clearInterval(violationTimer);
                violationTimer = 0;

                const result = await reportEvent(eventName, "Grace period elapsed");

                if (result?.terminated) {
                    finishPage("Security violation recorded. Ending assessment…");
                } else {
                    violationStartedAt = 0;
                    document.getElementById("shadow-violation-warning")?.remove();

                    setStatus(
                        "Violation recorded. The creator has disabled automatic termination for this test.",
                        true
                    );
                }
            }
        }, 1000);
    };

    const cancelViolationGrace = () => {
        if (!violationStartedAt || finished) return;

        const elapsed = Date.now() - violationStartedAt;

        if (elapsed >= 5000) {
            reportEvent("tab_hidden", "Returned after grace period").then(result => {
                if (result?.terminated) {
                    finishPage("Security violation recorded. Ending assessment…");
                } else {
                    violationStartedAt = 0;
                    document.getElementById("shadow-violation-warning")?.remove();

                    setStatus(
                        "Violation recorded. The creator has disabled automatic termination for this test.",
                        true
                    );
                }
            });

            return;
        }

        violationStartedAt = 0;

        if (violationTimer) {
            window.clearInterval(violationTimer);
            violationTimer = 0;
        }

        document.getElementById("shadow-violation-warning")?.remove();
        setStatus("Please remain on the exam page.", true);
    };

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            startViolationGrace("tab_hidden");
        } else {
            cancelViolationGrace();
        }
    });

    window.addEventListener("blur", () => startViolationGrace("window_blur"));

    window.addEventListener("focus", () => {
        if (!document.hidden) cancelViolationGrace();
    });

    document.addEventListener("fullscreenchange", () => {
        if (document.fullscreenElement) {
            fullscreenWasUsed = true;
        } else if (fullscreenWasUsed && !finished) {
            reportEvent("fullscreen_exit", "Fullscreen mode exited");
        }
    });

    const fullscreenButton = document.getElementById("enter-fullscreen");

    if (fullscreenButton) {
        fullscreenButton.addEventListener("click", async () => {
            try {
                await document.documentElement.requestFullscreen();
                fullscreenWasUsed = true;
                fullscreenButton.hidden = true;
            } catch (_) {
                setStatus(
                    "Fullscreen is unavailable in this browser. Other exam controls remain active.",
                    true
                );
            }
        });
    }

    if (channel) {
        channel.postMessage({ type: "active", tabId });

        channel.onmessage = event => {
            if (event.data?.type === "active" && event.data.tabId !== tabId && !finished) {
                reportEvent(
                    "duplicate_tab",
                    "Another exam tab was opened in this browser profile"
                ).then(result => {
                    if (result?.terminated) {
                        finishPage("Another exam tab was detected. This attempt is being ended.");
                    } else {
                        setStatus("Another exam tab was detected and recorded.", true);
                    }
                });
            }
        };

        window.addEventListener("pagehide", () => {
            channel.postMessage({ type: "leaving", tabId });
        });
    }

    document.addEventListener("selectstart", event => {
        if (
            !finished &&
            event.target.closest?.(".exam-question") &&
            !event.target.closest("input,textarea,select")
        ) {
            event.preventDefault();
        }
    }, true);

    ["copy", "cut", "paste", "contextmenu", "dragstart"].forEach(type => {
        document.addEventListener(type, event => {
            if (!finished && event.target.closest?.(".exam-question")) {
                event.preventDefault();
            }
        }, true);
    });

    document.addEventListener("keydown", event => {
        if (finished) return;

        const key = event.key.toLowerCase();
        const modifier = event.ctrlKey || event.metaKey;

        if (
            (modifier && ["a", "c", "x", "v", "s", "p", "u"].includes(key)) ||
            key === "printscreen"
        ) {
            if (event.target.closest?.(".exam-question")) {
                event.preventDefault();
                event.stopPropagation();
            }
        }
    }, true);

    window.addEventListener("beforeunload", event => {
        if (!finished) {
            const payload = JSON.stringify({
                token,
                event: "page_leave",
                visibility: document.visibilityState,
                detail: "Page is being unloaded"
            });

            try {
                if (navigator.sendBeacon) {
                    navigator.sendBeacon(
                        `/exam/${attemptId}/event`,
                        new Blob([payload], { type: "application/json" })
                    );
                }
            } catch (_) {}

            event.preventDefault();
            event.returnValue = "Your exam is in progress. Leaving may end your attempt.";
        }
    });

    setStatus("Answers save automatically.");
})();