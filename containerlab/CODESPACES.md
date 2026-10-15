# Running the lab in GitHub Codespaces, from a fresh machine

This is a guide for getting the containerlab BGPsec lab running when you have
nothing set up. All you need is a browser and access to Github.

This file will not be shown to students
## What you need before starting

- A GitHub account that can see `will-elsen/bgpsec_module`. If the repo is
  **private**, "can see" means owner or invited collaborator — check that
  the repo page loads in your browser while signed in.
- The repo's `lab-images` release (see the next section). Without it the
  Codespace still works, but builds the router images from source.
- Codespaces quota. The free personal tier includes 120 core-hours and
  15 GB-months of storage per month; this lab's 4-core machine therefore
  gives roughly 30 hours of runtime. No payment method is needed within
  that.

Nothing is installed locally. Docker, containerlab, Python, and the lab's
router images all live inside the Codespace.

## One time, after the first push: publish the image release

The `postCreate` script downloads the router images from the `lab-images`
release of **the repo the Codespace runs from**. A newly created GitHub repo
has no releases, so publish one once, from a clone on a machine with `gh`
signed in:

```bash
bash containerlab/lab/tools/publish_images.sh            # or: ... owner/repo
```

It uploads `containerlab/lab/dist/bgpsec-lab-images.tar.gz` (gitignored, so
fetch it first from an existing release with `gh release download lab-images
--repo <old-repo> --dir containerlab/lab/dist`), or saves a fresh bundle
from the local `bgpsec/*:local` images when that file is absent. It checks
that all four images are in the bundle before uploading, and re-running it
replaces the asset. Re-publish whenever the images are rebuilt.

## Creating the Codespace

1. Open the repo on github.com → **Code → Codespaces → Create codespace on
   main**. If you are offered a machine size, pick **4-core** (the
   devcontainer requests 4 CPUs / 8 GB / 32 GB and GitHub will default to a
   machine that satisfies that).
2. The editor opens while setup continues in a terminal panel. Setup has two
   parts:
   - the devcontainer image (containerlab + docker-in-docker, with the
     GitHub CLI added) — a minute or two;
   - the `postCreate` script, which installs the notebook's Python packages,
     downloads the ~260 MB router-image bundle from this repo's `lab-images`
     release, loads it into Docker, and pre-pulls the three RPKI-plane
     images from Docker Hub — about 3–5 minutes on the happy path.
3. Wait for the terminal to print
   `=== done — open bgpsec_lab_exercise.ipynb and run it from the top ===`.
   Opening the notebook before that line appears is the classic mistake:
   cells fail on missing images that were still downloading.
4. Open `bgpsec_lab_exercise.ipynb`, pick the **Python 3** kernel when VS
   Code asks, and run from the top. The first cell is a preflight that
   checks the environment and names the specific fix for anything missing.

If the release download fails (no auth, GitHub API hiccup, network), the
script says so and falls back to building the four images from the vendored
source — that also works, it just takes ~20 minutes instead of ~5.

## Verifying the setup

From the Codespace terminal:

```bash
docker images --filter=reference='bgpsec/*'
# four images, all tagged :local — quaggasrx, gobgpsrx, srx-server, tal-share

containerlab version        # installed by the devcontainer image

cat containerlab/lab/phase4/keys/ski-list.txt
# six ASN-SKI lines — the key vault, built by the bootstrap from the tracked keys
```

Then run the notebook's preflight cell. If both look right, the lab will
deploy.

## When something goes wrong

The bootstrap is idempotent — the fix for almost every setup failure is:

```bash
bash .devcontainer/postCreate.sh
```

It skips what already succeeded, re-downloads anything corrupt, and ends by
telling you whether the images are in place.

| Symptom | Cause | Fix |
|---|---|---|
| `done` never printed, download errors in the log | network/GitHub hiccup during the 260 MB download | re-run the script; it retries and falls back to a source build |
| notebook cells fail with missing `bgpsec/*` images | notebook opened before setup finished | wait for setup, re-run the script if needed, then re-run the cell |
| `lab.deploy()` fails: `Failed to verify bind path … phase4/keys` | the key vault was not built (bootstrap predates it, or that step failed) | `bash containerlab/lab/tools/build_vault.sh`, then `lab.deploy()` again |
| sessions up but **no routes move** after resuming a stopped Codespace | containerlab's virtual wires do not survive stop/resume; everything looks green | re-run the `lab.deploy()` cell — full clean rebuild, 2–3 min |
| a lab container was restarted with `docker restart` | same silent wire loss | `lab.deploy()` again; never `docker restart` lab nodes |

That third row is **the one rule of Codespaces** for this lab: idle
Codespaces stop automatically after ~30 minutes, and every resume needs a
fresh `lab.deploy()` before anything will route.

## Quota hygiene

- **Stop** the Codespace when you finish a session (github.com → Codespaces
  → ⋯ → Stop, or let the idle timeout do it). Stopped Codespaces burn no
  core-hours but still count against storage.
- **Delete** it when you are done with the module entirely. Everything worth
  keeping should be committed and pushed first — a deleted Codespace takes
  its uncommitted work with it.

## Working from desktop VS Code instead of the browser

The browser editor is fully capable of running the lab, but if you prefer a
desktop: install VS Code and its **GitHub Codespaces** extension, sign in,
and connect to the same Codespace (or create one from there). The Codespace
is identical either way; only the window is local.

## No Codespaces at all: the local alternatives

Two options, both needing more than a browser:

- **Local dev container.** A machine with Docker and VS Code's Dev
  Containers extension can run this same devcontainer from a clone: clone
  the repo, run `gh auth login` first (without it the private release asset
  cannot be downloaded and the script builds the images from source), then
  "Reopen in Container".
- **Bare Linux/WSL2.** No container wrapper at all — Docker + containerlab
  installed directly (`containerlab/quick-setup.sh` does both on a fresh
  machine), images loaded from the release or built with
  `containerlab/lab/build-images.sh`. The "Running it locally" section of
  `Task-bgpsec-lab.md` walks through it.
