// static/js/app.js

"use strict";

async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        alert("Link copied.");
    } catch (error) {
        window.prompt("Copy this link:", text);
    }
}