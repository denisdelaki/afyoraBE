from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import KNHTSConcept, MedicationHPT, TerminologyCatalog
from .serializers import KNHTSConceptSerializer, MedicationHPTSerializer, TerminologyCatalogSerializer


class KNHTSConceptViewSet(viewsets.ModelViewSet):
    """
    KNHTS concept catalog – supports code lookup, search, and cross-system
    terminology mapping (SNOMED CT, ICD-11, LOINC, CIEL, KEMSA HPT).
    """
    queryset = KNHTSConcept.objects.filter(is_active=True)
    serializer_class = KNHTSConceptSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        code_system = self.request.query_params.get('codeSystem')
        if code_system:
            qs = qs.filter(code_system=code_system)
        domain = self.request.query_params.get('domain')
        if domain:
            qs = qs.filter(domain=domain)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(display__icontains=search) |
                Q(code__icontains=search) |
                Q(synonyms__icontains=search)
            )
        return qs

    @action(detail=False, methods=['get'], url_path='lookup')
    def lookup(self, request):
        """Look up a concept by exact code and code system."""
        code = request.query_params.get('code')
        code_system = request.query_params.get('codeSystem', 'KNHTS')
        if not code:
            return Response({'error': 'code parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            concept = KNHTSConcept.objects.get(code=code, code_system=code_system, is_active=True)
            return Response(KNHTSConceptSerializer(concept).data)
        except KNHTSConcept.DoesNotExist:
            return Response({'error': f'Concept {code} not found in {code_system}.'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], url_path='gender-codes')
    def gender_codes(self, request):
        """Return KNHTS-compliant gender concept codes."""
        concepts = KNHTSConcept.objects.filter(domain='Gender', is_active=True)
        return Response(KNHTSConceptSerializer(concepts, many=True).data)

    @action(detail=False, methods=['get'], url_path='catalog-summary')
    def catalog_summary(self, request):
        """Return a summary of concept counts by code system and domain."""
        from django.db.models import Count
        by_system = (
            KNHTSConcept.objects.filter(is_active=True)
            .values('code_system')
            .annotate(count=Count('id'))
            .order_by('code_system')
        )
        by_domain = (
            KNHTSConcept.objects.filter(is_active=True)
            .values('domain')
            .annotate(count=Count('id'))
            .order_by('domain')
        )
        catalogs = TerminologyCatalog.objects.all()
        return Response({
            'byCodeSystem': list(by_system),
            'byDomain': list(by_domain),
            'catalogs': TerminologyCatalogSerializer(catalogs, many=True).data,
        })


class MedicationHPTViewSet(viewsets.ModelViewSet):
    """
    KEMSA/KNHTS Health Products & Technologies drug registry.
    Supports drug-allergy cross-checking and essential medicines lookup.
    """
    queryset = MedicationHPT.objects.filter(is_active=True)
    serializer_class = MedicationHPTSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(generic_name__icontains=search) |
                Q(brand_names__icontains=search) |
                Q(kemsa_code__icontains=search) |
                Q(atc_code__icontains=search)
            )
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        essential_only = self.request.query_params.get('essentialOnly')
        if essential_only and essential_only.lower() == 'true':
            qs = qs.filter(is_on_essential_medicines_list=True)
        return qs

    @action(detail=False, methods=['post'], url_path='check-allergy')
    def check_allergy(self, request):
        """
        Drug-allergy cross-check: given a drug code and patient allergy list,
        returns any conflicts found.
        """
        drug_code = request.data.get('drugCode')
        allergens = request.data.get('allergens', [])  # list of allergen names
        if not drug_code:
            return Response({'error': 'drugCode is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            drug = MedicationHPT.objects.get(kemsa_code=drug_code, is_active=True)
        except MedicationHPT.DoesNotExist:
            return Response({'error': f'Drug {drug_code} not found in HPT registry.'}, status=status.HTTP_404_NOT_FOUND)

        conflicts = []
        drug_names = [drug.generic_name.lower()]
        if drug.brand_names:
            drug_names += [b.strip().lower() for b in drug.brand_names.split(',')]

        for allergen in allergens:
            if any(allergen.lower() in name for name in drug_names):
                conflicts.append({'allergen': allergen, 'drug': drug.generic_name, 'severity': 'CRITICAL'})

        return Response({
            'drug': MedicationHPTSerializer(drug).data,
            'conflicts': conflicts,
            'isSafe': len(conflicts) == 0,
        })


class TerminologyCatalogViewSet(viewsets.ModelViewSet):
    queryset = TerminologyCatalog.objects.all()
    serializer_class = TerminologyCatalogSerializer
