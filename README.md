# Train App

> **Build notice:** VACA is in active reconstruction after an outside source
> poisoned the training loop. The harness and the corpus are rebuilt and running
> **now** — see [Run it](#run-it-linux-and-windows) and then
> [give it more than one model](#give-it-more-than-one-model) before you judge a
> build. The model itself is retraining from a clean base; the notice is
> temporary and comes down after December.
> [Read the full notice →](NOTICE.md)

A small, standalone implementation of the 80/20 architecture: a
**language-agnostic harness** that runs code, hands the real error to a local
LLM, proves the fix by running it again, and turns only **verified** fixes into
LoRA training rows.

```
node file ──▶ harness runs it (real toolchain)
                  │
          fails ───┴─── passes
            │            └─▶ done
            ▼
   LLM gets: file + command + platform + exit code + output
            │
            ▼
   harness writes the reply back and runs it again
            │
      passes ─┴─▶ captured to dataset/corrections.jsonl ──▶ QLoRA on the agent box
```

The harness contains **zero** language semantics. It knows three things per
language: the executable that proves the toolchain is installed, the argv that
compiles/parses the file, and the argv that runs it (`trainapp/execution.py`).
Everything language-specific comes from the model and from the RAG/library side
of the stack, exactly as the memo describes.

## Quick start

```bash
cd ~/Desktop/vaca-train-app
./run.sh --open          # http://127.0.0.1:8137
```

No virtualenv, no pip install: the app is Python standard library only. The
trainer it launches (`train_lora.py`) is the one part that needs torch,
transformers, peft and datasets — and it runs on the GPU box, not here.

## What each piece is

| file | role |
|---|---|
| `trainapp/execution.py` | Execution Schema Layer — per-language binaries, check/run argv, per-OS install hints, honest failures |
| `trainapp/repair.py` | The only intelligence loop: run → prompt → fix → run → prove |
| `trainapp/capture.py` | Verified-fix capture, dedupe, hash-based train/val export |
| `trainapp/training.py` | Dataset export + one training job at a time, on the agent box or locally |
| `trainapp/library.py` | Ingests VACA's code-bible (904 chunks), Rosetta corpus (313 programs), curated patterns (6) |
| `trainapp/validate.py` | Proves every snippet with the real toolchain; typed statuses, no guesses |
| `trainapp/judge.py` | Larger-model judge with a deterministic gate in front of it |
| `trainapp/tournament.py` | 7 styles per task → execute → measure → judge → winner + preference pairs |
| `trainapp/preferences.py` | Collects every run's judged pairs, dedupes, hash-splits train/val (ORPO rows) |
| `trainapp/battery.py` | Scores a coder (or an adapter) by compiling and running held-out tasks |
| `trainapp/probes.py` | Contract gate: the boundary probes a round must not regress on (fences, scaffolds, reasoning lanes) |
| `trainapp/localcoder.py` | Serves an HF model ± a PEFT adapter behind the same `complete()` seam |
| `trainapp/grow.py` | Grows the library from judged, measured, verified improvements only |
| `trainapp/band.py` | The band: any number of connections, a toggle and a seat each, one leading; copies every build whole |
| `trainapp/board.py` | The blackboard: one shared board, four owned sections, a read/write policy per seat, a filtered view per call |
| `trainapp/orchestra.py` | Four seats — architect, tech lead, developer, QA — write one app; bounded repair loop, toolchain last |
| `trainapp/harvest.py` | Reads every finished build copy, logs the run, adds verified builds to the library, cuts a monthly sheet |
| `trainapp/relay.py` | A seat a person answers by hand, for models with no endpoint and no key |
| `trainapp/server.py` | HTTP API + static UI, stdlib only |
| `trainapp/static/` | The canvas: nodes, editor, harness console, toolchains, dataset, training |
| `train_lora.py` | QLoRA SFT over `{instruction, input, output}` JSONL |

## Supported languages

`python`, `javascript`, `typescript`, `go`, `rust`, `c`, `cpp`, `java`, `ruby`,
`php`, `csharp`, `kotlin`, `swift`. Each has a compile/parse check plus a run
step, except TypeScript, which runs through Node's type stripping and has no
check gate yet (stated in the toolchain panel, not hidden).

### The five lanes (`focus`)

The executor still builds and runs all thirteen languages, but the corpus the
model is trained and measured on is scoped to five lanes, declared once in
`trainapp/focus.py`:

| lane | identifiers | rows | judgeable sets |
|---|---|---|---|
| JavaScript/TypeScript | `javascript`, `typescript` | 1513 | 78 |
| Python | `python` | 278 | 31 |
| Go | `go` | 297 | 21 |
| Java | `java` | 249 | 8 |
| C | `c` | 240 | 4 |

`library.load_tasks()` applies the filter, so every consumer — SFT rows, plan
and scaffold rows, the probe pool, the gate, the growth loop, the scoreboard —
sees one scope. The sheet on disk keeps every row it was built with:
`load_tasks(all_languages=True)` still returns all 4340, so the cut is an edit to
`LANES` and a rebuild, not a lost corpus.

Three things to know before changing it:

- **Families need siblings in the lanes.** A family needs two in-focus sets
  before its score means anything. The cut initially dropped 13 families whose
  only siblings were in a dropped language, so the five multi-language programs
  got Java and C implementations (`clisets/java.py`, `clisets/c.py`): the pool is
  now 28 families / 112 scored sets over 167 verified sets, and each of the five
  programs has all five lanes.
- **PHP is out.** Its 257 rows stay in the sheet; its lane, and the
  WordPress/web-long-tail coverage that came with it, do not.
- **TypeScript and JavaScript share one lane.** They are the same job on the same
  platform, so a family's siblings may be written in either and still count as
  separate demonstrations.

Two languages need more than an argv list, and the schema now carries it:

- **C#** — `dotnet build` refuses a directory with no project. `run_node`
  scaffolds a throwaway `.csproj` that compiles the file by absolute path
  (`ImplicitUsings` on, `TreatWarningsAsErrors` off), with the target framework
  read from `dotnet --version`, so Main, `namespace`-wrapped Main and top-level
  statements all run. The source directory is never touched.
- **Java** — the launcher takes a class name, so the file is written as
  `<PublicClass>.java` (`execution.source_stem`) instead of `candidate.java`,
  and the run step launches `execution.java_main_class` — the class that
  declares `main`, package-qualified when the source has a `package` line.
  Without that, every Java entry failed with
  `ClassNotFoundException: candidate` — 29 false failures, 13 of them real
  programs once fixed, plus packaged ones like `package programas;` that now
  resolve as `programas.IterativeFactorial`.

Adding a language is still a data edit: append a `Toolchain` with its
extensions, binary candidates, check/run argv and install hints.

## Capture rules (why the dataset stays clean)

A row is written only when **all** of these hold:

1. the file failed the real toolchain before the edit;
2. the model's reply actually changed the file;
3. the same argv then exited 0;
4. the output is not empty, fenced, oversized, or identical to the broken file;
5. the `(instruction, output)` pair is not already in the sheet.

A failed fix is discarded, and a no-op rewrite is reverted. This is the guard
against the poisoning loop that unverified capture creates.

## Library, validation, and the style tournament

### What is in the library (measured, not estimated)

| source | tasks | shape |
|---|---|---|
| `data/code-bible/*.py` | 904 | TypeScript/React chunks (`iface` + `code`); compile-checked |
| `backend/src/knowledge/rosettaCorpus.json` | 313 | standard-library programs; executed |
| `backend/src/knowledge/curatedLanguagePatterns.ts` | 6 | Rust/C++/Go/Java idioms, extracted by importing the module |
| `trainapp/basebuilds/` | **1,300** | 100 elementary programs per language, generated and toolchain-proven |
| `trainapp/mediumbuilds/` | **1,300** | 100 multi-function programs per language, generated and toolchain-proven |
| VACA exports (`appcorpus.py`) | 448 | multi-file app sets (see below) |
| **total** | **4,275** | 13 languages, 3,855 proven by a real toolchain |

Ingest with `python3 -m trainapp.validate --build`, or the **Ingest** button.

### Validation result on this machine

| corpus | verified | other |
|---|---|---|
| TypeScript chunks (tsc 5.9.3, `--noEmit`) | **882 / 904** | 22 failed |
| Rosetta/curated/grown programs | **215 / 323 (67%)** | 86 failed, 21 components, 1 timeout |
| base builds | **1,300 / 1,300** | — |
| medium builds | **1,300 / 1,300** | — |
| app file-sets (scaffold) | **158 / 448 (35%)** | 290 failed |
| **total** | **3,855 / 4,275 (90%)** | 398 failed, 21 components, 1 timeout |

By language (verified): c 217, cpp 226, csharp 232, go 235, java 221, kotlin 232,
php 234, python 229, ruby 230, rust 235, swift 217, typescript 1,128,
javascript 219.

A Rosetta entry is not automatically a *program*: `fun oneHundredDoors()`,
`static string Reverse(...)` and `int[] a = {1, 2};` all compile, but none of
them is launchable on its own. Those are now `component` — compiled with the
real check step, never run, never a seed. Before that status existed they were
counted as verified programs, which is how unlaunchable snippets ended up in
tournament seed lists and in every battery skip (21 of them).

Selection follows the proof, not the guess: the `runnable` flag is set at ingest
(every Rosetta row claims true), so the battery used to pick files that could
only ever be skipped. It now requires a `verified` validation record, and the
tournament's `confirmed()` already did.

Every remaining failure is a real one: programs that need a console
(`Console.ReadLine` under a closed stdin, `readLine()!!`), interactive loops,
WinForms imports, Java 21 preview syntax (implicit classes need
`--enable-preview`), or chunks whose `iface` is documentation rather than
TypeScript. Nothing is marked verified without the toolchain agreeing.

### Multi-file scaffold tasks (real app exports)

A single file cannot show a scaffold: whether a module imports a sibling that
exists, whether a launcher finds the class another file declares, whether two
files define the same symbol. VACA's 502 real exports under
`backend/exports/*/_training.json` are that shape, and `trainapp/appcorpus.py`
turns each into one **multi-file task**: the whole file set plus a `target` (the
file a model is asked to write while the others are given as context).

```bash
python3 -m trainapp.appcorpus --dry-run   # what would be ingested
python3 -m trainapp.appcorpus             # write data/library/app_tasks.jsonl
```

| | count |
|---|---|
| exports scanned | 502 |
| tasks ingested (`origin: vaca-export`, `category: scaffold`) | **448** |
| verified as a set | **158 (35%)** |
| adherence on the verified sets | **0.983** |

54 exports contributed nothing: no source files left after filtering drafts and
build output, or a target identical to one already ingested. The 290 failures
are real, not gate noise — the dominant classes are TypeScript imports of a
package the export never shipped (58 × TS2307, mostly `react`/`deno`), further
tsc errors inside sibling files (41), and C#/Java sources that do not compile
(11 × `CS…`). They stay `failed` and never enter a battery or a seed list.

**Grading** is two-part, because either half alone lies:

1. `execution.run_files()` writes the whole set to a scratch dir and builds it
the way the toolchain does — all sources together (Go package, `javac *.java`,
`dotnet` project, one `gcc`/`g++` link, `kotlinc`, `swiftc`) or entry + siblings
(python, js, php, ruby). TypeScript is **typechecked** with `tsc --noEmit` and a
documented globals shim, so a set that passes is one the export pipeline can
compile. `cargo` projects are refused rather than silently half-built.
2. `trainapp/adherence.py` scores the set the way VACA's scaffold experiment
does: `exports_declared` (entry files exempt), `sibling_imports_ok`,
`no_phantom_imports` (decided by a `package.json` in the set, or allowed when
there is none), `declares_code`, `imports_resolve` (Go module paths, Java/C#
namespaces, Rust `mod`), `no_prose_leak`, `not_stub`.

`validate.py` records both (`adherence`, `adherence_failures`, `file_count`) and
the battery mixes scaffold tasks with single-file ones: siblings go into the
prompt, the returned file replaces the target, and the whole set is rebuilt.
Tournaments and the growth loop ignore sets — they restyle one program, and a set
has no single program to restyle.

### Puzzle scoring: the app's own discrimination test

The VACA Puzzle-RAG trainer on the agent box
(`visual-ai-architect/scripts/puzzle_trainer.py`) turns exports into puzzles —
the correct node, a subtle mutation of it, and a same-purpose node from another
app — and made a *model* play them, rewarding leaner-and-faster rewrites. The
design is reusable; the player is not. `trainapp/puzzles.py` keeps the generator
and replaces the player with the builder itself:

1. **chunk** a file set into nodes (functions, arrow consts, classes, CSS rules,
   HTML blocks, Python `def`/`class`), each with a span that splices back
   exactly, and classify its purpose (database, ui-render, game-logic,
   event-handler, state, styling, layout, input, output, util);
2. **build three candidates**: the real node, one subtle mutation from the
   trainer's operator table (comparison / boolean / off-by-one / API, retried
   until the code actually changes), and a same-purpose node from a **different
   app in the same language**;
3. **substitute and build** the whole set for each candidate;
4. **read the verdict off the build**, not off a model:
   - correct node that fails to build → a real defect in the export;
   - mutation caught by the compiler or by a changed stdout → a strong puzzle;
   - mutation that builds *and* behaves identically → a **weak exemplar**: nothing
     in that node is load-bearing, so copying it teaches nothing.

```bash
python3 -m trainapp.puzzles --tasks 8 --max-nodes 3 --language typescript --to-library
```

First real run (8 TypeScript apps, 9 chunked nodes): **9/9 sets built, 6/9
mutations caught, 9/9 cross-app decoys caught, mean clean 0.928**; a Python
sample (10 apps, 12 nodes) scored **0.925** with the same shape. The three
surviving mutations are the interesting part — a `state` mutation and two
`database` mutations that the output cannot see, i.e. code that is correct but
not load-bearing.

The per-app rollup (`clean` = mean of builds, behaviour stability, mutation
caught, adherence, decoy caught) is merged into
`data/library/puzzle_scores.jsonl` and surfaced by `library.stats()` and
`/api/library` as `puzzle_scored`. That ranking is what an exemplar-aware
retrieval should sort by: the library currently stores everything that compiles,
and this is the first number that says which of those files are worth learning
from.

Known limits, measured rather than guessed: the chunker only understands
JS/TS/CSS/HTML/Python, so Go/Rust/Java/C# sets contribute no nodes; TypeScript
puzzles are graded by `tsc` only (no runtime stdout, so "behaviour" there means
"still typechecks"); and a sample of 8 apps yields ~9 nodes, so a library-wide
ranking needs a much larger sweep than the two samples run here.

### Base builds: 100 elementary programs per language

The library had idioms, app sets and grown variants but very little of the
ground floor: a small program that prints a known result. `trainapp/basebuilds/`
generates ten templates (sum, factorial, fibonacci, primes, gcd, vowels, reverse,
sort, min/max/mean, times table) with ten parameter variants each, for every
language VACA can build:

```bash
python3 -m trainapp.basebuilds --dry-run        # counts per language
python3 -m trainapp.basebuilds                  # write data/library/base_builds.jsonl
python3 -m trainapp.validate                    # prove them (this is the gate)
```

| | result |
|---|---|
| programs generated | **1,300** (100 × 13 languages) |
| verified by compile + run | **1,300 / 1,300** |
| languages | c, cpp, csharp, go, java, javascript, kotlin, php, python, ruby, rust, swift, typescript |

Every program is standard-library only, deterministic, prints a result, reads no
stdin, touches no files, network or clock, and is unique in code — the test suite
asserts each of those properties per language, because a corpus that stalls on
`input()` is worse than no corpus at all.

**A validator bug this exposed:** the first pass verified 1,200/1,300, with all
100 TypeScript programs failing on "Duplicate function implementation" and
"Cannot redeclare block-scoped variable". The tsc *batch* compiles many files as
one program, which is right for the code-bible chunks (components, checked for
compiling at all) and wrong for independent runnable programs. Runnable
TypeScript now goes through the single-file path, and the 100 verify cleanly —
the failure was the harness, not the programs, and it would have silently
rejected any future corpus of small TypeScript programs.

### Curriculum: basic → medium → scaffold

The library is now big enough that mixing it hurts: a 20-line program and a
400-line app set teach different things. `trainapp/curriculum.py` splits it into
three stages with one rule for moving up:

| stage | data | proven | goal |
|---|---|---|---|
| `basic` | 1,300 base builds | **1,300** | compile and print the right answer in one file |
| `medium` | 1,623 (1,300 medium builds + 323 Rosetta/curated) | **1,515** | a complete small program with real logic, compactly |
| `scaffold` | 448 app file-sets | **158** | one file that fits its siblings and keeps the app building |

```bash
python3 -m trainapp.curriculum --plan        # stage, data, exit condition, next command
python3 -m trainapp.curriculum --coverage    # per stage and per language
python3 -m trainapp.curriculum --record runs/battery/X/summary.json
python3 -m trainapp.curriculum --advance     # only if the plateau rule agrees
```

**Efficiency** is one number per evaluation: `verify_rate − bytes/2000 −
ms/400`, so a model that compiles everything but doubles in size does not look
like progress. **The plateau rule** needs at least three evaluations on the
current stage and a gain under 0.01 across them; only then does `--advance` move
to the next stage and reset the round counter. State and an append-only history
live in `data/curriculum/`, so a long run resumes and every advance is auditable.
This is the "stop when the LLM and judge stop improving" control — it is a
decision function, not a scheduler: the battery run that feeds it is explicit.

### Replacing the old adapters (clean model)

The adapters already on the box were trained before the capture gates existed and
there is no record of which files went into which one. `trainapp/cleanmodel.py`
is the replacement path: a manifest of exactly the proof-gated sheets (rows plus
a digest per sheet), and a registry that separates `clean` / `candidate` /
`deprecated` adapters.

```bash
python3 -m trainapp.cleanmodel --manifest data/models/clean1
python3 -m trainapp.cleanmodel --register clean1 data/models/clean1 --status candidate
python3 -m trainapp.cleanmodel --deprecate orpo1 "trained before capture gates"
python3 -m trainapp.cleanmodel --commands data/models/clean1
```

`orpo1` and `orpo2` are registered as deprecated with that reason. The clean
adapter itself (`clean1`: SFT on the 290/34 sheet, then the fresh pair set, then
a head-to-head battery) is queued behind the running tournament and the orpo3
chain in `/tmp/clean-llm-chain.sh` — it starts when the box frees, writes the
manifest before training, and registers the result as a `candidate`, not as a
replacement.

### Medium builds: the rung above base builds

`trainapp/mediumbuilds/` generates 100 programs per language that are *not* one
loop and a print: a record type, a dictionary, a matrix, a stack with a
push/pop/peek contract, or an account with a refusal path, each built from ten
templates over ten datasets (five over twenty in C++, C# and Java), and each
with at least three functions plus a data structure passed between them. Same
hard constraints as the base builds —
stdlib only, no stdin/files/network/clock/randomness, deterministic output.

```bash
python3 -m trainapp.mediumbuilds --dry-run   # 100 each for all 13 languages
python3 -m trainapp.mediumbuilds             # write the sheet
python3 -m trainapp.validate                 # compile + run; this is the gate
```

| | result |
|---|---|
| programs generated | **1,300** (100 × 13 languages) |
| verified by compile + run | **1,300 / 1,300** |
| languages | c, cpp, csharp, go, java, javascript, kotlin, php, python, ruby, rust, swift, typescript |

Every program is in `data/library/medium_builds.jsonl` with a `verified`
validation record, so the curriculum's `medium` stage now draws on them (1,515
proven tasks) instead of only the 215 Rosetta programs. `mediumbuilds.missing()`
still names any language without a module and the contract refuses to invent
counts for it, so a partial corpus cannot be mistaken for a complete one.

The gate rejected 190 of the first 1,300, and every rejection was a generator
defect rather than a corpus limit: a C++ matrix loop, Java class-body syntax in
inventory/ledger/stack, PHP's linked-list splice nesting `[@LIST@]` into a
single array node, C# word-frequency printing `${row.Key}` without an opening
`$"`, and Rust `ranked`/`longest` returning borrowed values with no named
lifetime. Fixing the generators took the corpus to 1,300/1,300; nothing was
marked verified without the toolchain agreeing.

### Scoreboard

`python3 -m trainapp.server` then open **http://127.0.0.1:8137/scoreboard**
(or `curl /api/scoreboard` for JSON; `python3 -m trainapp.scoreboard` prints the
same thing as text). It reports, live: per-language coverage (tasks, proven,
rate, base builds, file sets, puzzle-scored apps) with a toolchain dot; task
provenance; every training sheet's row count; the exemplar ranking from the
puzzle scorer; and the state of the tournament, validation run and training job.
Auto-refreshes every 15 s.

### SFT rows from VACA's captures

VACA captures each tsc-clean export as `{instruction, input, output}` rows whose
instruction already contains the request, the intent and the planned file list.
Those are training data the trainer can consume without conversion, so
`capture.py` imports them into their own sheet and merges both sheets at export:

```bash
python3 -m trainapp.capture --import-vaca   # 84 rows imported, 40 rejected (instruction > 4 000 chars)
python3 -m trainapp.capture --export        # 214 corrections + 84 VACA = 254 train / 31 val
```

Before this, `train.jsonl` held **1 row** while `corrections.jsonl` held 209
verified ones — the export had never been re-run, so the SFT path was training on
a single example.

**Swift corpus repair.** 9 of the 31 Swift rows still used `println(`, removed
in Swift 3; that is now `print(` — 15 calls, in the corpus itself
(`rosettaCorpus.json`), then re-ingested and re-validated. Only **13 of 31**
verify: removing `println` exposes the older Swift 2 API behind it (`reduce`,
`filter`, `count` as globals, `Cocoa`/`NSFileHandle`/`Process`, pre-Swift-3
argument labels). Those eight need real code rewrites, not a token rename, so
they stay `failed` rather than being papered over.

### The tournament

For each confirmed **runnable** task the coder writes the same program in seven
styles — `terse`, `idiomatic`, `functional`, `oop`, `defensive`, `readable`,
`fast`. Every variant must compile, run, and be timed (median of 3 runs). The
judge then compares each build against the confirmed reference and the top two
against each other, with bytes and milliseconds in front of it.

Outputs land in `data/tournament/<timestamp>/`:

| file | contents |
|---|---|
| `results.jsonl` | full record per task: variants, verdicts, score, winner |
| `pairs.jsonl` | preference pairs (chosen / rejected) for DPO-style training |
| `summary.json` | verified rate, per-style wins, avg bytes reference vs winner |

every winner is also appended to the SFT dataset with `source: tournament:winner`,
so the next LoRA round learns from judged, executable code.

**First real run** (3 Go tasks, 4 styles, judge Qwen3-Coder-30B):

| | |
|---|---|
| variants generated / verified | **12 / 12 (100%)** |
| style wins | `idiomatic` 3 |
| avg bytes: reference → winner | **456 → 415** |
| avg runtime | ~31 ms across styles |
| preference pairs | **15** |
| winner SFT rows | 3 |

The judge did not just pick the shortest build: on one task it kept a longer
`idiomatic` rewrite over a smaller `terse` one (528 B vs the 443 B reference),
because the terse version was judged less versatile. Per-dimension verdicts
(`correctness`, `smaller`, `faster`, `versatility`) are stored with every pair,
so that trade-off is auditable rather than hidden in one opaque number.

**Pilot run** (25 library programs, 4 styles, same 14B coder + 30B judge):

| | |
|---|---|
| variants generated / verified | **89 / 96 (92.7%)** |
| style wins | `fast` 11, `idiomatic` 8, `terse` 4, `readable` 1 |
| avg bytes: reference → winner | **557 → 546** |
| avg runtime by style | terse 262, idiomatic 242, readable 226, fast 216 ms |
| preference pairs | **109** |

The pilot corrected one impression from the 3-task run: `idiomatic` does not win
everything. At 25 tasks `fast` wins most often, and the winner is only ~2% smaller
than the reference — because these seeds are the library's own confirmed code, not
naive implementations. The 7 unverified variants are real failures (compiler
rejects), not judge opinions.

### The band: any number of connections

The app never hard-codes a model. Every named connection in `config.json` is a
**player**: it can be switched on or off, it can hold one of the three seats
(`coder`, `builder`, `judge`), and one player **leads**. The band panel is a row
per player — a toggle, a seat selector, a hang-up button, and a `?` that asks the
server whether it is answering and actually serves the model named.

```json
"band": { "leader": "llm", "copy_builds": true },
"roles": { "coder": "llm", "builder": "builder", "judge": "judge" }
```

`llm` is Qwen2.5-Coder-14B and leads; it is also the connection the builder uses
when no player is named. `builder` (Qwen3-Coder-30B over the tailnet) and `judge`
hold the other two seats.

**Adding a player needs no key and no code.** A local server — Ollama, LM
Studio, llama.cpp, vLLM, anything OpenAI-compatible — is reachable by URL alone:

```bash
curl -X POST localhost:8137/api/band/add -H 'Content-Type: application/json' -d \
  '{"name":"lmstudio","model":"qwen2.5-coder-7b","url":"http://127.0.0.1:1234/v1"}'
curl -X POST localhost:8137/api/band/seat -H 'Content-Type: application/json' -d \
  '{"role":"coder","name":"lmstudio"}'
curl -X POST localhost:8137/api/band/probe -H 'Content-Type: application/json' -d \
  '{"name":"lmstudio"}'
```

`kind` is the wire protocol, not the vendor: `ollama` uses the native chat API
(the only one that also returns the model's thinking text), `openai` is any
OpenAI-compatible server, and `relay` is the manual seat described below. `api_key` is optional and blank by default — when
it is empty no `Authorization` header is sent at all, which is what every local
server expects. Fill it for a hosted endpoint that issues one; the key is never
returned by the API, only `needs_key: true`.

Three refusals keep the band honest, each with the reason in the error:

- a player that **leads** cannot be switched off or hung up until another
  connection leads;
- a player that **holds a seat** cannot be switched off or hung up until the
  seat moves (a seat takes one player, so seating another moves it);
- a **switched-off** player is refused by `chat_for`, `seat` and the builder
  rather than quietly used.

**Every build is copied whole.** `band.copy_builds` is on by default; after each
app the builder writes `data/builds/<stamp>/<model>--<task>/` holding
`record.json`, every final file under `files/`, the file set of any attempt that
differed from the one that shipped, `attempt-N-plan.md` / `attempt-N-files.md`
with the model's own reasoning, and `build.txt` with the command, exit code and
output. The pool dedupes; the copy does not — a build that failed twice before
passing keeps both failed sets, so the run can be read, re-scored or mined after
the pool has moved on.

### Offline only: models on this box, no keys

Nothing in the band needs a key. A local server is a URL and a model name, and
the empty `api_key` means no `Authorization` header is sent at all:

```bash
# Ollama, native chat (this is the leader's own box setup)
curl -X POST localhost:8137/api/band/add -H 'Content-Type: application/json' -d \
  '{"name":"ollama","model":"qwen2.5-coder:14b","url":"http://127.0.0.1:11434"}'

# LM Studio, llama.cpp server, vLLM — all OpenAI-compatible, all keyless
curl -X POST localhost:8137/api/band/add -H 'Content-Type: application/json' -d \
  '{"name":"lmstudio","model":"qwen2.5-coder-7b","url":"http://127.0.0.1:1234/v1"}'

curl -X POST localhost:8137/api/band/seat -H 'Content-Type: application/json' -d \
  '{"role":"builder","name":"lmstudio"}'
curl -X POST localhost:8137/api/band/probe -H 'Content-Type: application/json' -d \
  '{"name":"lmstudio"}'
```

`probe` is how you know it is really there: it asks `/api/tags` and then
`/v1/models` and reports whether the named model is actually served, so an
empty answer is a real answer rather than a mysterious failure later.

### Chat-only models: the relay seat

Some models cannot be connected at all — Freebuff, the ChatGPT / Claude /
Gemini web apps, anything you reach by typing into a page. They expose no
endpoint and issue no key: the session belongs to the client, not to you, and
driving their private backend would be brittle and against their terms. The
honest way to put one in the band is a **relay seat**: VACA writes the prompt to
disk, you paste it into whichever chat window you like, and you paste the answer
back. The seat returns exactly the text the model gave you.

```bash
# a player with no URL at all
curl -X POST localhost:8137/api/band/add -H 'Content-Type: application/json' -d \
  '{"name":"webbrain","model":"chat-ui-model","kind":"relay"}'

python3 -m trainapp.relay --pending          # what is waiting
python3 -m trainapp.relay --show <id>        # the exact text to paste
python3 -m trainapp.relay --answer <id> --file reply.txt
```

Requests live in `data/relay/outbox/<id>.json`, answers in `inbox/`, and both
move to `archive/` once the seat collects them — so `--pending` never lists a
prompt twice. The seat blocks until answered (`timeout_s`, 1 h by default), and
a timeout says which id to answer rather than failing silently. A relay player
needs no key, sends nothing anywhere, and can hold any seat, including the
leader — which is how you can run a whole four-seat build on a model that only
exists in a browser tab.

One limit, stated plainly: it is one paste per seat per pass. A four-seat build
is four hand-offs, and every repair pass adds one more. For anything more than
an occasional run, an offline model on a socket is faster.

### The orchestra: four seats write the app

`orchestra` is the band doing a job, not a connection list. One requirement goes
through four personas in order, each with its own system prompt and its own
output shape:

| seat | produces | cannot |
|---|---|---|
| architect | JSON blueprint: tree, files + purpose, entry point, `run` command, fixture `inputs`, `expected_stdout`, dependencies — the last three only when the request left them open | write code, or be asked to fix any |
| tech lead | markdown logic per file: steps, state, edge cases | emit code |
| developer | complete files as `FILE: path` blocks | invent a path |
| QA | JSON verdict: `PASSED` / `FAILED`, errors, scope, files, checked against the manifest | overrule the toolchain |

#### The blackboard, not a chat chain

Seats do not pass chat history to each other. They share one board
(`trainapp/board.py`) and each is handed a *view* of it — a filter, computed at
call time from what that seat is allowed to read. Four sections, one owner each:

| section | owner | holds |
|---|---|---|
| `project_manifest` | architect | path → the functional requirement of that file (plus `tree`, `entry`, `dependencies`, and the `run` command / fixture `inputs` / `expected_stdout` the request left open) |
| `design_ledger` | tech lead | path → algorithm, steps, state kept, edge cases |
| `code_repository` | developer | path → the source |
| `bug_tracker` | QA | append-only failures: path, error, scope, attempt, toolchain flag, time, resolved |

| seat | writes | reads |
|---|---|---|
| architect | `project_manifest` | (the requirement only) |
| tech lead | `design_ledger` | `project_manifest` |
| developer | `code_repository` | `project_manifest`, `design_ledger`, `code_repository`, `bug_tracker` |
| QA | `bug_tracker` (append + resolve) | `code_repository`, `project_manifest` |

A seat that writes a section it does not own raises `BoardPermission`; so does
one that reads a section it has no claim on. This is the difference between the
blackboard and a prompt chain — the boundary is a check, not a request. The code
is the single source of truth, so a repair pass is a *commit* of one file, not a
re-statement of the project.

The coder's files are handed to `execution.run_files`, and **both** QA and the
real toolchain have to pass: a model that says `PASSED` over `print(` still
fails, and the compiler's words are what the developer gets next — written to
the board as a `toolchain: true` bug on the same file. A failure with
`scope: "design"` goes back to the tech lead instead of the coder. The loop is
capped at 3 passes.

Two boundaries do the structural work:

- **The developer may not invent a file.** It writes `REQUEST_FILE: path — purpose`
  and the state returns to the architect, because a new file is a blueprint
  change. That round consumes one of the three passes, so it cannot run away.
  A path it slips in unannounced is refused at the commit, not filtered later.
- **A repair sees only the files QA blamed** — `board.view("developer", only=failing)`
  returns those files' code, their ledger entries and their open bugs, and
  nothing else. That is cheaper and much harder to corrupt: an untouched file
  cannot be accidentally rewritten by a defensive model. Two things keep the
  filter narrow over three passes: a new verdict resolves the per-file bugs it
  did not repeat (`resolve_stale`), and a toolchain failure is attributed to the
  file the compiler named rather than left pathless — otherwise the coder gets
  the whole project back on every pass.

#### Exercising the build: `--smoke`, `--input`, `--expect`

A program the requirement exercises with an argument is run the way the
requirement says, not bare. The invocation is `builder.args_from_run` over the
`run` command — the same convention the builder's plan already uses. Without it
a line counter run as `python cli.py` prints its usage and exits 1, and the gate
blames the code for a failure the invocation caused.

The caller says it first. `--smoke` fixes the invocation, `--input PATH=CONTENT`
supplies a file the program reads, `--expect TEXT` says what a correct run
prints. All three go on the board before the architect speaks, and it cannot
revise them: a model that writes both the code and the data it runs against can
agree with itself, so the test data is not written by the model being tested.
What the request leaves open the architect fills; `blueprint.json` records which
of the two said so (`run_from`, `inputs_from`, `stdout_from`).

`--expect` is the check that makes fixture data mean something. An exit code of
0 only says the program did not crash — a build that ignores its input and
prints a constant exits 0 and passes every earlier gate. The expected output is
compared (whitespace-trimmed, otherwise exact), so `Hello, ada!` against
`Hello, ada` fails; the seats that write the code are shown the same contract,
because a gate nobody was told about punishes punctuation instead of testing the
job. Fixtures are written to the scratch directory for the run and never copied
into `files/`: the app ships without its test data.

When nobody states an expectation, one is derived from the requirement itself
(`trainapp/expect.py`): a quoted literal (`prints "Hello, ada"`), a plain number,
`the sum/product/difference/quotient of 2 and 3`, or `2 + 3`. A derivation is
recorded as `derived` with the rule that produced it, because the sentence is
weaker evidence than the caller's word. Anything needing an oracle — "the first
12 primes", "the current date" — is left alone, and the fallback is that a
requirement saying it prints must print something: exit 0 with empty stdout
fails. `matches` is `unknown` in the copy when there was nothing to compare, so
a pass that rested on an exit code cannot read as a checked one.

Two limits are enforced rather than asked for, both found by running the band
across the toolchains:

- **`run`/`inputs` are only offered when the requirement names an input**
  (`argument`, `file`, `path`, `stdin`, `line`, ...). Offered unconditionally,
  the field reads as an invitation: a 14B asked for `inputs` on "print the sum
  of 2 and 3" designed a file-reading CLI and then failed the requirement it was
  given. `--smoke` is the escape hatch when the guess is wrong.
- **QA reads the manifest**, so it reviews the code against the job as planned.
  Given only the requirement, it invents requirements no other seat was given
  and fails a build for doing what its blueprint said.

Both structured seats ask the server for JSON rather than parsing prose after
the fact — `response_format` on an OpenAI-compatible player, `format: json` on
`kind: ollama`. Parsing is still tolerant, validation is not: a reply with no
usable blueprint is an error, not an empty app.

```bash
python3 -m trainapp.orchestra --require "a python CLI that prints the first 12 primes"
python3 -m trainapp.orchestra --require "..." --player lmstudio --attempts 2 --out /tmp/run

# the caller's own statement of how it is run, against what, and what it prints
python3 -m trainapp.orchestra \
    --require "a python CLI that counts the lines in a file, exiting 1 if missing" \
    --smoke "python cli.py notes.txt" --input "notes.txt=alpha" --expect "1"

# one player per seat: the bulk on one model, the review on another
python3 -m trainapp.orchestra --require "..." \
    --player agent-stock --seat qa=agent-vaca --seat architect=agent-stock
```

`--seat seat=player` (or `chats={"qa": player}` in Python) gives any of the
four seats its own model; a seat with no override uses the run's player. The
copy's `state.json` records `seats` — which model actually sat where — because
a result means nothing without it.

It uses whichever player is named, or the leader when none is. The **Orchestra**
panel runs the same thing from the app — requirement, language, player, passes,
the smoke command, the expected output, the files it reads (one `PATH=CONTENT`
per line), a `Build` button, and each seat's line as it happens
(`POST /api/orchestra/start` takes `smoke`, `expect` and `inputs` too, the last
as a mapping or as those `PATH=CONTENT` strings; `GET /api/orchestra/status`
echoes back what the run was told to do). The panel also renders the **bug
tracker pass by pass** — pass number, whether it passed, the files it blamed and
the bugs it recorded — from `status.passes`, which the job publishes as each
pass lands rather than only when the copy is written.

Every run is copied to `data/band/<stamp>/<requirement>/`: `blueprint.json`,
`reasoning.md`, `qa.jsonl` (one verdict per pass), `bugs.jsonl` (the whole bug
tracker, resolved entries included), `files/` (what shipped),
`attempt-N/files/` (every pass that was written), `build.txt`, `state.json`,
`notes.txt`. The function is `async` (`asyncio.to_thread` around the blocking
clients), so seats can be overlapped later without changing a signature;
`orchestra.run` is the synchronous door.

### Measured: two models on the agent box

Both models resident at once on `llmlab-agent` (2× RTX 3060 12 GB), after
unloading the 30B that was holding 20 GB:

| model | size | placed | context |
|---|---|---|---|
| `qwen2.5-coder:14b` (stock, the worker) | 9.8 GB | 100% GPU | 8192 |
| `vaca-r40-q4` (VACA's tuned model, the reviewer) | 10 GB | 100% GPU | 8192 |

Two builds with the stock 14B on architect, tech lead and developer and VACA's
model on QA — the split the band exists for:

| brief | wall | passes | result |
|---|---|---|---|
| first 12 primes, one file | 14.8 s | 1 | built; prints 2…37, verified by running it |
| `fibonacci.py` + `main.py`, named function, cross-file import | 21.3 s | 1 | built; `from fibonacci import first` correct, prints 0…89 |

Per seat (second build): architect 3.4 s, tech lead 11.6 s, developer 5.1 s,
QA 1.1 s. The pattern is the expected one — the tech lead's plan is the slow
part, and QA's review is cheap because it only reads a small set.

Two things this does not show: n=2 is not a quality measurement, and both
briefs are small. It does show the wiring: two models, one endpoint, a real
toolchain pass, and both artifacts correct when run by hand afterwards.

### Harvesting every build (monthly)

Two records are kept per build, and they are deliberately different:

- the **run** — requirement, blueprint, design, every attempt, every QA verdict,
  which player ran it — goes to `library/band_runs.jsonl`. A failed build is as
  informative as a passing one here, and nothing in this file is trained on.
- the **task** — only a build whose own toolchain run passed — becomes one
  library entry in `library/band_builds.jsonl` with a `verified` validation
  record, origin `band-build`. That is what a later SFT sheet can learn from.

The copies on disk (`data/band/…` from the orchestra, `data/builds/…` from the
builder) are the only source, so a build that never finished cannot become a
task by accident. Ingestion dedupes on the code's content hash — the same key
the rest of the library uses — so running it twice adds nothing twice.

An orchestra run enters the library only when the gate actually **compared its
output** (`build.matches: true`). A pass whose expectation was unknown prints
what it prints and exits 0; that is not evidence of an app, so the run is logged
in `runs.jsonl` and held back, and the summary counts it under `unchecked`.
Builder copies carry no output comparison at all, so `checked` is `null` for
them and their own gate (`record.ok`) is all they claim.

```bash
python3 -m trainapp.harvest --scan        # what is on disk
python3 -m trainapp.harvest --monthly     # ingest + this month's sheets
python3 -m trainapp.harvest --status      # when it last ran, what it kept
```

`--monthly` is the scheduled door and refuses to run twice inside 28 days
unless `--force`, so a restart cannot re-cut a month. It ingests, rebuilds the
library index, and writes `library/harvest/<YYYYMM>.jsonl` (the tasks gathered
that month) and `<YYYYMM>_sft.jsonl` (their training rows). File sets are
harvested as tasks but **not** flattened into one SFT row — a set is not one
instruction; `scaffoldsft` is the module that turns a set into rows, and the
summary reports the count instead of silently dropping it.

To run it on a schedule:

```bash
cp deploy/vaca-harvest.service deploy/vaca-harvest.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now vaca-harvest.timer   # OnCalendar=monthly, Persistent=true
systemctl --user list-timers | grep harvest
```

`harvest.status.json` holds the last run — month, runs read, tasks added, SFT
rows — and the **Harvest builds** button in the library panel runs it on demand.

### Judge model

The judge is **Qwen3-Coder-30B-A3B-Instruct Q4** (~18 GB), pulled onto the agent
box and served by its Ollama over the tailnet:

```json
"judge": { "url": "http://100.121.154.124:11434/v1", "model": "qwen3-coder:30b" }
```

It is ~20× the student, a newer family, and MoE (3.3B active) so a verdict takes
~16 s instead of minutes. The deterministic gate decides invalid-vs-valid and
identical-code cases with no model call at all.

### Preference training (ORPO)

Tournament verdicts become training signal, not just JSONL on disk:

```bash
python3 -c "from trainapp import preferences; print(preferences.export_pairs())"
python3 train_lora.py --mode orpo --pairs data/dataset/pairs_train.jsonl \
    --val-pairs data/dataset/pairs_val.jsonl \
    --model Qwen/Qwen2.5-Coder-1.5B-Instruct --out data/models/orpo1 --max-steps 60
```

`export_pairs()` collects every `pairs.jsonl` from every run, dedupes by
`(task_id, chosen, rejected)`, and hash-splits 90/10 so a val pair is never one
the policy trained on. ORPO needs no reference model, which is what makes
preference training fit this hardware at all.

The loss is `-logp(chosen)` plus `lambda_or * -logsigmoid(logodds(chosen) -
logodds(rejected))`, computed over response tokens only (the prompt is masked).
After training the adapter is scored on the held-out split and the result is
written to `train_meta.json`:

Before training the same 18 held-out pairs are scored by the untrained policy, so
`train_meta.json` carries both sides of the comparison:

```json
"val_before": { "pairs": 18, "accuracy": 0.556, "mean_margin": 0.087 },
"val":        { "pairs": 18, "accuracy": 0.778, "mean_margin": 0.203 },
"val_improved": true
```

`accuracy` is the share of unseen pairs where the policy already prefers the
judged winner — a tie counts as a loss. **That number, not the training loss, is
what says whether a round was worth keeping.**

**Real round** (152 pairs → 134 train / 18 val, 60 steps, 3.5 epochs, seq 1024,
1.5B on the desktop 3060):

| | base | after ORPO |
|---|---|---|
| held-out accuracy | 10/18 (0.556) | **14/18 (0.778)** |
| mean margin | +0.087 | **+0.203** |

Six pairs flipped wrong→right and two right→wrong. **That is not statistically
significant on 18 pairs** (exact sign test p=0.29), so that adapter
(`data/models/orpo1/adapter`) stayed provisional. Two real bugs were found and
fixed getting here: Trainer's eval drove the model with the pair dataset's raw
columns (crash *after* a successful train), and the fp32 log-softmax over a 151k
vocabulary exhausted 12 GB at seq 1024 — the log-prob helper now chunks and ORPO
turns on gradient checkpointing.

**Larger round** — an overnight 70-task tournament (`20261022T024501`) took the
pair pool from 152 to **320 unique pairs** (134 verified variants of 210, 63.8%;
winners cut avg bytes 531 → 395). Same settings, 286 train / 34 val, adapter
`data/models/orpo2/adapter`:

| | base | after ORPO |
|---|---|---|
| held-out accuracy | 20/34 (0.588) | **23/34 (0.676)** |
| mean margin | +0.069 | **+0.133** |

Six pairs flipped wrong→right, three right→wrong — **exact sign test p=0.51**.
Nearly doubling the val split moved the p-value from 0.29 to 0.51: the gain is
indistinguishable from noise at this size, and detecting a ~10-point effect needs
a few hundred val pairs (≈3000 pairs total), not 34.

A second sweep is running over all 214 confirmed programs in 7 styles
(`python3 -m trainapp.tournament --tasks 214`). At ~7 pairs per task it should
roughly quadruple the pool (≈1,500 pairs, ≈150 held-out), which is enough to
resolve a 15-point effect but still not the 10-point one. The run writes
`pairs.jsonl` incrementally and is visible in the UI while it works, including
when it is started from the CLI.

`python3 -m unittest ...` covers the pure parts (`preference_accuracy`,
incomplete-pair rejection) so the metric is testable without a GPU.

### Scoring an adapter on real toolchains (`battery`)

```bash
python3 -m trainapp.battery --tasks 30 \
    --adapter data/models/orpo2/adapter --model Qwen/Qwen2.5-Coder-1.5B-Instruct
```

Two arms (base, base+adapter) answer the same held-out library tasks with the
prompt the pairs were built from, and every answer is compiled, run, and
compared against the reference's stdout. Tasks that already have preference
pairs are excluded ("seen"), so nothing scored here was trained on.

**Real run** (30 proven tasks, 9 languages, **no skips**, adapter `orpo2`):

| | base | + ORPO adapter |
|---|---|---|
| compiles and runs | **23 / 30 (77%)** | 20 / 30 (67%) |
| output matches reference | 2 / 30 (7%) | 3 / 30 (10%) |
| avg bytes | 380 | 369 |

Four tasks flip to the adapter (rust stdin-summarise, Java 100 doors, Java
callback, Swift arithmetic) and seven to base — exact McNemar p=0.55. The
verdict matches the earlier, partly-skipped runs (base 19/25 vs adapter 15/25):
**no compile-correctness gain**, a single extra behavioural match, and only 3%
smaller output once every language is represented. The earlier 20% size gap was
a small-sample artefact of PHP/Python-heavy tasks.

This battery has no skipped tasks at all, because it only selects tasks whose
reference has a `verified` record (the fixes above are what make that set exist:
C# builds through a generated project, Java files carry the class name, and
components are no longer counted as programs). An earlier run could only score
12–13 of 30 and reported harness failure as if it were model failure.

**Growth A/B** (3 held-out seeds × 3 styles, same judge, `--seed-ids` pinned,
adapter `orpo1`):

| coder | accepted | rejected |
|---|---|---|
| base 1.5B | **0 / 9** | 3 invalid, 3 behaviour mismatch, 3 lost |
| + ORPO adapter | **1 / 9** | 6 invalid, 1 identical, 1 duplicate |

The 14B coder managed 2/9 on its own seeds, so **the adapter does not beat that
result** — it is a 1.5B model and it got *worse* at compiling, not better. What
it does do is place one judged winner (FizzBuzz, `idiomatic`), which is the shape
of progress the loop needs but not yet at a rate worth shipping.

### Growing the library

```bash
python3 -m trainapp.grow --seeds 3 --styles terse,idiomatic,fast
```

For each confirmed seed the coder writes candidates, and a candidate is added
**only** when all of these hold:

1. it compiles and runs (real toolchain, exit 0);
2. it is not code already in the library;
3. when the reference's output is deterministic (same on two runs), the
   candidate produces the same output;
4. the judge ranks it strictly above the reference (a tie is not a win);
5. the measurements support the verdict: at most +10% bytes, at most +10%
   runtime (plus a 50 ms floor), at least one strict win, and no verdict whose
   own dimensions favour the reference.

Survivors are written to `data/library/grown.jsonl`, get a verified validation
record, and join `library.confirmed()` — so tournaments and training use them
like any hand-written entry. Re-running `library.build()` never deletes them.

**First real run** (3 seeds × 3 styles, 14B coder, 30B judge): **2 accepted of
9 candidates**.

| accepted | bytes | runtime | reference |
|---|---|---|---|
| rust, idiomatic | 546 | 84 ms | 593 B / 487 ms |
| rust, fast | 609 | 87 ms | 593 B / 487 ms |

Rejected: 1 did not compile, 3 changed the deterministic output, 3 lost to the
reference. The size/runtime gate is what stopped a later "winner" whose own
reasoning admitted the reference was smaller.

## Training

`config.json` (optional; defaults in `trainapp/config.py`):

```json
{
  "training": {
    "backend": "agent",
    "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "max_steps": 120,
    "out_dir": "training/out/base",
    "agent": {
      "host": "llmlab-agent",
      "user": "llmlab",
      "python": "/home/llmlab/vaca-train-venv/bin/python",
      "workdir": "/home/llmlab/Desktop/visual-ai-architect",
      "remote_dir": "vaca-train-app"
    }
  }
}
```

The **agent** backend (`build_agent_script`) does exactly three things over
ssh: `mkdir` the remote dir, `scp` `train.jsonl` + `val.jsonl` + `train_lora.py`,
then run the trainer with the remote venv's python. Nothing is installed
remotely. The **local** backend runs the same trainer here.

The app does not silently fall back: if ssh or the trainer fails, the job turns
`failed` with the log tail visible in the UI.

### Unattended nights (`overnight`)

```bash
cd ~/vaca-train-app
nohup python3 -m trainapp.overnight --hours 8 --rounds 2 > /tmp/overnight.out 2>&1 &
python3 -m trainapp.overnight --status      # round, counts, ETA, last set
touch data/overnight.stop                   # or: --stop  — ends between attempts
```

To make it survive logout and reboot, install the user unit in `deploy/` (edit
`WorkingDirectory` if the clone is elsewhere):

```bash
mkdir -p ~/.config/systemd/user
cp deploy/vaca-overnight.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now vaca-overnight.service
systemctl --user status vaca-overnight.service   # or: --status for the loop's own file
```

Nothing in it needs a terminal, an agent, or a person: Ollama serves the coder
and the loop reads its own status file. `Restart=on-failure` resumes the round it
was in.

`overnight` is the loop around the function-level probe, built to be left alone:
every attempt is appended to `data/overnight/<stamp>/samples.jsonl` or
`failures.jsonl` the moment it finishes, `data/overnight.status.json` is
rewritten after each one, a restart resumes the round it was in, and a model
error is retried and then skipped (several in a row end the run rather than burn
the night). The app and the trainer are the only moving parts: Ollama serves the
coder, `execution.run_files` builds and runs the set, the reference run decides
pass or fail. Nothing calls an LLM to judge.

Why function granularity: on the same 19 non-TypeScript held-out sets with the
same 14B, asking for the whole target file matched the reference output 4/19
times; asking for one function, given its signature and the real sibling files,
matched 11/19. Same weights, same conventions.

What a night produces (`data/overnight/export/`):

- `sft.jsonl` — only the passes, as `{instruction, input, output}` in the
trainer's exact `### Instruction / ### Input / ### Response` shape;
- `pairs.jsonl` — the same prompt's passing reply against its failing one
  (`{prompt, chosen, rejected}`), which is what ORPO can use;
- `nearmiss.jsonl` — pairs mined by `trainapp.nearmiss` from answers that were
  already right (see below);
- `summary.json` — counts.

`trainloop.prepare_data()` reads those two files, so the night's verified rows
join the same hash split as every other proof-gated row. To chain the two:

```bash
python3 -m trainapp.overnight --hours 8 --rounds 2 --train 2   # generate, export, train
```

A pair needs the same prompt to pass once and fail once, so it needs sampling
diversity: at the default `--temperature 0.2` a round mostly reproduces the
previous round's answer and `pairs.jsonl` stays thin. For pair mining run later
rounds hotter:

```bash
python3 -m trainapp.overnight --rounds 3 --limit 60 --temperature 0.8
```

### Autonomous cycles (`autoloop`)

```bash
nohup python3 -m trainapp.autoloop --cycles 3 --hours 6 > /tmp/autoloop.out 2>&1 &
python3 -m trainapp.autoloop --status      # stage, cycle, champion, last verdict
python3 -m trainapp.autoloop --report      # the cycle table, as markdown
python3 -m trainapp.autoloop --stop        # ends between two stages
python3 -m trainapp.autoloop --fake --cycles 3   # the policy with no GPU
```

One cycle is: a night over the judgeable pool, family-balanced near-miss mining,
SFT with whole families held out, one ORPO pass over the night's verified pairs,
then scoring on both held-out pools and the boundary battery. `trainapp.autoloop`
decides whether the candidate replaces the champion, and if not, escalates one
lever instead of repeating the cycle.

The family split holds out only families with **at least two scored sets**, and
no family may contribute more than four. A family represented by one set scores
one draw — 34 of the first 42 held families had exactly one, which is how a
language swap inside a family arrived as "+3". The pool is frozen per split
version, so a restart cannot keep scoring a split that has been replaced.

A gain is judged **paired**: the same held-out sets, scored for both arms, with
an exact McNemar test; a gain that does not survive the pairing is refused.

What counts as progress: **family-held-out behaviour** must rise by at least one
task and survive the pairing, with the boundary battery losing at most one
probe. A candidate that repairs at least two boundary probes while its task pool
improves with pairing is kept even when family behaviour stays inside noise:
the format lanes are what the app itself depends on. A tie on families can
still be kept as a breadth gain (two more task-level tasks), because compile
breadth is what makes the next cycle measurable. Behaviour bought by giving up
the no-fence lane is refused — that trade was already measured and rejected.

A candidate that repairs at least two boundary probes with no regression in
either behaviour pool is kept even when family behaviour sits inside noise. The
gate is graded per probe over three samples, so it does not need a behaviour
pairing to be believed; requiring one refused two candidates that had fixed the
fence lane outright.

Two contract lanes get their own training rows (`contractsft`): verified
multi-file sets asked for one file with the explicit invitation to invent
siblings (teaching the refusal), and verified Go builds broken by the dead
declaration the compiler names (teaching the repair). Every row is checked
against the probe that grades it before it can enter the sheet.

Each probe is generated three times and graded by strict majority, because one
sample at temperature grades a coin flip as a fact: the first unattended cycle
refused a candidate whose only regressions were two prose probes while every
format probe it had failed still failed. The verdict line names the probes it
lost by lane, and `report.md` carries a per-lane pass count, so a refusal says
which contract moved instead of only how many probes did.

The night is ordered **cold first**: sets no night has measured, then sets that
have been probed and never once passed, then the rest. An hour reaches only a
prefix of the pool, and one round per cycle makes `rotated(pool, 1)` the
identity — so without this ordering every cycle re-probed the same opening sets.
The sets that ordering now reaches first were mostly unjudgeable, so the real
gap is the 75 that have been probed and never passed, not the few that were
never tried.

The training mix drops near-duplicate demonstrations (`librarysft.rows`): the
library asks `sum to 5`, `sum to 7`, `sum to 9` with different constants, and
those variants were 2600 of the sheet's 3029 rows — 20 programs in 13 languages,
repeated. One demonstration per program per language keeps all 20 families and
all 13 languages in 245 rows, so no single program owns the gradient.

When nothing improves, the ladder climbs one rung per cycle: more balanced pairs
per family, more night samples, a longer ORPO pass, a longer night, every
function rather than three, a longer SFT, then training on top of the champion.
When every rung is spent it stops and says so: the next gain then needs new
program families, which is content, not tuning.

State lives in `data/autoloop/` (`state.json`, `journal.jsonl`, `report.md`), the
live stage in `data/autoloop.status.json`. Install `deploy/vaca-autoloop.service`
to keep it running across reboots.

### Near misses (`nearmiss`)

```bash
python3 -m trainapp.nearmiss --per-row 1     # after a night, before training
```

The night's own pairs teach “builds vs. does not build”: the rejected half is
whatever the sampler produced, which is usually something that fails to compile.
The errors that survive on held-out sets are smaller than that — a fibonacci
seeded at 1, a word count that never accumulated — and both halves build.

So `nearmiss` manufactures the missing contrast. It takes a passing answer,
perturbs it once (loop guard, range end, seed, accumulator sign, comparison,
arithmetic, divisor), rebuilds the whole set, and keeps the perturbation only
when the set still builds **and** its stdout now disagrees with the reference.
The kept perturbation becomes a pair: the original answer chosen, the near miss
rejected, one prompt on both sides. Nothing is asserted about what a mutation
should do — the set decides, exactly as it decides a night's rows.

Measured on 24 held-out sets (task-level split, below 1/3 of task ids), SFT on the
same rows for every arm, ORPO on 98 pairs per arm:

| arm | compile | behaviour | boundary gate |
|---|---|---|---|
| base 1.5B | 14/24 | 9/24 | 4/10 |
| SFT night only | 18/24 | 13/24 | 7/10 |
| + random pairs, 12 steps | 20/24 | 15/24 | **3/10** |
| + random pairs, 40 steps | 18/24 | 15/24 | **3/10** |
| + near-miss pairs, 12 steps | 19/24 | 15/24 | 7/10 |
| + near-miss pairs, 40 steps | **23/24** | **19/24** | 5/10 |

Against the base the 40-step near-miss arm is significant on both compile
(+10/−1, p=0.012) and behaviour (+11/−1, p=0.006). Against the same-dose random
control it is ahead by five behaviour tasks but that gap is not significant at
this size (p=0.22), and the clearer difference is the gate: generic preference
pairs cost the no-fence lane (7/10 → 3/10) at any dose, while the mined pairs do
not (−0 at 12 steps, −2 at 40). Harvest is roughly 1 pair per 2.4 passing rows
(169 pairs from 406 rows in a night), and about a third of the attempts are lost
to mutations that stop the build (84) or leave stdout unchanged (152).

That table is a task-level split, and a task-level split leaves the siblings of
held-out sets in training: 9 of the 11 behaviour gains were the fibonacci ask in
other languages. `functioneval.held_out_tasks(by_family=True)` holds out whole
programs instead — 52 sets from 38 families, the fibonacci family left in
training — and the same arms score:

| arm | compile | behaviour |
|---|---|---|
| base | 23/48 | 14/48 |
| SFT night only | 27/48 | 17/48 |
| + near-miss pairs, 40 steps | 27/48 | 17/48 |
| + random pairs, 40 steps | 29/48 | 20/48 |

Mined pairs add exactly nothing over SFT on families they were not mined from
(+3/−3, p=1.0); the earlier +6 was the family, not the lesson. Train with
`--family-holdout` to keep those families out of training as well before
reading any of it as transfer.

The night's passing rows are as skewed as the library, so mining walks rows
round-robin by family and `--per-family N` caps what one program may
contribute: the same night yields 169 pairs with a 115-pair fibonacci share
unbalanced, or 53 pairs across 18 families with a 5-pair share balanced. The
balanced sheet is what a family split needs, because an unbalanced one teaches
the family it was mined from.

Diversity is the other half of that: 20 more families went into `clisets`
(binary search, LRU, Luhn, Dijkstra, calendar, parking, CSV stats, Morse, ISBN,
vending, interest, election, life, tic-tac-toe, acronyms, moving average,
Horner, determinant, durations, anagrams). The judgeable pool is now 223 sets
over 123 families with the largest family at 22% (was 203 sets, 103 families,
49/103 = 47%), and the family split holds out 56 sets from 42 families.

Only sets whose behaviour is observable are probed: the loop runs each set
untouched first and drops any whose stdout is empty or whose own run fails,
because a row that can only prove “it compiles” is the lesson that earlier made
a round format-perfect and useless. `--include-unjudgeable` keeps them anyway
and labels those rows `verified: compile`.

Honest limits: the extractor covers 132 of 158 verified sets (the rest are
single-statement or top-level-script targets with no function to ask for), of
which roughly 30 produced a passing function in the last night; only the largest
function in a file is probed, and TypeScript sets are typechecked rather than
run. A pass means “this function, spliced into the real set, produced the
reference stdout” — not that the whole file was written correctly.

### Generated CLI sets (`clisets`)

```bash
python3 -m trainapp.clisets --build     # write data/library/cli_sets.jsonl
python3 -m trainapp.validate --language go,python,php,ruby,javascript
```

VACA's exports are the only multi-file source, and most of them are apps whose
behaviour no stdout can show. `clisets/` adds fifteen sets that were written to
be judged: three files each (entry, target module, formatter), standard library
only, no stdin/argv/clock/network, and a deterministic report on stdout. Five
languages today — Python, Go, PHP, Ruby, JavaScript — three families each.

Nothing is trusted: the sheet is ingested like any other source and
`validate.py` still has to build and run every set before it counts.

### Observing an app set (`runprobe`)

A set whose reference run prints nothing can only prove "it compiles".
`runprobe` looks for an invocation that makes it print: no arguments, then
`--help`, `-h`, `--version`, each run twice, and only stable non-empty output on
a clean exit counts. TypeScript sets are actually run for this (`tsx`, which
resolves their extensionless imports) instead of only typechecked.

The probe is stored per task in `data/library/run_probes.jsonl`, and
`functionprobe.run_set` uses it, so the reference and the model's answer are
always judged under the same invocation. On the current library it found
observable behaviour for 35 of the 78 TypeScript/JavaScript/Rust sets, which
moved judgeable sets from 61 to 111 of 173.

### Scoring what a night produced (`functioneval`)

```bash
python3 -m trainapp.functioneval --adapter data/models/night2/adapter
```

Every third task id is held out (`functioneval.is_held_out`), and
`trainloop.prepare_data()` refuses to train on those rows, so the split cannot
leak through a pair or a neighbour in the same file. The scores are the same
compile-and-run gate the night used: base and adapter answer the identical
prompt for a set they never saw, and the set is built and run. At the current
library size that is a handful of sets, so treat the difference as directional
until the judgeable pool grows.

## Verified end to end

On the agent box (`llmlab-agent`, 2×RTX 3060), a real run of this base:

- captured a verified fix from `tally.py` (ZeroDivisionError → guarded average);
- exported it to `train.jsonl` and scp'd dataset + trainer over;
- trained 1.5B QLoRA for 3 steps (`loss 1.638 → 1.307`) and wrote the adapter to
  `~/vaca-train-app/training/out/base/adapter`.

The job slot reports `done`/`failed` with the log tail, and an ssh or trainer
failure is shown, never papered over.

## Honest limits of this base

- **The agent box needs its VRAM back first.** Both 3060s are routinely pinned
  by an Ollama model with keep-alive `forever` and by LM Studio's model
  servers; the first attempt here died with 625 MB free. Unload those before a
  run (`ollama stop <model>`; LM Studio: eject the model).
- **Local training is small-model only.** This desktop has one 12 GB RTX 3060,
  so `backend: local` is for a 1.5B–3B QLoRA at best. 14B rounds belong on the
  agent/Kaggle path.
- **SFT is still the default; ORPO is opt-in.** `training.mode: orpo` trains on
  judged pairs and reports held-out preference accuracy, but the pair pool is
  still small (320 pairs = 286 train / 34 val), so one ORPO round cannot move
  much and its held-out gain stays inside noise (p=0.51). There is no
  DPO/reference-model path, and no chat-template masking beyond the
  prompt/response split in the ORPO collator.
- **A preference win is not a correctness proof.** Pairs come from judged,
  executed builds, so they encode style (`smaller`, `faster`, `idiomatic`), not
  new capability. Expect ORPO to sharpen taste first and solve problems later.

## Tests

```bash
cd ~/Desktop/vaca-train-app
python3 -m unittest discover -s tests -t . -v
```

The suite runs real toolchains (Python is enough for the default path), fakes
the LLM, and exercises the HTTP surface end to end. No network, no GPU, no
third-party packages.

## Run it (Linux and Windows)

Nothing to install beyond Python 3.11+ and whatever toolchains you already use:
the app is standard library only, with no build step and no packages.

**Linux / macOS**

```bash
cd vaca-train-app
./run-server.sh                      # http://127.0.0.1:8137/
```

**Windows**

```bat
cd vaca-train-app
run-server.bat                       # http://127.0.0.1:8137/
```

Both launchers are thin wrappers around the real command, so use it directly if
you prefer it on either platform:

```bash
python3 -m trainapp.server --host 127.0.0.1 --port 8137
```

`TRAIN_APP_DATA` moves the data directory (that is how the tests keep a clean
one), and the connection list lives in `config.json` next to the code. Compiled
languages need their compilers on `PATH`; **Source languages** above lists what
each lane needs, and the app shows what it found under **Toolchains**.

## The 2026 design: one board, four seats

This build does not pass chat history between agents. Four seats share a single
**blackboard** (`trainapp/board.py`) and each one is handed a filtered view of it:

| seat | writes | reads |
|---|---|---|
| architect | `project_manifest` — the files and their jobs | the requirement only |
| tech lead | `design_ledger` — logic, steps, edge cases | the manifest |
| developer | `code_repository` — the code | manifest, ledger, code, bug tracker |
| QA | `bug_tracker` — structured failures | code and manifest |

A seat that writes a section it does not own raises, and so does one that reads
one it has no claim on. That is what keeps a repair a repair: when a pass fails,
the developer is handed **only the files QA blamed** plus their bugs — never the
healthy files, so an untouched file cannot be quietly rewritten.

The gate is not the reviewer's opinion. The set is compiled and run in a scratch
directory, and when the board knows what a correct run prints, the output is
compared: `--expect` from you, else the value read off the requirement itself
(`"prints the sum of 2 and 3"` → `5`), else the architect's own claim. A program
that exits 0 and prints the wrong thing fails, and QA cannot veto a build the
gate verified — its note is recorded as advisory.

**From the app.** Open **http://127.0.0.1:8137/**, then the *Orchestra* panel:
say what to build, pick a language and a player, and press **Build**. The three
optional fields are yours, not the architect's:

- **Run it as** — the command the program must satisfy, e.g. `python cli.py notes.txt`
- **A correct run prints** — the exact output, e.g. `total: 3`
- **Files it reads** — one `PATH=CONTENT` per line, e.g. `notes.txt=alpha`

Leave them blank and the run still works; it just knows less about what "right"
means. The panel shows each seat's line as it happens and the **bug tracker pass
by pass**, so a failing run is readable while it is still failing.

**From a shell** — the same run, and the same contract:

```bash
python3 -m trainapp.orchestra \
    --require "a python CLI that counts the lines in a file, exiting 1 if it is missing" \
    --language python --player agent-stock --attempts 2 \
    --smoke "python cli.py notes.txt" --input "notes.txt=alpha" --expect "1"
```

```text
orchestra: qwen2.5-coder:14b · python · max 2 pass(es)
  architect: 1 files, run `python cli.py notes.txt` (from the request)
pass 1: failed · failing: cli.py
    ✗ cli.py: the toolchain rejected it (run as: python3 cli.py notes.txt): …
pass 2: passed
built: data/band/<stamp>/<requirement>
```

Every run is copied to `data/band/<stamp>/<requirement>/`: `blueprint.json`
(including who stated the invocation and the expectation), `reasoning.md`,
`files/` (what shipped), `attempt-N/files/` (every pass), `bugs.jsonl` (the
whole tracker, resolved entries included), `qa.jsonl`, `build.txt`,
`state.json`, `notes.txt`. Nothing is deleted on a retry, so a failure stays
readable after the fact.

## Give it more than one model

> **Run several connections, not the 14B on its own.** This version is built for
> multiple LLM connections: a band where each seat can sit a different model.
> Running the main `qwen2.5-coder:14b` solo for all four seats is the shape that
> measured worst here and is not what this build is tuned for — point the seats
> at different models before you judge a run.
>
> This is a temporary restriction, not a permanent rule: it is removed after
> **December 2026** with the build notice above, once the retrained model ships
> and a solo connection is a fair test again. Until then a solo run is an
> experiment, not a measurement of this build.

`config.json` holds the connections; each is a name, a URL, a model and a few
options. Two are enough to start:

```json
{
  "coder":  { "kind": "ollama", "url": "http://127.0.0.1:11434",
              "model": "qwen2.5-coder:14b", "num_ctx": 8192, "timeout_s": 600 },
  "architect": { "kind": "ollama", "url": "http://10.0.0.5:11434",
              "model": "qwen3-coder:30b", "num_ctx": 16384, "timeout_s": 900 }
}
```

Then either give a seat its own player for one run:

```bash
python3 -m trainapp.orchestra --require "…" --player coder \
    --seat architect=architect --seat qa=architect
```

…or use the **Band** panel to add players, seat them and choose the leader, which
is what the app then uses by default (`/api/band/*` does the same over HTTP).

Why it matters: the four seats want different things from a model. The architect
needs planning and has to resist inventing a file for a job that reads nothing;
the developer needs strict formatting; QA needs to read code against a blueprint
without inventing requirements. One model doing all four is the configuration
that produced the drift this build was hardened against. A bigger solo model
did not fix it in testing — a 14B seated alone scored *worse* on two-file builds
than a smaller one — so vary the models before concluding a build is bad.

## Retraining a new LLM

The model is retraining from a clean base. The loop that produces the rows is the
same one that judges them, so a round is only as good as what it can prove:

```bash
python3 -m trainapp.harvest --scan       # what is on disk right now
python3 -m trainapp.harvest --dry-run    # what would become a library task
python3 -m trainapp.harvest --monthly    # ingest, rebuild the index, cut the sheets
python3 -m trainapp.battery --languages python --model base --out data/battery/base.json
python3 train_lora.py --mode sft --train data/dataset/train.jsonl \
    --val data/dataset/val.jsonl --model <hf-base> --out training/out/round1
python3 -m trainapp.battery --adapter training/out/round1 \
    --languages python --out data/battery/round1.json
```

Three rules make the difference between a round and a regression:

1. **Only compared work becomes a row.** Harvest takes a run only when the gate
   actually compared its output (`build.matches: true`). A pass that merely
   exited 0 is logged and held back — the summary counts it as `unchecked`.
   This is why the first ingest after this push adds only the verified builds and
   not the whole history.
2. **Score on held-out programs, both arms, same tasks.** `battery` runs the
   base and the adapter over the same task file; a gain that does not survive
   that pairing is noise, not progress.
3. **Repair is trained, not assumed.** `data/dataset/corrections.jsonl` only
   holds fixes that were re-run and passed, and `--mode orpo` trains on judged
   pairs — style, not capability. Expect taste to improve before correctness.

For a whole unattended cycle — probe, mine, train, score, judge, escalate — use
`python3 -m trainapp.autoloop --cycles 3 --hours 6` (it refuses to promote a
round that cannot be measured on a fresh pool). The data directories under
`data/` are regenerated by these commands, so nothing in them needs to be
committed for the app to run.
