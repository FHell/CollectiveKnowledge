#!/usr/bin/env python3
"""Browser test: the discussion on a proposed edit works on the diff page.

Driven by tests/web_e2e.sh, which prepares a built site, a rendered diff
page for change #1, and a running stub forge. Env:

  SITE_URL  — static site under test (python http.server)
  API_URL   — stub forge base (…/api/v1 is appended by the client)

Asserts, in a real (headless) Chromium:
  1. anonymous visitor sees the rendered diff, the review bar, and the
     existing discussion (opening post + bob's comment);
  2. sign-in with a pasted token works;
  3. replying posts to the forge and appears in the thread in place;
  4. request-changes from the review bar lands in the thread too.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from playwright.sync_api import expect, sync_playwright

SITE = os.environ["SITE_URL"].rstrip("/")
API = os.environ["API_URL"].rstrip("/")


def forge_state() -> dict:
    with urllib.request.urlopen(f"{API}/api/v1/repos/class/notes/_state") as r:
        return json.load(r)


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(
            executable_path=os.environ.get("BOOK_E2E_CHROMIUM", "/opt/pw-browsers/chromium")
        )


def main() -> int:
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        # --- 1. anonymous read: diff + review bar + existing thread ---------
        page.goto(f"{SITE}/diffs/pr-1/")
        # rendered diff: inline edits use <ins>, whole-paragraph additions
        # use .bk-diff-insert blocks
        expect(page.locator("ins, .bk-diff-insert").first).to_be_visible()
        expect(page.locator(".bk-reviewbar")).to_contain_text("Change #1")
        thread = page.locator(".bk-thread")
        expect(thread).to_contain_text("alice")
        expect(thread).to_contain_text("opened this change")
        expect(thread).to_contain_text("Step 2 looks wrong to me")  # bob, via API
        expect(thread).to_contain_text("bob")

        # --- 2. sign in with a pasted token ---------------------------------
        page.locator(".bk-authbar .bk-authlink").click()
        dialog = page.locator(".bk-modal")
        dialog.locator("input[type=password]").fill("carol")
        dialog.get_by_role("button", name="Sign in").click()
        expect(page.locator(".bk-authbar")).to_contain_text("carol")

        # --- 3. reply in place ------------------------------------------------
        thread.locator("textarea").fill("I agree with bob — the sign flips in step 2.")
        thread.get_by_role("button", name="Reply").click()
        expect(thread).to_contain_text("the sign flips in step 2")
        expect(thread).to_contain_text("carol")
        state = forge_state()
        bodies = [c["body"] for c in state["comments"].get("1", [])]
        assert any("sign flips in step 2" in b for b in bodies), \
            f"reply not stored on the forge: {bodies}"

        # --- 4. request changes from the review bar shows up in the thread ----
        page.locator(".bk-reviewbar").get_by_role("button", name="request changes").click()
        modal = page.locator(".bk-modal")
        modal.locator("textarea").fill("Please re-derive step 2 before we merge.")
        modal.get_by_role("button", name="Send").click()
        expect(thread).to_contain_text("requested changes")
        expect(thread).to_contain_text("re-derive step 2")
        state = forge_state()
        reviews = state["reviews"].get("1", [])
        assert any(r["state"] == "REQUEST_CHANGES" and r["user"]["login"] == "carol"
                   for r in reviews), f"review not stored on the forge: {reviews}"

        if errors:
            print("page errors:", errors, file=sys.stderr)
            return 1
        browser.close()
    print("WEB DISCUSSION OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
