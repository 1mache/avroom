# Architecture Overview

## Project Goal

Avroom is an AI-powered application that allows users to select and remove objects or furniture from room photos and naturally inpaint the missing background. The user clicks on an object in a photo; the system segments it, erases it, and reconstructs the background behind it using generative AI.

## High-Level System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        react-front (UI)                         │
│    Upload image  →  Click on object  →  View results            │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP (JSON / multipart)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      fastApi-app (API)                          │
│    POST /images/upload    POST /images/click                    │
└────────────────────────────┬────────────────────────────────────┘
                             │  Python in-process call
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              TestModules/src  (CV/ML Pipeline)                  │
│                                                                 │
│   OptimizedDepthFacade → SamImageAdapter → BoundaryVariance     │
│             ↓                                   ↓               │
│        depth map            Router decides SAM input +          │
│                             expansion parameters                │
│                                   ↓                             │
│              SamFacadeSingleton  →  mask                        │
│                                   ↓                             │
│              MaskRefiner  →  refined mask                       │
│                                   ↓                             │
│              HybridInpainter (LaMa + Stable Diffusion)          │
│                                   ↓                             │
│              background_bgr  +  cutout_bgra                     │
└─────────────────────────────────────────────────────────────────┘
```

## Design Principles

The pipeline follows **SOLID** principles with a clear separation of concerns:

| Principle | Application |
|---|---|
| Single Responsibility | Each class does exactly one job (depth, segmentation, inpainting, routing) |
| Open/Closed | New routing strategies or inpainters can be added without modifying `ObjectRemover` |
| Liskov Substitution | All inpainters are interchangeable via `IInpainter`; all routers via `ISegmentationRoutingStrategy` |
| Interface Segregation | Interfaces are minimal and role-specific (`IDepthFacade`, `IImageAdapter`, etc.) |
| Dependency Inversion | `ObjectRemover` depends on abstract interfaces, not concrete implementations |

## Design Patterns Used

| Pattern | Class | Purpose |
|---|---|---|
| Singleton | `SamFacadeSingleton`, `ImageDepthMapper`, `LamaInpainter` | Prevent re-loading heavy models |
| Facade | `OptimizedDepthFacade`, `SamFacadeSingleton` | Hide complex model internals behind a simple interface |
| Adapter | `SamImageAdapter` | Convert grayscale depth maps to RGB arrays that SAM can process |
| Strategy | All `*RoutingStrategy` classes | Swap the routing algorithm without changing the orchestrator |
| Composition | `CacheComponent` inside `SamImageAdapter`, `MaskRefiner` inside `SamFacadeSingleton` | Assemble behavior from focused components rather than inheritance |

## Subsystem Index

| Subsystem | Source Location | Documentation |
|---|---|---|
| CV/ML Pipeline | `TestModules/src/` | [`docs/pipeline/`](../pipeline/overview.md) |
| FastAPI Service | `fastApi-app/` | [`docs/api/`](../api/overview.md) |
| React Frontend | `react-front/` | [`docs/frontend/`](../frontend/overview.md) |
| Shared Context | — | This folder (`docs/shared/`) |
