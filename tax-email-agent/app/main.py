# TODO: implement — see PLAN.md
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Tax Email Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-Provider"],
)


# GET  /api/emails        — list queue
# POST /api/emails        — add raw email (status=pending)
# PATCH /api/emails/{id}  — mark done
# POST /api/process       — two-step agent call (see agent.py)
