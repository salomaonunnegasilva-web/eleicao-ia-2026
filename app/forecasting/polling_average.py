import os
import math
from datetime import date
from sqlalchemy.orm import Session
from app.db.models import Poll, PollResult, Candidate
from app.text_utils import is_non_valid_vote_label

def calculate_polling_average(
    db: Session,
    scenario_name: str = "Estimulada Turno 1",
    round_num: int = 1,
    target_date: date = None
) -> dict:
    """
    Calculates the recency-weighted polling average for all candidates in a given scenario.
    Decay half-life is read from environment variable 'DECAY_HALF_LIFE_DAYS' (default: 30.0).
    """
    if target_date is None:
        target_date = date.today()

    half_life = float(os.getenv("DECAY_HALF_LIFE_DAYS", "30.0"))
    decay_rate = math.log(2) / half_life if half_life > 0 else 0

    # Query all results for the scenario
    query = (
        db.query(
            Poll.id.label("poll_id"),
            Poll.pollster.label("pollster"),
            Poll.publication_date.label("pub_date"),
            Poll.sample_size.label("sample_size"),
            PollResult.candidate_id.label("candidate_id"),
            Candidate.name.label("candidate_name"),
            PollResult.vote_intention.label("vote_intention"),
            PollResult.margin_of_error.label("moe")
        )
        .join(PollResult, Poll.id == PollResult.poll_id)
        .join(Candidate, PollResult.candidate_id == Candidate.id)
        .filter(PollResult.scenario_name == scenario_name)
        .filter(PollResult.round == round_num)
        .filter(Poll.publication_date <= target_date)
    )

    results = query.all()
    if not results:
        return {
            "scenario": scenario_name,
            "round": round_num,
            "target_date": str(target_date),
            "raw_averages": {},
            "valid_vote_averages": {},
            "polls_used": [],
            "total_polls": 0,
        }

    # Group results by poll to compute weight first
    polls_metadata = {}
    for r in results:
        poll_id = r.poll_id
        if poll_id not in polls_metadata:
            # Calculate weight
            days_ago = (target_date - r.pub_date).days
            # Weight decay: exp(-decay_rate * days_ago)
            weight_recency = math.exp(-decay_rate * max(0, days_ago))
            # Weight sample size: sqrt(sample_size)
            weight_size = math.sqrt(r.sample_size)
            # Total weight
            polls_metadata[poll_id] = {
                "weight": weight_recency * weight_size,
                "pollster": r.pollster,
                "pub_date": r.pub_date,
                "moe": r.moe
            }

    # Calculate weighted average for each candidate
    candidate_scores = {}
    # Track poll references
    used_polls = []

    for r in results:
        poll_id = r.poll_id
        c_id = r.candidate_id
        c_name = r.candidate_name

        weight = polls_metadata[poll_id]["weight"]
        vote_share = r.vote_intention

        if c_id not in candidate_scores:
            candidate_scores[c_id] = {
                "name": c_name,
                "weighted_sum": 0.0,
                "sum_of_weights": 0.0,
            }

        candidate_scores[c_id]["weighted_sum"] += vote_share * weight
        candidate_scores[c_id]["sum_of_weights"] += weight

        poll_info = {
            "poll_id": poll_id,
            "pollster": r.pollster,
            "pub_date": str(r.pub_date),
            "weight": weight
        }
        if poll_info not in used_polls:
            used_polls.append(poll_info)

    # Finalize average
    final_averages = {}
    for c_id, data in candidate_scores.items():
        if data["sum_of_weights"] > 0:
            final_averages[data["name"]] = round(data["weighted_sum"] / data["sum_of_weights"], 2)

    # Compute valid votes average (excluding Branco/Nulo and Não Sabe/Indeciso)
    valid_sum = 0.0
    for name, avg in final_averages.items():
        if not is_non_valid_vote_label(name):
            valid_sum += avg

    valid_vote_averages = {}
    if valid_sum > 0:
        for name, avg in final_averages.items():
            if not is_non_valid_vote_label(name):
                valid_vote_averages[name] = round((avg / valid_sum) * 100, 2)

    return {
        "scenario": scenario_name,
        "round": round_num,
        "target_date": str(target_date),
        "raw_averages": final_averages,
        "valid_vote_averages": valid_vote_averages,
        "polls_used": used_polls,
        "total_polls": len(used_polls)
    }
