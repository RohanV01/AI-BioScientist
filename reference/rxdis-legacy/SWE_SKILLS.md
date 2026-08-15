# SWE Skills Quick Reference

Invoke any skill by typing `/skill-name` in your Claude Code prompt.

---

## Project Lifecycle

| Command | What it does |
|---------|--------------|
| `/common-ground` | Surface Claude's hidden assumptions before work begins |
| `/project:discovery:create-epic-discovery` | Create a discovery doc for a research/customer epic |
| `/project:discovery:synthesize-discovery` | Consolidate discovery findings into an analysis + proposed tickets |
| `/project:discovery:approve-synthesis` | Approve synthesis and create implementation tickets |
| `/project:planning:create-epic-plan` | Analyze Jira tickets + codebase → epic planning doc |
| `/project:planning:create-implementation-plan` | Generate a step-by-step plan from a planning doc |
| `/project:execution:execute-ticket` | Execute a Jira ticket per its implementation plan |
| `/project:execution:complete-ticket` | Mark ticket done, transition Jira to "In Review" |
| `/project:retrospectives:complete-sprint` | Run a sprint retrospective |
| `/project:retrospectives:complete-epic` | Run an epic retrospective |

---

## Code Quality & Review

| Command | What it does |
|---------|--------------|
| `/code-review` | Review current diff — add `low/medium/high/max/ultra` for depth, `--comment` for inline PR comments, `--fix` to auto-apply |
| `/simplify` | Review changed code for reuse/simplification/efficiency and apply fixes |
| `/security-review` | Full security audit of codebase or diff |
| `/secure-code-guardian` | Security best-practice lens while writing code |
| `/fullstack-guardian` | Holistic full-stack correctness review |
| `/test-master` | Generate comprehensive test suites (unit, integration, e2e) |
| `/chaos-engineer` | Identify failure modes and resilience gaps |
| `/spec-miner` | Extract implicit specs and invariants from existing code |

---

## App Launch & Verification

| Command | What it does |
|---------|--------------|
| `/run` | Launch the project app and confirm changes work in the real app |
| `/verify` | Run the app and observe behavior to confirm a specific change works |
| `/init` | First-time project scaffolding and setup |

---

## Architecture & Design

| Command | What it does |
|---------|--------------|
| `/architecture-designer` | System architecture design with trade-offs |
| `/api-designer` | REST/GraphQL API contracts and schema design |
| `/microservices-architect` | Service decomposition and communication patterns |
| `/cloud-architect` | AWS/GCP/Azure architecture and cost optimization |
| `/graphql-architect` | GraphQL schema, resolvers, federation |
| `/feature-forge` | Break a feature request into implementable sub-tasks |

---

## Language Specialists

| Command | Language / Focus |
|---------|-----------------|
| `/python-pro` | Idiomatic Python, packaging, async, type hints |
| `/typescript-pro` | TypeScript patterns, generics, strict mode |
| `/javascript-pro` | JS runtime quirks, ES2024+, bundlers |
| `/golang-pro` | Go idioms, goroutines, interfaces |
| `/rust-engineer` | Ownership, lifetimes, async Rust |
| `/java-architect` | Java 21+, Spring, design patterns |
| `/kotlin-specialist` | Coroutines, Android, multiplatform |
| `/cpp-pro` | Modern C++23, templates, RAII |
| `/csharp-developer` | .NET 8+, LINQ, async/await |
| `/dotnet-core-expert` | ASP.NET Core, Blazor, EF Core |
| `/swift-expert` | SwiftUI, Combine, concurrency |
| `/php-pro` | PHP 8.3+, PSR standards, Composer |

---

## Frontend Frameworks

| Command | Framework |
|---------|-----------|
| `/react-expert` | React hooks, state, performance, RSC |
| `/nextjs-developer` | App router, SSR/SSG, middleware, Vercel |
| `/vue-expert` | Vue 3 Composition API, Pinia, Nuxt |
| `/vue-expert-js` | Vue 3 in plain JS (no TypeScript) |
| `/angular-architect` | Angular 17+, signals, standalone components |
| `/react-native-expert` | Expo, navigation, native modules |
| `/flutter-expert` | Dart, widgets, state management |

