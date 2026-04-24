from django.db.models import Q
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from .models import ServiceRequest, Proposal, Category, CatalogService
from .serializers import (
    ServiceRequestSerializer, ProposalSerializer, 
    CategorySerializer, CatalogServiceSerializer
)
from ns_backend.utils import haversine_distance
from notifications.utils import send_notification
from rest_framework.views import APIView
from accounts.models import Profile, ServicePackage
from accounts.serializers import ProfileSerializer
from .ai_matching import EmbeddingService
from interactions.models import Appointment
from interactions.utils import send_appointment_confirmation_email
from .tasks import send_proposal_approval_email_task, send_new_proposal_email_task, send_direct_request_email_task
from django.core.cache import cache
import hashlib

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
    pagination_class = None

    @method_decorator(cache_page(60 * 60 * 2))  # Cache for 2 hours
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

class CatalogServiceViewSet(viewsets.ModelViewSet):
    queryset = CatalogService.objects.select_related('category').all()
    serializer_class = CatalogServiceSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
    pagination_class = None

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


    def perform_create(self, serializer):
        category_id = self.request.data.get('category')
        if not category_id:
            category, _ = Category.objects.get_or_create(
                name='Others',
                defaults={'description': 'Automatically created for custom services'}
            )
            serializer.save(category=category)
        else:
            serializer.save()

