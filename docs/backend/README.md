# Backend Docs

The FastAPI service in [`fastApi-app/`](../../fastApi-app/) is a thin HTTP shell over the AI pipeline. It manages image storage, validates input, and calls `ObjectRemover` in-process.

## Pages

- [overview.md](overview.md) — what the service is and how it's wired.
- [api-endpoints.md](api-endpoints.md) — every HTTP endpoint with request/response.
- [core-image-processing.md](core-image-processing.md) — the bridge module that calls into the AI pipeline.
- [schemas.md](schemas.md) — Pydantic models.
- [settings-and-storage.md](settings-and-storage.md) — image storage directory resolution.
- [data-flow.md](data-flow.md) — request lifecycle for upload + click.

## At a glance

```mermaid
flowchart LR
    main["main.py<br/>FastAPI app + CORS"]
    routes["api/routes.py<br/>/images router"]
    objects["api/objects.py<br/>/objects router"]
    core["core/image_processing.py<br/>bridge to AI pipeline"]
    schemas["schemas/image.py<br/>Pydantic models"]
    settings["settings.py<br/>image dir"]
    pipeline["avroom_object_removal<br/>(TestModules)"]
    disk[("fastApi-app/tmp/images/")]

    main -->|include_router| routes
    main -->|include_router| objects
    routes -->|validates with| schemas
    routes -->|delegates to| core
    routes -->|asks for| settings
    core -->|"in-process import"| pipeline
    routes -->|writes upload| disk
    core -->|reads bytes| disk
    objects -->|reads cutout| disk
```
