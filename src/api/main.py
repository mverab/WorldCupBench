from fastapi import FastAPI, HTTPException, Query
from typing import Annotated

from src.api.disagreement import (
    PHASE_GROUP,
    PHASE_KNOCKOUT,
    build_disagreement_response,
    load_predictions,
    load_tournament,
)

app = FastAPI(title="WorldCupBench API")

VALID_PHASES = {PHASE_GROUP, PHASE_KNOCKOUT}


@app.get("/api/disagreement")
def get_disagreement(
    phase: Annotated[str | None, Query(description="Filter by phase: group or knockout")] = None,
    models: Annotated[str | None, Query(description="Comma-separated model names")] = None,
):
    if phase and phase not in VALID_PHASES:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")

    model_names = None
    if models:
        model_names = [m.strip() for m in models.split(",") if m.strip()]

    try:
        tournament = load_tournament()
        predictions = load_predictions()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not predictions:
        raise HTTPException(status_code=500, detail="No predictions found")

    return build_disagreement_response(tournament, predictions, phase, model_names)
