"""
One-time migration script: Restore service requests that were incorrectly
auto-expired (status=CANCELLED) despite having pending proposals.

Run on the live server:
  python fix_expired_requests.py

This is safe to run — it only affects requests that:
1. Were set to CANCELLED
2. Have at least one proposal (meaning a provider accepted)
3. Do NOT already have an approved proposal (those are truly IN_PROGRESS)
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ns_backend.settings')
django.setup()

from services.models import ServiceRequest, Proposal
from audit.utils import log_audit_action
from django.db.models import Q

# Find CANCELLED requests that have proposals but none approved
# These were incorrectly auto-expired
candidates = ServiceRequest.objects.filter(
    status='CANCELLED'
).filter(
    proposals__isnull=False  # Has at least one proposal
).exclude(
    proposals__is_approved=True  # But no approved proposal (those stay as-is)
).distinct()

print(f"Found {candidates.count()} incorrectly auto-expired request(s) to restore.\n")

restored = []
for req in candidates:
    proposal_count = req.proposals.count()
    print(f"  Restoring: {req.id} | '{req.title}' | {proposal_count} proposal(s)")
    req.status = 'OPEN'
    req.save()
    
    log_audit_action(
        user=None,
        action='RESTORE_REQUEST',
        resource_type='ServiceRequest',
        resource_id=req.id,
        details={'reason': 'Incorrectly auto-expired despite having proposals; restored to OPEN'},
    )
    restored.append(req.id)

print(f"\nDone. Restored {len(restored)} request(s) to OPEN status.")
if restored:
    for rid in restored:
        print(f"  - {rid}")
