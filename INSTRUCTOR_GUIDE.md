# Instructor guide

Two ways to review: from the CLI (full control, can edit the change), or
entirely in the browser (any machine).

## CLI workflow

```sh
book changes                 # list open changes (number, author, title)
book review 12               # fetch change #12, open its rendered diff
```

`book review` checks out the change locally (branch `review/pr-12`) and
opens the rendered AST diff against `main` — insertions green, deletions
red, changed math symbols highlighted inside the typeset formula.

Then one of:

```sh
# ask for revisions:
book request-changes 12 -m "the second step skips a sign flip"

# or fix it yourself first:
#   … edit files …
book save -m "tighten wording"
book push-review 12          # your edits land on the student's change

# and approve:
book approve 12 --vouch --note "checked derivation"
```

`book approve` merges with a **merge commit** (never squash — squashing
would destroy per-paragraph authorship), pulls `main`, and with `--vouch`
records your endorsement of every changed paragraph in
`meta/vouches.yaml`, committed and pushed. Vouches are keyed by paragraph
content hash, so they go stale automatically if the text changes later.

CI rebuilds and redeploys the public book on every merge.

## Web-only workflow (browser, any machine)

1. Open the Forgejo repo → *Pull requests*. Each change is a PR.
2. The CI bot comments a **Rendered diff** link on every PR — that page is
   the same AST-level diff the CLI shows.
3. Discuss in PR comments; use *Request changes* in the review dropdown.
4. Merge with the **Create merge commit** button (not squash).
5. The live book updates automatically about a minute after the merge.

The only thing the web workflow cannot do is vouch (vouches live in git,
not in Forgejo). Vouch later from any checkout:

```sh
git pull && book vouch chapters/03-heat-equation.md --note "verified"
git push
```

## Occasional tasks

```sh
book blame chapters/03-heat-equation.md   # who wrote each paragraph
book build                                # local preview in _build/html/
```

Operations (accounts, tokens, runner, deployment) are covered in
`infra/README.md`.
