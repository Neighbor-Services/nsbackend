from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceRequestViewSet, ProposalViewSet, CategoryViewSet, CatalogServiceViewSet, MatchProvidersView

router = DefaultRouter()
router.register(r'requests', ServiceRequestViewSet)
router.register(r'proposals', ProposalViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'catalog-services', CatalogServiceViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('match-providers/', MatchProvidersView.as_view(), name='match-providers'),
]
