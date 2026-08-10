# Student guide

You write; the tool handles git. Five commands total.

## Setup (once)

1. Install the tool (Python 3.10+; on Windows use WSL):

   ```sh
   pipx install book-cli   # or: pip install book-cli
   ```

2. Clone the course book (URL and your token come from your instructor):

   ```sh
   book clone https://git.example.org/course/book.git
   cd book
   ```

   It will ask for your username. Then put your API token in
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
