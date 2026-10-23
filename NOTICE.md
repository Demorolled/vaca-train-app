# Build notice — VACA is in reconstruction

**Status:** active reconstruction · **Model:** retraining from a clean base ·
**Harness, corpus and gate:** open and in this repository

## Why the build is being rebuilt

VACA's training loop was poisoned by an outside source. Corrupted examples
entered the pipeline and the model absorbed them — not as a bad answer here or
there, but as a bend in how it wrote code at all.

We did not take that lying down. The first response was surgery: find the bad
rows, prune them, retrain on what was left. It worked for a while, and then it
didn't. The damage had already been folded into the weights, so removing the
examples removed the symptoms and left the cause. Each new round of training
found the same bend again, and each repair held for one cycle before slipping
back. Pruning was treating a wound that had gone internal.

So we stopped repairing and started over. VACA now trains from a clean base,
and the pipeline behind it is built to make the same failure loud instead of
quiet: only behaviour-verified work becomes a training row, candidates are
judged on programs held out of training entirely, and a repair that cannot be
measured on a fresh pool is not promoted — however good the story is.

Starting over is not a step backwards. It is the reason the next build is the
best one yet.

## What the new build brings

### Reverse anything

The new VACA can work **backwards**. Hand it an app, a file, or a finished node
tree and it reconstructs the plan, the structure, and the steps that produced
it — the map behind the build rather than another guess at the destination.
Learn from something that already works, re-derive it in your own stack, or pull
a finished app apart to see exactly how it holds together.

### Dual LLM connections, with real controls

VACA now supports **two model connections side by side**, each with its own
setup and controls. Reasoning, scaffolding, planning and generation can be
routed to whichever model you choose for the job — a fast model for the scaffold,
a deeper one for the architecture, or the same pair swapped per task.

That is not a convenience feature, it is a quality one: two different minds
attacking the same build produce **more diverse** results, and diversity is what
keeps a build from collapsing into one model's habits.

### Drag and drop, and a second tree

The newest build offers **drag-and-drop node trees**. Drop something into VACA
and it can grow a **new tree alongside the one you are working in** — your
current build stays exactly where it is while a second tree takes shape next to
it. Compare, borrow, merge, or keep them apart and see where each one goes.

The point is freedom of movement: your work is no longer one linear stack you
have to protect. It is a workspace, and you can put anything next to anything
else and watch what happens.

## What stays true while we rebuild

- **Verified or it doesn't count.** A fix is proven by running it again with a
  real toolchain; only verified behaviour becomes training data.
- **Measured on held-out programs.** Candidates are scored on whole program
  families kept out of training, and promoted only when the gain survives
  pairing — never on the numbers that flatter them.
- **No hidden phases.** The harness, the corpus, the probes and the gate are all
  in this repository, with the tests that guard them.

## While reconstruction is underway

Expect movement — files, adapters and numbers will change as the clean base is
rebuilt. The direction will not: a coder that proves its work, a pipeline that
cannot be quietly poisoned, and a workspace that lets you build in more than one
direction at once.

Thank you for watching the rebuild. The best version of VACA is the one being
built right now.
