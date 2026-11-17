<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.

## What Lovable manages

Rules outside this block are the project's own. Change the pieces below in
Lovable, not by hand. With the [Lovable MCP](https://mcp.lovable.dev)
connected, `send_message` asks Lovable to do it; otherwise ask the user to
use the editor.

- **Database.** Do not add or edit `supabase/migrations/` or `drizzle/`.
  Ask Lovable to change the schema.
- **Generated files.** Do not edit a file whose header says it is automatically
  generated.
- **AI gateway.** Keep model calls on Lovable's gateway, and keep
  `LOVABLE_API_KEY` out of browser code.
- **Connectors.** Lovable provides native connectors. `list_connectors` shows
  which are enabled; `add_connector` only returns the dashboard link. When a
  connector is enabled, calls go through the connector gateway and need
  `LOVABLE_API_KEY`. When Lovable does not provide one, users can bring their
  own key and store it in Secrets.
- **Secrets.** Lovable manages them. Do not put secret values in the repo.
<!-- LOVABLE:END -->

<!-- AGENT-MEMORY:BEGIN -->
## Architecture rules
- Public site routes live at `/`, `/how-it-works`, etc. and wrap content in `SiteLayout`; the product app lives under `/app/*` with `src/routes/app.tsx` as the sidebar layout. Why: two experiences, one design system.
- All engine protocol details (`/ws/session`, `/api/info`, `/api/export`) stay in `src/lib/engine/client.ts`; the wire format there is an assumption until verified against the engine source. Why: the UI must not depend on unverified protocol details.
- Measured figures come only from `src/lib/benchmarks.ts`; anything in `src/lib/demo-data.ts` must render with a visible Demonstration/Illustrative label. Why: the product must never present invented metrics as real.
- The preview never animates the portrait in the browser; only engine frames drawn to the stage canvas show motion. Why: fake zoom/wobble animation is explicitly forbidden.
- Shared Studio state uses the tiny external store in `src/lib/store.ts` (`studioStore`, `settingsStore` persisted to localStorage); no database or auth. Why: the engine persists nothing and accounts are out of scope.
- SVG geometry is rounded (`round()` in `face-geometry.ts`) so SSR and client attributes match. Why: float drift caused hydration mismatches.
<!-- AGENT-MEMORY:END -->
