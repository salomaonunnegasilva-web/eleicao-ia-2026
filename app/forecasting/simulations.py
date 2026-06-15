import os
import numpy as np
import pandas as pd
from datetime import date
from sqlalchemy.orm import Session
from app.db.models import Poll, PollResult, Candidate
from app.forecasting.polling_average import calculate_polling_average
from app.text_utils import is_non_valid_vote_label

def run_monte_carlo_simulation(
    db: Session,
    scenario_name: str = "Estimulada Turno 1",
    round_num: int = 1,
    target_date: date = None,
    num_iterations: int = None
) -> dict:
    """
    Runs a Monte Carlo simulation of the election based on the polls.
    For each iteration, it draws candidate support from normal distributions centered on each poll's
    reported results (using margin of error to define SD), aggregates them using recency/size weights,
    and calculates final vote shares, runoff probabilities, and head-to-head frequencies.
    """
    if target_date is None:
        target_date = date.today()

    if num_iterations is None:
        num_iterations = int(os.getenv("MONTE_CARLO_ITERATIONS", "10000"))

    import math
    half_life = float(os.getenv("DECAY_HALF_LIFE_DAYS", "30.0"))
    decay_rate = math.log(2) / half_life if half_life > 0 else 0

    # Get the deterministic average to extract polls metadata and baseline weights
    avg_data = calculate_polling_average(db, scenario_name, round_num, target_date)
    polls_used = avg_data.get("polls_used", [])

    if not polls_used:
        return {
            "error": "No polls available to simulate.",
            "scenario": scenario_name,
            "round": round_num
        }

    poll_ids = [p["poll_id"] for p in polls_used]

    # Query all results for these specific polls
    query = (
        db.query(
            PollResult.poll_id.label("poll_id"),
            Candidate.name.label("candidate_name"),
            PollResult.vote_intention.label("vote_intention"),
            PollResult.margin_of_error.label("moe")
        )
        .join(Candidate, PollResult.candidate_id == Candidate.id)
        .filter(PollResult.poll_id.in_(poll_ids))
        .filter(PollResult.scenario_name == scenario_name)
        .filter(PollResult.round == round_num)
    )

    records = query.all()

    # Structure data: index by poll_id, columns are candidates
    poll_dict = {}
    candidate_names = sorted(list(set(r.candidate_name for r in records)))

    for r in records:
        if r.poll_id not in poll_dict:
            poll_dict[r.poll_id] = {
                "intentions": {},
                "moes": {}
            }
        poll_dict[r.poll_id]["intentions"][r.candidate_name] = r.vote_intention
        poll_dict[r.poll_id]["moes"][r.candidate_name] = r.moe

    # Weights array
    weights_dict = {p["poll_id"]: p["weight"] for p in polls_used}
    poll_ids_ordered = list(poll_dict.keys())
    weights = np.array([weights_dict[pid] for pid in poll_ids_ordered])
    sum_weights = np.sum(weights)

    if sum_weights <= 0:
        return {"error": "Weights sum is zero."}

    # Initialize arrays for simulations
    num_polls = len(poll_ids_ordered)
    num_candidates = len(candidate_names)

    # Matrix of shapes: (num_polls, num_candidates)
    base_intentions = np.zeros((num_polls, num_candidates))
    moes = np.zeros((num_polls, num_candidates))

    for i, pid in enumerate(poll_ids_ordered):
        for j, cname in enumerate(candidate_names):
            base_intentions[i, j] = poll_dict[pid]["intentions"].get(cname, 0.0)
            moes[i, j] = poll_dict[pid]["moes"].get(cname, 2.0)

    # Perform simulations
    # Standard deviation: moe / 1.96 (assuming 95% confidence interval for MOE)
    sds = moes / 1.96

    # Sim shape: (num_iterations, num_polls, num_candidates)
    # Draw from normal distribution
    sim_draws = np.zeros((num_iterations, num_polls, num_candidates))

    random_seed = int(os.getenv("MONTE_CARLO_SEED", "42"))
    rng = np.random.default_rng(random_seed)

    # Using numpy vectorization for fast drawing
    for i in range(num_polls):
        for j in range(num_candidates):
            sim_draws[:, i, j] = rng.normal(
                loc=base_intentions[i, j],
                scale=sds[i, j],
                size=num_iterations
            )

    # Clip negative values
    sim_draws = np.clip(sim_draws, a_min=0, a_max=100)

    # Normalize draws so each poll's candidates sum to 100% (or total poll sum)
    # This prevents draws from expanding/contracting the total voter base
    poll_sums = np.sum(base_intentions, axis=1) # (num_polls,)
    sim_sums = np.sum(sim_draws, axis=2) # (num_iterations, num_polls)

    for i in range(num_polls):
        # Avoid division by zero
        factor = np.where(sim_sums[:, i] > 0, poll_sums[i] / sim_sums[:, i], 1.0)
        sim_draws[:, i, :] *= factor[:, np.newaxis]

    # Weighted average across polls for each iteration
    # weights shape: (num_polls,)
    # Weighted sum: multiply sim_draws by weights along the poll axis, then sum
    # Resulting shape: (num_iterations, num_candidates)
    # We broadcast weights across iterations and candidates
    weighted_draws = np.sum(sim_draws * weights[np.newaxis, :, np.newaxis], axis=1) / sum_weights

    # Analyze simulated outcomes
    sim_df = pd.DataFrame(weighted_draws, columns=candidate_names)

    # Non-valid candidates
    valid_cols = [col for col in candidate_names if not is_non_valid_vote_label(col)]
    if not valid_cols:
        return {
            "error": "No valid candidates available to simulate.",
            "scenario": scenario_name,
            "round": round_num,
        }

    # Compute valid vote shares per iteration
    valid_sums = sim_df[valid_cols].sum(axis=1)
    sim_df_valid = sim_df[valid_cols].div(valid_sums, axis=0) * 100

    # Summarize candidates support
    candidate_summary = {}
    for cname in candidate_names:
        series = sim_df[cname]
        q_025 = np.percentile(series, 2.5)
        q_50 = np.percentile(series, 50.0)
        q_975 = np.percentile(series, 97.5)

        summary = {
            "mean": float(np.mean(series)),
            "median": float(q_50),
            "ci_lower": float(q_025),
            "ci_upper": float(q_975)
        }

        # Add valid votes stats if candidate is valid
        if cname in valid_cols:
            v_series = sim_df_valid[cname]
            v_q_025 = np.percentile(v_series, 2.5)
            v_q_50 = np.percentile(v_series, 50.0)
            v_q_975 = np.percentile(v_series, 97.5)
            summary["valid_median"] = float(v_q_50)
            summary["valid_ci_lower"] = float(v_q_025)
            summary["valid_ci_upper"] = float(v_q_975)

        candidate_summary[cname] = summary

    # Probabilities of runoff and wins
    runoff_count = 0
    win_counts = {cname: 0 for cname in valid_cols}
    top_two_counts = {cname: 0 for cname in valid_cols}

    # For each iteration, check if any candidate is > 50% in valid votes
    for i in range(num_iterations):
        valid_row = sim_df_valid.iloc[i]
        top_two = valid_row.nlargest(2)
        top_cand = top_two.index[0]
        top_val = top_two.values[0]

        # Track who is in the top two (potential second round candidates)
        for cand in top_two.index:
            top_two_counts[cand] += 1

        if top_val > 50.0:
            win_counts[top_cand] += 1
        else:
            runoff_count += 1

    win_probabilities = {cname: round((count / num_iterations) * 100, 2) for cname, count in win_counts.items()}
    runoff_probability = round((runoff_count / num_iterations) * 100, 2)
    top_two_probabilities = {cname: round((count / num_iterations) * 100, 2) for cname, count in top_two_counts.items()}

    # Calculate head-to-head match-up distributions (if there are runoff scenarios in db)
    # Let's return the results
    return {
        "scenario": scenario_name,
        "round": round_num,
        "iterations": num_iterations,
        "cutoff_date": str(target_date),
        "candidate_summary": candidate_summary,
        "win_probabilities": win_probabilities,
        "runoff_probability": runoff_probability,
        "top_two_probabilities": top_two_probabilities,
        "assumptions": {
            "half_life_days": half_life,
            "decay_rate": decay_rate,
            "sample_size_weighted": True,
            "random_seed": random_seed,
            "distribution": "Normal (using margin of error / 1.96 as standard deviation)"
        }
    }
