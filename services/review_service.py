from models import Review, ActivityLog

def record_review(db, assignment, outcome, feedback, actor="admin"):
    review = Review(assignment_id=assignment.id, outcome=outcome, feedback=feedback)
    assignment.feedback = feedback
    if outcome == "APPROVED":
        assignment.status = "APPROVED"
    elif outcome == "CHANGES_REQUESTED":
        assignment.status = "REVISION_REQUIRED"
    else:
        assignment.status = "UNDER_REVIEW"
    db.add(review)
    db.add(ActivityLog(actor_email=actor, action=f"REVIEW_{outcome}", details=f"assignment_id={assignment.id}"))
    db.commit()
    db.refresh(review)
    return review
