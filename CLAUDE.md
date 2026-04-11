# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build Commands

```bash
npm install
npm run dev          # Vite dev server (frontend only, port 1420)
npm run tauri dev   # Full Tauri app with Rust backend
npm run build       # Production build (Vue TS check + Vite build)
npm run test        # Vitest (frontend tests)
cargo test --manifest-path src-tauri/Cargo.toml  # Rust tests
```

## Architecture

### Stack
- **Tauri 2** desktop shell (Rust backend)
- **Vue 3** + **TypeScript** frontend
- **Vitest** for frontend tests, **Rust's built-in test** framework for backend

### Frontend Structure (`src/`)
- `App.vue` — Root shell. Renders loading state, then main app layout using panels.
- `components/` — UI panels: `ConversationPanel`, `DiagnosticsPanel`, `HeroPanel`, `OnboardingPanel`, `ReviewSidebar`, `SelectedPackPanel`, `ToolCatalogPanel`, `VoicePanel`
- `composables/useAssistantState.ts` — Central state management. All frontend state lives here. Coordinates with Rust via `lib/api.ts` and handles action locking to prevent concurrent mutations.
- `lib/api.ts` — Wraps Tauri `invoke` calls (one per Tauri command) and `listen` for snapshot/voice events.
- `lib/types.ts` — Shared types between Rust and TypeScript: `AppSnapshot`, `VoiceRealtimeEvent`, `AssetPack`, `ConversationMessage`, `ApprovalRequest`, etc.
- `lib/presentation.ts` — Helpers for voice state machine (determines interruptibility, turn activity).

### Rust Backend (`src-tauri/src/`)
- `lib.rs` — Entry point. Registers all Tauri commands (`bootstrap_state`, `submit_text_turn`, `resolve_approval`, etc.), manages `AssistantState` via Tauri state, wires up event emitters. Also contains Rust tests.
- `app_state.rs` — Core `AssistantState` struct: owns `snapshot()` generation, hardware detection, asset pack selection, onboarding, voice arm state, conversation timeline, pending approvals.
- `gateway.rs` — Async task spawner. `spawn_text_turn`, `spawn_voice_turn`, `spawn_approval_follow_up` kick off background work and emit snapshot/voice events.
- `protocol.rs` — Serde-serializable types matching TypeScript types (`AppSnapshot`, `VoiceRealtimeEvent`, `VoiceSessionState`, `ApprovalStatus`).
- `runtime.rs` — Runtime/runner management (context budgets, benchmark execution).
- `catalog.rs` — Asset pack catalog (list available packs, track downloaded IDs).
- `hardware.rs` — Platform hardware detection (CPU cores, memory, GPU hints, tier classification).

### State Flow
1. Frontend mounts → `useAssistantState.initialize()` → calls `bootstrapState` Tauri command
2. Rust `AssistantState::snapshot()` returns `AppSnapshot` → frontend displays panels
3. User actions (send text, voice, approve) → `invoke` Tauri commands → Rust updates state and `emit_snapshot`
4. Backend emits `assistant://snapshot` events → frontend `subscribeToAssistantEvents` listener updates `snapshot.value`
5. Voice pipeline emits `assistant://voice` events → stored in `voiceEvents` for `VoicePanel` display

### Tauri Commands (one per action)
`bootstrap_state`, `select_asset_pack`, `complete_onboarding`, `toggle_voice_arm`, `submit_text_turn`, `simulate_voice_turn`, `resolve_approval`, `interrupt_voice`, `run_benchmarks`

### Key Patterns
- **Action locking**: `useAssistantState` uses `actionCounts` to prevent concurrent mutations of the same state (setup, text, voice, interrupt, approval, benchmark are all mutually exclusive actions)
- **Snapshot events**: Backend emits `assistant://snapshot` on every state change. Frontend re-subscribes on `initialize()` to always get fresh state
- **Voice state machine**: `VoiceSessionState` enum drives UI availability (which states are interruptible, whether composer is disabled)
- **Rust `manage` pattern**: `AssistantState` is owned by Tauri via `app.manage(AssistantState::new())` and accessed via `tauri::State`

## Recommended IDE Setup

- VS Code with Tauri, Vue (Volar), and rust-analyzer extensions