---

## Backend Frameworks

| Command | Framework |
|---------|-----------|
| `/fastapi-expert` | FastAPI, Pydantic v2, async routes |
| `/django-expert` | Django ORM, views, DRF |
| `/spring-boot-engineer` | Spring Boot 3, JPA, security |
| `/nestjs-expert` | NestJS modules, guards, interceptors |
| `/laravel-specialist` | Laravel 11, Eloquent, Livewire |
| `/rails-expert` | Ruby on Rails, ActiveRecord, Hotwire |
| `/wordpress-pro` | Themes, plugins, Gutenberg blocks |
| `/shopify-expert` | Liquid templates, Shopify APIs, apps |

---

## Data & ML

| Command | Focus |
|---------|-------|
| `/ml-pipeline` | End-to-end ML pipeline design and implementation |
| `/pandas-pro` | DataFrame operations, performance, vectorization |
| `/spark-engineer` | PySpark, Spark SQL, distributed compute |
| `/fine-tuning-expert` | LLM fine-tuning, PEFT, LoRA, datasets |
| `/rag-architect` | Retrieval-Augmented Generation system design |
| `/prompt-engineer` | Prompt design, few-shot, chain-of-thought |
| `/claude-api` | Anthropic SDK, model IDs, pricing, streaming, tool use, MCP |

---

## Infrastructure & DevOps

| Command | Focus |
|---------|-------|
| `/devops-engineer` | CI/CD pipelines, Docker, GitHub Actions |
| `/kubernetes-specialist` | K8s manifests, Helm, operators |
| `/terraform-engineer` | IaC modules, state management, providers |
| `/sre-engineer` | SLOs, runbooks, incident response |
| `/monitoring-expert` | Observability, metrics, alerting, dashboards |

---

## Database

| Command | Focus |
|---------|-------|
| `/postgres-pro` | Query optimization, indexes, partitioning |
| `/sql-pro` | General SQL, query design, window functions |
| `/database-optimizer` | Schema design, query plans, caching strategy |

---

## Tooling & Configuration

| Command | What it does |
|---------|--------------|
| `/update-config` | Modify `settings.json` — permissions, hooks, env vars, automated behaviors |
| `/keybindings-help` | Customize `~/.claude/keybindings.json` — rebind keys, chord shortcuts |
| `/fewer-permission-prompts` | Scan transcripts and add allowlist entries to reduce permission prompts |
| `/loop [interval] [/command]` | Run a command on a recurring interval (e.g. `/loop 5m /verify`) |
| `/schedule` | Create and manage cron-scheduled remote agents |
| `/atlassian-mcp` | Jira/Confluence integration via MCP |

---

## Specialized

| Command | What it does |
|---------|--------------|
| `/debugging-wizard` | Deep systematic root-cause analysis for tricky bugs |
| `/legacy-modernizer` | Plan migration of legacy code to modern patterns |
| `/embedded-systems` | Bare-metal, RTOS, hardware interfacing |
| `/cli-developer` | Build CLI tools with good UX (Click, Cobra, argparse) |
| `/mcp-developer` | Build Model Context Protocol servers and tools |
| `/salesforce-developer` | Apex, LWC, SOQL, Flow |
| `/code-documenter` | Generate docstrings, READMEs, and API docs |
| `/playwright-expert` | E2E test authoring, fixtures, page objects |
| `/websocket-engineer` | Real-time communication, WS protocols, scaling |
| `/game-developer` | Game loops, ECS, physics, rendering |
| `/the-fool` | Creative/lateral-thinking mode — challenges assumptions |
| `/review` | Review a pull request (pass PR number or URL) |

---

## Tips

- **Start ambiguous tasks with** `/common-ground` to validate assumptions first
- **For this project:** `/ml-pipeline`, `/fastapi-expert`, `/react-expert`, `/postgres-pro`, `/debugging-wizard` are most relevant
- **Deep PR review:** `/code-review ultra` triggers multi-agent cloud review of the current branch
- **Chain skills:** `/common-ground` → `/feature-forge` → `/project:planning:create-implementation-plan` → `/project:execution:execute-ticket`
