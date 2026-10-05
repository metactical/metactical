// Entry for the /trackerv2 website page. Same Vue component as the desk page (/app/time-clock),
// but employees do not need desk access: this page carries its own login form, like /tracker.
import TimeClock from "./components/time_clock/TimeClock.vue";
import { createApp } from "vue";

function renderLogin(root) {
    root.innerHTML = `
        <form class="tc-card tc-login" autocomplete="on">
            <div class="tc-card-title">Time Clock</div>
            <label>Email address
                <input type="text" name="usr" autocomplete="username" required autofocus />
            </label>
            <label>Password
                <input type="password" name="pwd" autocomplete="current-password" required />
            </label>
            <div class="tc-warn" hidden></div>
            <button type="submit" class="tc-action tc-action-in tc-login-btn">Log in</button>
        </form>`;

    const form = root.querySelector("form");
    const warn = form.querySelector(".tc-warn");
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        warn.hidden = true;
        const btn = form.querySelector("button");
        btn.disabled = true;
        try {
            const res = await fetch("/api/method/login", {
                method: "POST",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({ usr: form.usr.value, pwd: form.pwd.value }),
            });
            if (!res.ok) throw new Error("Invalid email or password.");
            window.location.reload();
        } catch (err) {
            warn.textContent = err.message || "Could not log in. Please try again.";
            warn.hidden = false;
            btn.disabled = false;
        }
    });
}

frappe.ready(function () {
    const root = document.getElementById("time_clock_ui");
    if (!root) return;
    if (frappe.session.user === "Guest") {
        renderLogin(root);
    } else {
        createApp(TimeClock).mount(root);
    }
});
