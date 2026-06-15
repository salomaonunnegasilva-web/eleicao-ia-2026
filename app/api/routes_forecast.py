from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.main import get_db
from app.db.models import ForecastRun
from app.forecasting.polling_average import calculate_polling_average
from app.forecasting.simulations import run_monte_carlo_simulation
import datetime

router = APIRouter()

@router.get("/forecast/average")
def get_polling_average(
    scenario: str = "Estimulada Turno 1",
    round_num: int = Query(1, ge=1, le=2),
    db: Session = Depends(get_db)
):
    try:
        avg = calculate_polling_average(db, scenario_name=scenario, round_num=round_num)
        if avg["total_polls"] == 0:
            raise HTTPException(status_code=404, detail="No polls found for this scenario.")
        return avg
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to calculate polling average.") from e

@router.get("/forecast/simulation")
def get_simulation(
    scenario: str = "Estimulada Turno 1",
    round_num: int = Query(1, ge=1, le=2),
    iterations: int = Query(None, ge=100, le=50000),
    db: Session = Depends(get_db)
):
    try:
        sim = run_monte_carlo_simulation(
            db,
            scenario_name=scenario,
            round_num=round_num,
            num_iterations=iterations
        )
        if "error" in sim:
            raise HTTPException(status_code=404, detail=sim["error"])
        return sim
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to run simulation.") from e

@router.post("/forecast/run")
def trigger_forecast_run_save(
    scenario: str = "Estimulada Turno 1",
    round_num: int = 1,
    db: Session = Depends(get_db)
):
    try:
        avg = calculate_polling_average(db, scenario_name=scenario, round_num=round_num)
        sim = run_monte_carlo_simulation(db, scenario_name=scenario, round_num=round_num)
        if avg["total_polls"] == 0 or "error" in sim:
            raise HTTPException(status_code=404, detail="No polls found for this scenario.")

        run_record = ForecastRun(
            model_version="1.0.0",
            assumptions_json=sim.get("assumptions", {}),
            output_json={
                "averages": avg.get("raw_averages"),
                "valid_averages": avg.get("valid_vote_averages"),
                "runoff_probability": sim.get("runoff_probability"),
                "win_probabilities": sim.get("win_probabilities"),
                "candidate_summary": sim.get("candidate_summary")
            },
            data_cutoff_date=datetime.date.today()
        )
        db.add(run_record)
        db.commit()
        return {
            "status": "saved",
            "forecast_run_id": run_record.id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save forecast run.") from e
