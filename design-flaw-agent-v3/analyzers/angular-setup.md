# Angular / TypeScript — Design-Focused Lint Setup

## 1. Install architecture-aware ESLint plugins

```bash
npm install -D @angular-eslint/eslint-plugin eslint-plugin-rxjs eslint-plugin-rxjs-angular eslint-plugin-boundaries
```

## 2. `.eslintrc.json` (key design rules)

```json
{
  "plugins": ["@angular-eslint", "rxjs", "rxjs-angular", "boundaries"],
  "overrides": [
    {
      "files": ["*.ts"],
      "rules": {
        "rxjs/no-ignored-subscription": "error",
        "rxjs/no-unsafe-takeuntil": "error",
        "rxjs-angular/prefer-takeuntil": ["error", { "alias": ["untilDestroyed"] }],
        "rxjs/no-nested-subscribe": "error",

        "@angular-eslint/component-class-suffix": "error",
        "@angular-eslint/no-input-rename": "error",
        "@angular-eslint/use-lifecycle-interface": "error",
        "@angular-eslint/contextual-lifecycle": "error",

        "@typescript-eslint/no-explicit-any": "warn",
        "@typescript-eslint/explicit-member-accessibility": [
          "warn",
          { "accessibility": "explicit" }
        ],
        "@typescript-eslint/no-floating-promises": "error",

        "boundaries/element-types": [
          "error",
          {
            "default": "disallow",
            "rules": [
              { "from": "feature", "allow": ["shared", "core"] },
              { "from": "shared", "allow": ["shared"] },
              { "from": "core", "allow": ["core", "shared"] }
            ]
          }
        ]
      }
    }
  ],
  "settings": {
    "boundaries/elements": [
      { "type": "feature", "pattern": "src/app/features/*" },
      { "type": "shared", "pattern": "src/app/shared/*" },
      { "type": "core", "pattern": "src/app/core/*" }
    ]
  }
}
```

## 3. What each rule catches (design relevance)

| Rule | Design flaw it catches |
|---|---|
| `rxjs/no-ignored-subscription` | Subscription leaks — never unsubscribed, memory growth |
| `rxjs-angular/prefer-takeuntil` | Missing cleanup pattern in components |
| `@typescript-eslint/no-floating-promises` | Fire-and-forget async with swallowed errors |
| `boundaries/element-types` | Incorrect dependency direction between feature/shared/core modules |
| `@angular-eslint/use-lifecycle-interface` | Implicit lifecycle hooks (harder to test/verify) |
| `@typescript-eslint/no-explicit-any` | Leaky abstractions / lost type safety at boundaries |

## 4. Smart vs Dumb component check (manual + Copilot)

No automated lint fully detects "business logic in a component", but combine:
- ESLint `max-lines` / `complexity` on `*.component.ts` files to flag bloated components
- Then have the Design Flaw Reviewer chat mode inspect flagged files for
  business logic that should move to a service/store.

```json
{
  "files": ["*.component.ts"],
  "rules": {
    "max-lines": ["warn", 200],
    "complexity": ["warn", 10]
  }
}
```

## 5. NgRx / state management (if used)

- `@ngrx/eslint-plugin` catches direct state mutation outside reducers,
  effects without error handling (`catchError` missing), and selectors
  recomputing unnecessarily.