class ServiceRequestViewSet(viewsets.ModelViewSet):
    queryset = ServiceRequest.objects.select_related('user', 'user__profile', 'catalog_service', 'catalog_service__category').all()
    serializer_class = ServiceRequestSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'catalog_service__name']
    filterset_fields = ['catalog_service', 'status', 'user', 'target_provider']
    ordering_fields = ['created_at', 'price', 'scheduled_time']

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


    def get_queryset(self):
        queryset = self.queryset
        user = self.request.user
        
        if self.request.query_params.get('user_me'):
            queryset = queryset.filter(user=user)
        else:
            # EXCLUDE requests that already have an approved proposal
            unapproved = ~Q(proposals__is_approved=True)

            if user.is_authenticated:
                targeted_only = self.request.query_params.get('targeted') == 'true'
                
                if targeted_only:
                     queryset = queryset.filter(
                         Q(target_provider=user) & Q(status='OPEN') & unapproved
                     )
                else:
                    # Show OPEN, UNAPPROVED requests that are public (target_provider=None) 
                    # Also show my own requests unconditionally
                    queryset = queryset.filter(
                        (Q(status='OPEN') & Q(target_provider__isnull=True) & unapproved) |
                        Q(user=user)
                    )
            else:
                queryset = queryset.filter(Q(status='OPEN') & Q(target_provider__isnull=True) & unapproved)
        
        # Prevent duplicates due to the M2M NOT criteria evaluation
        queryset = queryset.distinct()
        
        # Prefetch related data for serialization (eliminates N+1 queries)
        queryset = queryset.prefetch_related(
            'proposals',
            'proposals__provider',
            'proposals__provider__profile',
            'appointments',
        )
        
        import math
        from django.db.models import F, FloatField
        from django.db.models.functions import ACos, Cos, Radians, Sin, Cast

        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        radius = self.request.query_params.get('radius')

        if lat and lng:
            lat = float(lat)
            lng = float(lng)
            lat_rad = math.radians(lat)
            lng_rad = math.radians(lng)

            # Cast DecimalField columns to float so Django can infer the
            # output type of the arithmetic expression without ambiguity.
            lat_col = Cast(F('latitude'), FloatField())
            lng_col = Cast(F('longitude'), FloatField())

            # Always annotate with DB-level distance when lat/lng are present.
            # This avoids the slow per-object Python fallback in the serializer.
            queryset = queryset.annotate(
                distance=6371 * ACos(
                    Sin(lat_rad) * Sin(Radians(lat_col)) +
                    Cos(lat_rad) * Cos(Radians(lat_col)) *
                    Cos(Radians(lng_col) - lng_rad),
                    output_field=FloatField(),
                )
            )

            if radius:
                radius = float(radius)
                # Bounding-box pre-filter (fast index scan)
                lat_delta = radius / 111.0
                lng_delta = radius / (111.0 * math.cos(math.radians(lat)))
                queryset = queryset.filter(
                    latitude__gte=lat - lat_delta,
                    latitude__lte=lat + lat_delta,
                    longitude__gte=lng - lng_delta,
                    longitude__lte=lng + lng_delta,
                    distance__lte=radius,
                ).order_by('distance')

        return queryset



    def perform_create(self, serializer):
        service_request = serializer.save(user=self.request.user)
        
        # Notify Provider if it's a direct request
        if service_request.target_provider:
            # Send Push Notification
            sender_name = self.request.user.profile.first_name if hasattr(self.request.user, 'profile') and self.request.user.profile.first_name else self.request.user.email
            send_notification(
                user=service_request.target_provider,
                title="New Direct Request",
                message=f"{sender_name} sent you a direct service request for {service_request.title}.",
                notification_type="DIRECT_REQUEST",
                data={"request_id": str(service_request.id)}
            )
            
            # Send Email (async)
            send_direct_request_email_task.delay(str(service_request.id))

    @action(detail=True, methods=['post'])
    def approve_proposal(self, request, pk=None):
        try:
            # Skip the ViewSet's heavy get_queryset logic for simple approval
            service_request = ServiceRequest.objects.get(pk=pk)
        except ServiceRequest.DoesNotExist:
             return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)

        if service_request.user != request.user:
            return Response({'error': 'Not authorized'}, status=status.HTTP_401_UNAUTHORIZED)
        
        proposal_id = request.data.get('proposal_id')
        try:
            with transaction.atomic():
                proposal = Proposal.objects.select_for_update().get(id=proposal_id, request=service_request)
                proposal.is_approved = True
                proposal.save()
                
                # Check if an appointment already exists for this proposal
                appointment = Appointment.objects.filter(proposal=proposal).first()
                if not appointment:
                    appointment = Appointment.objects.create(
                        seeker=service_request.user,
                        provider=proposal.provider,
                        title=service_request.title,
                        description=service_request.description,
                        appointment_date=service_request.scheduled_time,
                        service_request=service_request,
                        total_price=service_request.price or 0.00,
                        proposal=proposal
                    )

                # Update service request status
                service_request.status = 'IN_PROGRESS'
                service_request.save()

                # Notify Provider
                desc = service_request.description[:20] if service_request.description else "service request"
                send_notification(
                    user=proposal.provider,
                    sender=request.user,
                    title="Proposal Accepted",
                    message=f"Your proposal for {desc}... has been accepted!",
                    notification_type="PROPOSAL",
                    data={"proposal_id": str(proposal.id), "request_id": str(service_request.id)}
                )
                
                # Send Emails
                def dispatch_background_emails():
                    send_proposal_approval_email_task.delay(str(proposal.id))
                    from interactions.tasks import send_appointment_confirmation_email_task
                    send_appointment_confirmation_email_task.delay(str(appointment.id))
                
                transaction.on_commit(dispatch_background_emails)
                
            serializer = self.get_serializer(service_request)
            return Response(serializer.data)
        except Proposal.DoesNotExist:
            return Response({'error': 'Proposal not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def cancel_approval(self, request, pk=None):
        service_request = self.get_object()
        if service_request.user != request.user:
            return Response({'error': 'Not authorized'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Find approved proposal
        approved_proposal = Proposal.objects.filter(request=service_request, is_approved=True).first()
        if approved_proposal:
            with transaction.atomic():
                approved_proposal.is_approved = False
                approved_proposal.save()
                
                service_request.status = 'OPEN'
                service_request.save()

                # Delete associated appointment
                Appointment.objects.filter(proposal=approved_proposal).delete()
            
            return Response({'status': 'approval cancelled'})
        return Response({'error': 'No approved proposal found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['patch'], url_path='image')
    def upload_image(self, request):
        # Frontend sends {"id": "..."} in a field called "data" (JSON string)
        # and "image" as a file.
        data_str = request.data.get('data')
        if data_str:
            import json
            data = json.loads(data_str)
            request_id = data.get('id')
        else:
            request_id = request.data.get('id')
            
        if not request_id:
            return Response({'error': 'Request ID required'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            service_request = ServiceRequest.objects.get(id=request_id)
            if 'image' in request.FILES:
                service_request.image = request.FILES['image']
                service_request.save()
                serializer = self.get_serializer(service_request)
                return Response(serializer.data)
            return Response({'error': 'No image provided'}, status=status.HTTP_400_BAD_REQUEST)
        except ServiceRequest.DoesNotExist:
            return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)

class ProposalViewSet(viewsets.ModelViewSet):
    queryset = Proposal.objects.select_related(
        'provider', 'provider__profile',
        'request', 'request__user', 'request__user__profile',
    ).prefetch_related('request__proposals').all()
    serializer_class = ProposalSerializer
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print(f"Proposal creation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        try:
            # Try standard lookup by Proposal ID
            instance = self.get_queryset().get(pk=pk)
        except (Proposal.DoesNotExist, ValueError):
            # Fallback: Treat pk as ServiceRequest ID and find proposal for current provider
            try:
                instance = self.get_queryset().get(request_id=pk, provider=request.user)
            except (Proposal.DoesNotExist, ValueError):
                return Response({'error': 'Proposal or Request not found'}, status=status.HTTP_404_NOT_FOUND)
        
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        instance.delete()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(self._wrap_proposals(serializer.data)["requests_acceptance"])

        serializer = self.get_serializer(queryset, many=True)
        return Response(self._wrap_proposals(serializer.data))

    def _wrap_proposals(self, data):
        wrapped = []
        for item in data:
            provider_profile = item.get('provider_profile')
            seeker_profile = item.get('seeker_profile')
            # The frontend expects a specific structure for 'RequestAcceptance'
            wrapped.append({
                "acceptance": item,
                "provider": provider_profile,
                "user": seeker_profile
            })
        return {"requests_acceptance": wrapped}

    def get_queryset(self):
        queryset = self.queryset
        if self.request.query_params.get('provider_me'):
            queryset = queryset.filter(provider=self.request.user)
        
        service_request_id = self.request.query_params.get('service_request')
        if service_request_id:
            queryset = queryset.filter(request_id=service_request_id)
            
        approved_only = self.request.query_params.get('approved')
        if approved_only == 'true':
            queryset = queryset.filter(is_approved=True)
        elif approved_only == 'false':
            queryset = queryset.filter(is_approved=False)
            
        return queryset

    def perform_create(self, serializer):
        proposal = serializer.save(provider=self.request.user)
        
        # Notify Seeker
        service_request = proposal.request
        send_notification(
            user=service_request.user,
            title="New Proposal",
            message=f"You have a new proposal from {proposal.provider.email}",
            notification_type="PROPOSAL",
            data={"proposal_id": str(proposal.id), "request_id": str(service_request.id)}
        )
        
        # Send Email to Seeker (async)
        send_new_proposal_email_task.delay(str(proposal.id))

class MatchProvidersView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (JWTAuthentication,)

    def post(self, request):
        description = request.data.get('description')
        if not description:
            return Response({'error': 'Description is required'}, status=status.HTTP_400_BAD_REQUEST)

        # 0. Check Cache
        cache_key = f"ai_match_{hashlib.md5(description.encode()).hexdigest()}"
        cached_results = cache.get(cache_key)
        if cached_results:
            return Response(cached_results)

        # 1. Generate embedding for the query
        query_embedding = EmbeddingService.get_embedding(description)
        if not query_embedding:
            return Response({'error': 'Failed to generate embedding'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        matches = []
        # ... logic remains same ...
        # (skipping for brevity but will include the full logic in the tool call)
        # 2. Match against Profiles (Bio/About)
        # Fetch only ID and embedding to save memory
        profiles = Profile.objects.filter(user_type='PROVIDER').exclude(bio_embedding__isnull=True).only('id', 'bio_embedding', 'subscription_tier')
        for profile in profiles:
            similarity = EmbeddingService.cosine_similarity(query_embedding, profile.bio_embedding)
            # Apply tier-based priority boost
            boosted_score = similarity * float(profile.priority_score())
            if boosted_score > 0.15:
                matches.append({'type': 'profile', 'object_id': profile.id, 'score': boosted_score})

        # 3. Match against Service Packages
        packages = ServicePackage.objects.exclude(description_embedding__isnull=True).select_related('profile').only('id', 'profile_id', 'description_embedding', 'profile__subscription_tier')
        for pkg in packages:
             similarity = EmbeddingService.cosine_similarity(query_embedding, pkg.description_embedding)
             # Apply tier-based priority boost
             boosted_score = similarity * float(pkg.profile.priority_score())
             if boosted_score > 0.15:
                 matches.append({'type': 'package', 'object_id': pkg.profile_id, 'package_id': pkg.id, 'score': boosted_score})

        matches.sort(key=lambda x: x['score'], reverse=True)
        seen_providers = set()
        matched_ids = []
        for match in matches:
            provider_id = match['object_id']
            if provider_id not in seen_providers:
                seen_providers.add(provider_id)
                matched_ids.append(provider_id)
            if len(matched_ids) >= 10: break
        
        # Now fetch full profile objects for the top 10 results
        results = Profile.objects.filter(id__in=matched_ids).select_related('user', 'catalog_service', 'catalog_service__category').prefetch_related('portfolio_items', 'service_packages')
        
        # Maintain original score-based ordering
        results_map = {p.id: p for p in results}
        sorted_results = [results_map[p_id] for p_id in matched_ids if p_id in results_map]
        
        serializer = ProfileSerializer(sorted_results, many=True, context={'request': request})
        final_data = serializer.data
        
        # 4. Cache results for 30 minutes
        cache.set(cache_key, final_data, 60 * 30)
        
        return Response(final_data)
