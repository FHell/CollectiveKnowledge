# Student guide

Your **ORCID iD is your account** — there is nothing else to register.
You write; the tool handles git. Five commands total — or no commands
at all: on the published book site, **Sign in with ORCID**
(bottom-right), tap any paragraph, and use ✏️ **edit** to propose a
change straight from the browser. It becomes a change under review
exactly as if you had used the CLI below.

## Setup (once)

1. **Sign in with ORCID** — on the published site or the course forge
   (link from your instructor). No ORCID iD yet? Get one free at
   https://orcid.org/register. Your first sign-in creates your forge
   account (username = your ORCID iD) and asks once for an email
   address.

2. For the CLI, install the tool (Python 3.10+; on Windows use WSL):

   ```sh
   pipx install book-cli   # or: pip install book-cli
   ```

3. Generate a token for the CLI: on the forge, *Settings →
   Applications → Generate token* (repository + issue read/write).
   Then clone and configure:

   ```sh
   book clone https://git.example.org/course/book.git
   cd book
   ```

   It will ask for your username (your ORCID iD). Put the token in
   `~/.config/book/config.toml` so submitting works:

   ```toml
   [forgejo]
   token = "YOUR_TOKEN_HERE"
   ```

   (Alternatively set the environment variable `BOOK_TOKEN`.)

## Making a change

```sh
book change new "fix-derivation"     # start a change (do this first!)
# … edit files under chapters/ with any editor …
book save -m "fix sign error in the derivation"
book submit
```

`book submit` prints two links: the change page (where discussion happens)
and the rendered diff (a page showing exactly what you changed, with math
typeset — it appears about a minute after you submit).

That's it. If the instructor asks for revisions, edit again, then
`book save` and `book submit` — the same change updates.

## Discussing your change

The conversation about a change lives with the change — readable by
everyone on its diff page, answerable there when signed in, and equally
from the CLI:

```sh
book comments 1                      # read the discussion on change #1
book comment 1 -m "Good point — fixed in the new version."
```

## Useful extras

```sh
book diff main          # what did I change? (in the terminal)
book diff main --render --open   # …as a rendered page with typeset math
book changes            # list all open changes in the course
book change list        # list my local change branches
book change switch NAME # go back to another of my changes
book log                # recent history
```

## Rules of the road

- Always start with `book change new` — you cannot push to `main` directly.
- One topic per change; small changes get reviewed faster.
- `book save` early and often; only `book submit` makes it public.
