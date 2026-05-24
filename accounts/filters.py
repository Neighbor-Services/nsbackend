
import django_filters
from .models import Profile

class ProfileFilter(django_filters.FilterSet):
    price_min = django_filters.NumberFilter(field_name="catalog_services__base_price", lookup_expr='gte')
    price_max = django_filters.NumberFilter(field_name="catalog_services__base_price", lookup_expr='lte')
    rating_min = django_filters.NumberFilter(field_name="average_rating", lookup_expr='gte')
    category_id = django_filters.UUIDFilter(field_name="catalog_services__category__id")
    category_name = django_filters.CharFilter(field_name="catalog_services__category__name", lookup_expr='icontains')
    service_name = django_filters.CharFilter(field_name="catalog_services__name", lookup_expr='icontains')
    service_id = django_filters.UUIDFilter(field_name="catalog_services__id")
    city = django_filters.CharFilter(field_name="city", lookup_expr='icontains')
    user = django_filters.UUIDFilter(field_name="user__id")

    class Meta:
        model = Profile
        fields = ['user_type', 'city', 'user']
