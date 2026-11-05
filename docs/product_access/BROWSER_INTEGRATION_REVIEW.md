# Browser consumer integration — independent assessment, not source takeover

2026-10-09. Mastermind protected source `326c8469a21d7f50fc9ecb1848196bf1c6e66685`. Product source carrier: PR #1301. This assessment does not change the incumbent Browser/Workbench source or clear #1259's publication and Chrome administrator-policy holds. No browser or real application was opened.

## Critical-path refinement

**Small native screenshots do not inherently require merging #838 first.** The existing Browser MCP app's `_native_result` preserves the producer's native `CallToolResult.content`, including `ImageContent`, and enforces a 16 MiB serialized-result ceiling. Its authenticated read route revalidates the original credential before returning content. The existing tunnel also uses the same native-result projection. Therefore the first admitted protected-page screenshot can use the existing Browser native return, once the actual browser, app identity, image integrity and conversation rendering are qualified.

A new local integration test invokes the real existing Browser MCP SDK/ASGI and JWT boundary with an explicitly synthetic owner port. It returns a one-pixel generated fixture PNG and verifies exact decoded bytes/digest without the artifact-return plugin. A separate test expires authorization after the fixture producer is reached and verifies that no image is released. This is native wire compatibility, NOT browser-host, screenshot, page, production or selected-account proof.

#838 remains the existing candidate for retained/ranged text, PNG and binary artifacts. Its F0 producer contract is the existing command ActionArtifactStore's stdout/stderr channels and qualified command result; it is not automatically a durable screenshot archive for read-only Browser calls. Inspect and qualify that purpose/identity bridge through the same artifact owner before retaining Browser traces or screenshots. Do not invent a second evidence store, expose local paths or reinterpret a command artifact reference as a Browser action reference.

## Reproduced unresolved image-integrity gap

The existing Browser native-return path validates the MCP result structure, not the decoded image format or relationship to an expected preview revision. With a valid synthetic authenticated call to `browser_take_screenshot`, a fixture producer returning base64-encoded `not PNG bytes` labeled `image/png` is forwarded as successful native image content.

`tests/product_access_mcp/test_browser_return_boundary.py::BrowserNativeReturnTests::test_corrupt_png_is_refused_before_native_image_release` is a **strict expected failure** requiring rejection. It is intentionally not counted as a passed negative case. The adjacent positive test proves the screenshot producer is reached with the actual pinned schema (including required `scale: css`); a malformed request being refused cannot substitute for testing image corruption. Remove the expected-failure marker only after the actual owner repair is independently verified.

This is an acceptance/evidence-integrity finding, not proof of exploitation or a real corrupt production screenshot. Owner repair must establish bounded decoded bytes, valid permitted media format, exact content length/digest, unambiguous capture/resource identity, capture time and actual environment/deployment association. Reuse accepted byte-owner/image-validation mechanisms where applicable. No image fixture can satisfy the commission's real defect or screenshot requirement.

## Product-scoped security profile still needed

The general Browser resource is not yet a proven product-only profile. At the inspected source:

- `build_browser_resource_plan` pins Playwright MCP 0.0.79 and forbids shared context, raw CDP, extension attachment and unrestricted file access. It constructs a browser process with output directory and isolated/persistent mode, but does not itself enforce approved Macro/Terminal navigation origins or redirect isolation. Final network/host admission must be verified at the existing enforcement owner, not assumed from this constructor.
- The pinned native screenshot schema retains caller-selected `filename`; general canonical argument validation is JSON/size validation. This is not evidence of arbitrary filesystem exploitation, but it is insufficient to prove that the product-facing read capability cannot cause ungoverned file writes. Product publication should omit caller-selected file destinations or bind them through the existing artifact owner; upstream convenience guards alone are not the required security boundary.
- `browser_resize` is absent from the allowed tool set. Desktop/tablet/mobile acceptance therefore needs an explicitly admitted existing-owner viewport strategy or a separately versioned capability, not a claim that generic browser access already provides viewport switching.
- Snapshot, console and network reads must preserve the existing grant while refusing secret-bearing fields and wrong-product navigation. The inspected native-result adapter alone does not prove credential redaction or product entitlement. A credential-bearing screenshot cannot be made safe by an MCP OAuth scope alone.

Current Microsoft documentation explicitly describes Playwright MCP origin/file-access checks as convenience defenses, not a security boundary; origin lists do not cover redirects. Its output-directory documentation distinguishes automatically named files from caller-named files. These current upstream statements are architectural guidance, not a claim that a particular fleet runtime has been upgraded or qualified. The exact 0.0.79 tool schema used in the above fixture is retained in this repository.

## Existing-owner next slice

The Browser principal should keep #1259's original effect/custody state, integrate the merged #1071 path instead of replaying old stacks, and qualify a product-scoped static profile under BrowserResource/Capacity/RuntimeBinding/Workbench/Operator Harness. Required controls: approved origins and redirects at the actual network authority, exact app identity and entitlements, no arbitrary file selectors, disabled trading/admin flows, admitted viewport modes, secret-safe diagnostics, original-action reconciliation and exact image/evidence integrity.

First production browser acceptance remains: an actually admitted host and authenticated app profile opens approved Macro and Terminal pages; a real screenshot and snapshot are delivered into the requesting Web conversation; returned bytes and capture provenance are verified; then a real defect is reproduced and related to an exact authorized preview. The above local tests remove uncertainty about the native content representation only. No host placement, login ceremony, production probe or denied extension workaround is authorized by this assessment.

## Evidence locations

Protected source: `integrations/workbench_browser_mcp/app.py` (`_native_result` and final same-token check), `integrations/workbench_browser_mcp/tunnel.py`, `integrations/workbench_browser_mcp/browser_port.py`, `integrations/workbench_browser_mcp/contracts.py`, `control_plane/browser_resource_contract.py`, `research/evidence/claude_browser_mcp_tools_0_0_79.json`.

Artifact candidate: #838 at `75434f2dee94c298d6eb094f65decc04e109053c`, still draft/unmerged/uninstalled. Its PR body explicitly limits producer ownership to command stdout/stderr and requires actual native Web text/PNG consumption after existing-owner rollout.

Primary upstream guidance: https://playwright.dev/mcp/configuration/options and https://github.com/microsoft/playwright-mcp/blob/main/README.md. These references do not grant project permission or replace exact runtime validation.
