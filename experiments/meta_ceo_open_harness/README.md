# Meta-CEO: Native DeepSeek Harness Web smoke

**Status: TESTED PROBE / REAL DONOR NOT YET RUN / NOT INSTALLED.**

Independent executable P0 slice for [Meta-CEO plan PR #1841](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1841). This branch does not edit the existing DSH full-app pilot [#1717](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1717) or governed MCP/ACP work [#1790](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1790).

## Real consumer capability

The script at experiments/meta_ceo_open_harness/smoke_dsh_web.py starts an **already built full DSH Web application** from a pinned Git checkout, with isolated temporary HOME, DSH_HOME, XDG config/cache, temp directory and working directory. It forwards no inherited account credentials, network proxy or NODE_OPTIONS. It uses the upstream native Web CLI arguments: web --no-open --host 127.0.0.1 --port 0, recognizes the real OS-selected loopback port, performs a real HTTP GET to the HTML app root, and stops its own process group.

Upstream release pin: **deepseek-ai/deepseek-harness@687f282e8625c6b8d11ff58211a90524be2e4317**, the same commit pinned in #1717 (MIT, retain upstream notices in distribution). Native --port 0 behavior is grounded in upstream packages/bundle/web-app/src/startup.ts and packages/boot/cmdline/README.md.

The script refuses wrong SHA, modified tracked source, unavailable built CLI or node_modules, missing/incorrect loopback response, crashed/hung process, incomplete cleanup, and reuse of an existing receipt. It writes one private (mode 0600) JSON record outside the donor checkout. It does not install, build, configure company providers, call Fabric/Executive, or send a model turn.

**Positive result means only a pinned native Web CLI served plausible HTML on loopback and stopped.** It does not verify JS bundle closure, provider readiness, conversation streaming/resume, actual Chairman UI, security of the donor process, Model Router, WorkerResult, or a production install. Provider request observation is explicitly NOT_INSTRUMENTED; the probe itself sends only a loopback GET.

## Run with a qualified host and built donor checkout

This is a read-only probe of the donor checkout. Verify that the selected source is not under an active concurrent writer before starting. A previous or archived #1717 session is not a required participant; use current live custody facts.

~~~sh
python3 experiments/meta_ceo_open_harness/smoke_dsh_web.py \
  --donor /Volumes/Mastermind/agent-workspaces/dsh-donor-20261022 \
  --node /opt/homebrew/bin/node \
  --timeout 60 \
  --receipt /tmp/mmx-dsh-native-web-smoke-01.json
~~~

Use a unique new receipt filename on every legitimate independent invocation; never overwrite or retry an effect-unknown operation. The donor must already have a clean tracked tree, built apps/cli/lib/bin.js and installed node_modules. Use the accepted #1717 setup procedure for any separate authorized installation; this script makes no downloads and changes no donor source.

## Offline test suite (no provider or Mastermind login)

~~~sh
python3 -W error::ResourceWarning -m unittest discover \
  -s tests/meta_ceo_open_harness -p 'test_*.py' -v
~~~

**Observed 2026-10-24:** 11 tests PASS in an isolated Linux container with Python 3.13 and Node 22.16.0. These actually run a disposable *synthetic* Node HTTP app and real Git/loopback/subprocess lifecycle (positive and negative paths). The container had no GitHub DNS access, so **the real DeepSeek Harness application was not downloaded, built, started or inspected here**. A synthetic fixture must not be reported as a native donor acceptance.

## Next verification and handoff

Once the authorized real host has an available stable donor checkout, run this smoke against the real release and retain the precise private receipt. Then use an eligible browser to validate actual native chat send/stream/cancel/resume and schedule using a separately granted fake provider. Only then advance model route and existing governed MCP/ACP and Executive result-consumption integration. Preserve actual live writers and unknown effects; this test does not transfer source ownership or grant any production permission.
