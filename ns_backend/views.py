from django.utils import timezone
from django.core.cache import cache
from django.db.models import Sum, Count
from django.db.models.functions import TruncDay
from accounts.models import User, Profile
from services.models import ServiceRequest, Proposal
from payments.models import WalletTransaction, Subscription, PayoutRequest

def dashboard_callback(request, context):
    """
    Callback to provide statistics for the Unfold admin dashboard.
    Uses caching to improve performance for expensive aggregations.
    """
    # Use v2 key to invalidate old cache structure
    stats = cache.get('admin_dashboard_stats_v2')
    
    if not stats:
        # Calculate Revenue
        total_revenue = WalletTransaction.objects.filter(
            status='COMPLETED', 
            transaction_type='DEBIT'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Calculate Active Subscriptions
        active_subs = Subscription.objects.filter(is_active=True).count()
        
        stats = {
            "total_users": User.objects.count(),
            "new_users_7d": User.objects.filter(
                created_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).count(),
            "total_revenue": total_revenue,
            "active_subscriptions": active_subs,
            "pending_payouts": PayoutRequest.objects.filter(status='PENDING').count(),
            "total_providers": Profile.objects.filter(user_type='PROVIDER').count(),
        }
        # Cache for 5 minutes
        cache.set('admin_dashboard_stats_v2', stats, 60 * 5)
    
    # Calculate Chart Data (Revenue last 30 days) - Cache separately or with stats?
    # Let's keep it real-time-ish or use a separate cache key if expensive.
    # For now, let's just calculate it.
    
    end_date = timezone.now()
    start_date = end_date - timezone.timedelta(days=30)
    
    daily_revenue = WalletTransaction.objects.filter(
        status='COMPLETED',
        transaction_type='DEBIT',
        created_at__gte=start_date
    ).annotate(date=TruncDay('created_at')).values('date').annotate(
        total=Sum('amount')
    ).order_by('date')
    
    # Format for Chart.js
    revenue_data = {
        item['date'].strftime('%Y-%m-%d'): item['total'] 
        for item in daily_revenue
    }
    
    chart_labels = []
    chart_data = []
    current = start_date
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        chart_labels.append(current.strftime('%b %d'))
        chart_data.append(float(revenue_data.get(date_str, 0)))
        current += timezone.timedelta(days=1)


    # Define KPIs structure
    kpis = [
        {
            "title": "Total Revenue",
            "metric": f"${stats.get('total_revenue', 0):,.2f}",
            "footer": "Total Transaction Volume",
            "icon": "payments",
        },
        {
            "title": "Active Subscriptions",
            "metric": stats.get('active_subscriptions', 0),
            "footer": "Recurring Revenue",
            "icon": "card_membership",
        },
        {
            "title": "Total Users",
            "metric": stats.get('total_users', 0),
            "footer": f"+{stats.get('new_users_7d', 0)} this week",
            "icon": "group",
        },
            {
            "title": "Pending Payouts",
            "metric": stats.get('pending_payouts', 0),
            "footer": "Requires Action",
            "icon": "pending_actions",
        },
    ]

    # Update context with both keys for compatibility
    context.update({
        "kpi": kpis,
        "stats": kpis,
        "chart_labels": chart_labels,
        "chart_data": chart_data,
    })
    
    return context
